"""モーニングページ1枚ごとの記録を作る(日報とは別の入れ物。dashboard の「モーニングページ」画面用)。

- ヘッダーの表(時間・場所・服装)は Claude を使わずに読む。文字数は本文から数える(ヘッダーの「文字数」は3割のページにしか無いため)。
- 作業日報(画面記録)の無い期間(DAILY_REPORT_START より前)は、そのページに書かれた「昨日のこと・今日の予定・気になったこと」を
  Claude で取り出す。日報のある期間は、予定と実績を日報の6節目で読めるので、ヘッダーだけにする。
- 本文そのものは送らない。取り出した短い箇条書きとヘッダーの値だけを送る。
"""

import datetime
import json
import os
import re

from src.claude_runner import run_claude
from src.morning_page import page_body

# 作業日報(画面記録)の最初の日。これより前のページだけ、本文から取り出す
DAILY_REPORT_START = datetime.date(2025, 12, 23)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CACHE_DIR = os.path.join("outputs", "morning_pages")
# 1ページの所要時間がこれを超えるときは、ヘッダーの書き間違い（日付をまたぐなど）として使わない
MAX_MINUTES = 240
# 終了時刻を書き忘れた(「8:57 ~ 9:( m)」のような)ページの所要時間。開始時刻だけ残し、終了は不明のままにする
MISSING_END_MINUTES = 30
MAX_ITEMS = 16
MAX_ITEM_CHARS = 400
MAX_BODY_CHARS = 14000
# 服装の欄の1段(「シャツ(Uniqlo U)」のような書いたままの値)の長さの上限
MAX_OUTFIT_CHARS = 100
OUTFIT_LAYERS = {"上": "top", "中": "middle", "下": "bottom"}

EXTRACT_PROMPT = """あなたは、本人が朝に書いた（話した）モーニングページ1枚から、書かれていることを整理するアシスタントです。
出力は次の3つの小見出しだけ。前置き・説明・コードブロックは書かない。日本語で、書かれていないことを推測で足さない。

### 昨日のこと
- 本文が振り返っている**前日の出来事**を、時間帯や場所が分かれば添えて **0〜8個** の箇条書きで。無ければ「- 記載なし」。

### 今日の予定
- 本文に書かれた**そのページの日にやるつもりのこと**を **0〜8個** の箇条書きで。無ければ「- 記載なし」。

### 気になったこと・考えたこと
- 気がかり・悩み・考えたことを **0〜5個**、各行の先頭に `[気がかり]` を付けて。無ければ「- 記載なし」。

# モーニングページの本文（{date}）

{body}
"""


def page_path(base_dir, date):
    """2023〜2025年のフォルダは月が英語名(Jan〜Dec)、2026年は数字。どちらもあれば存在する方を返す。"""
    candidates = [
        os.path.join(base_dir, f"{date:%Y}", month, f"{date:%d}.md")
        for month in (MONTHS[date.month - 1], f"{date:%m}")
    ]
    return next((path for path in candidates if os.path.exists(path)), candidates[0])


def parse_header(text):
    """ヘッダーの表から (開始, 終了, 所要分, 場所) を読む。読めない値は None / 空文字。
    「時間」の欄が `10:00 ~ 10:02(2 m)<br>10:10 ~ 10:50(40 m)` のように複数の区間なら、開始は最初の区間、終了は最後の区間、
    所要分は区間の合計(2+40=42)。読めない区間は無視する。
    終了時刻が書かれていない(書きかけの)区間は、所要分を MISSING_END_MINUTES とみなす(終了は不明のまま)。
    「25:23 ~ 25:48」のように24時を超えた時刻(深夜の続きの書き方)は、翌日の同じ時刻(01:23)として読む。
    どれかの区間が MAX_MINUTES を超えるときは、書き間違いとして所要分だけ使わない(時刻は残す)。"""
    started = ended = minutes = None
    cell = re.search(r"\|\s*時間\s*\|([^|\n]*)", text)
    spans = []
    for part in re.split(r"<br\s*/?>", cell.group(1)) if cell else []:
        match = re.match(r"\s*(\d{1,2}):(\d{2})\s*~\s*(?:(\d{1,2}):(\d{2}))?", part)
        if not match:
            continue
        sh, sm = int(match.group(1)), int(match.group(2))
        if sh >= 48 or sm >= 60:
            continue
        start = f"{sh % 24:02d}:{sm:02d}"
        if match.group(3) is None:
            spans.append((start, None, MISSING_END_MINUTES))
            continue
        eh, em = int(match.group(3)), int(match.group(4))
        if eh >= 48 or em >= 60:
            continue
        span = ((eh * 60 + em) - (sh * 60 + sm)) % 1440
        spans.append((start, f"{eh % 24:02d}:{em:02d}", span if span <= MAX_MINUTES else None))
    if spans:
        started, ended = spans[0][0], spans[-1][1]
        minutes = None if any(span[2] is None for span in spans) else sum(span[2] for span in spans)
    place = re.search(r"\|\s*場所\s*\|\s*([^|]*?)\s*\|", text)
    return started, ended, minutes, place.group(1).strip() if place else ""


def parse_outfit(text):
    """ヘッダーの表の「服装」を、上・中・下の段ごとに書いたままの値で読む。
    欄は `上:シャツ(Uniqlo U)<br>中:Tシャツ(WhitesVille)<br>下:デニム(白)` の形(コロンは全角でもよい)。
    括弧の中はブランドのことも色のこともあるので分けない。欄・段が無ければ空文字。"""
    outfit = {"top": "", "middle": "", "bottom": ""}
    cell = re.search(r"\|\s*服装\s*\|([^|\n]*)", text)
    for part in re.split(r"<br\s*/?>", cell.group(1)) if cell else []:
        match = re.match(r"\s*([上中下])\s*[:：]\s*(.*?)\s*$", part)
        if match and match.group(2):
            outfit[OUTFIT_LAYERS[match.group(1)]] = match.group(2)[:MAX_OUTFIT_CHARS]
    return outfit


def count_chars(text):
    """本文(URL だけの行を除く)の、空白を除いた文字数。本文が無ければ None。"""
    body = page_body(text, limit=10**7)
    return len(re.sub(r"\s+", "", body)) if body else None


def parse_extraction(response):
    """Claude の回答から (昨日のこと, 今日の予定, 気がかり) の箇条書きを取り出す。「記載なし」は除く。"""
    sections = {"yesterday": [], "plan": [], "notes": []}
    current = None
    for line in response.replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^#{2,4}\s*(.*)$", line)
        if heading:
            title = heading.group(1)
            current = "yesterday" if "昨日" in title else "plan" if "予定" in title else "notes" if re.search(r"気にな|考え|気がかり", title) else None
            continue
        bullet = re.match(r"^\s*[-*・]\s+(.*\S)\s*$", line)
        if current and bullet:
            text = re.sub(r"^[\[［]気がかり[\]］]\s*", "", bullet.group(1)).strip()
            if text and not re.fullmatch(r"記載なし。?", text):
                sections[current].append(text[:MAX_ITEM_CHARS])
    return {key: items[:MAX_ITEMS] for key, items in sections.items()}


def extract_page(date, text, model=None):
    """そのページの本文から、昨日のこと・今日の予定・気がかりを Claude で取り出す。本文が無ければ空。"""
    body = page_body(text, limit=MAX_BODY_CHARS)
    if not body:
        return {"yesterday": [], "plan": [], "notes": []}
    return parse_extraction(run_claude(EXTRACT_PROMPT.replace("{date}", date.isoformat()).replace("{body}", body), model=model))


def build_record(date, text, extraction=None):
    """dashboard へ送る1ページ分。extraction が None ならヘッダーだけ(extracted=False)。"""
    started, ended, minutes, place = parse_header(text)
    record = {
        "date": date.isoformat(), "startedAt": started, "endedAt": ended, "minutes": minutes, "place": place,
        "chars": count_chars(text), "outfit": parse_outfit(text),
        "yesterday": [], "plan": [], "notes": [], "extracted": extraction is not None,
    }
    if extraction is not None:
        record.update(extraction)
    return record


def cache_path(date, cache_dir=CACHE_DIR):
    return os.path.join(cache_dir, f"{date.isoformat()}.json")


def load_cached(date, cache_dir=CACHE_DIR):
    try:
        with open(cache_path(date, cache_dir), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_cached(record, cache_dir=CACHE_DIR):
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, f"{record['date']}.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)


def needs_extraction(date, header_only=False, extract_all=False):
    """Claude で取り出すページか。日報のある期間は、予定と実績を日報の6節目で読めるのでヘッダーだけ。"""
    return not header_only and (extract_all or date < DAILY_REPORT_START)


def make_record(date, base_dir, *, header_only=False, extract_all=False, force=False, model=None, cache_dir=CACHE_DIR):
    """1ページ分の記録を作る(取り出し済みのキャッシュがあれば、取り出しはやり直さない)。ページが無ければ None。"""
    path = page_path(base_dir, date)
    if not os.path.exists(path):
        return None
    want = needs_extraction(date, header_only, extract_all)
    cached = load_cached(date, cache_dir)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if cached and not force and cached["extracted"]:
        # 取り出し(Claude)の結果だけを使い回し、ヘッダーは毎回読み直す(あとで足した服装などを反映する)
        extraction = {key: cached[key] for key in ("yesterday", "plan", "notes")}
    elif want:
        extraction = extract_page(date, text, model=model)
    else:
        extraction = None
    record = build_record(date, text, extraction)
    save_cached(record, cache_dir)
    return record
