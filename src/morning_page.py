"""Obsidian のモーニングページ（{MORNING_PAGE_DIR}/YYYY/MM/DD.md）から、日報に足す節を取り出す。

モーニングページは、朝に話した音声を文字にした【本文】と、それを整理した【サマリ】からなる。
日報には【サマリ】側の次の節だけを使う（【本文】は音声認識の誤りが多いので使わない）。

- D 日の日報には、D+1 日のページの「昨日の振り返り」と「気になること・考えたこと」（D 日の実績）
- D 日のページの「今日の予定」（D 日の予定。実績と比べるのに使う）

見出しは日によって「昨日（11/20・金）の振り返り」「昨日の振り返り」「今日の予定・作業内容」のように揺れるので、
`## ` の見出しをキーワードで見分ける。
"""

import datetime
import os
import re

from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
DIR_ENV = "MORNING_PAGE_DIR"
# 1つの節が長すぎるとプロンプトが膨らむので、この文字数で切る（ふだんは長くても6,000字程度）
MAX_SECTION_CHARS = 8000

RETRO_RE = re.compile(r"^昨日.*振り返り")
THOUGHTS_RE = re.compile(r"^(気になること|内省)")
# 「今日（10/8）の状況」「新居のこと・今日の予定」のように、予定の節の名前は揺れる
PLAN_RE = re.compile(r"^今日|今日の予定")
# 見出しの「（11/20・金）」「（9/6）」の日付
HEADING_DATE_RE = re.compile(r"[（(]\s*(\d{1,2})\s*/\s*(\d{1,2})")


class MorningContext:
    """日報の6節目を書くための材料。どれも見つからなければ None。"""

    def __init__(self, date, plan=None, retro=None, thoughts=None, notices=None):
        self.date = date
        self.plan = plan
        self.retro = retro
        self.thoughts = thoughts
        # 見つからなかった・使わなかった理由（画面に出す）
        self.notices = notices or []

    @property
    def empty(self):
        return self.plan is None and self.retro is None

    def source_line(self):
        """6節目の先頭に付ける、使ったページの説明（プログラムが付けるので、日付は正確）。"""
        next_day = self.date + datetime.timedelta(days=1)
        # 「11/21の振り返り」だと 11/21 を振り返ったように読めるので、どちらも対象日（D 日）についての話だと分かる書き方にする
        parts = []
        if self.plan is not None:
            parts.append(f"当日朝（{_short(self.date)}）の予定")
        if self.retro is not None:
            parts.append(f"翌朝（{_short(next_day)}）の振り返り")
        return "> モーニングページ: " + "・".join(parts)


def morning_page_dir():
    """.env か環境変数の MORNING_PAGE_DIR。未設定ならモーニングページは使わない（None）。"""
    load_dotenv(ENV_PATH)
    value = os.environ.get(DIR_ENV, "").strip()
    return os.path.expanduser(value) if value else None


def page_path(base_dir, date):
    return os.path.join(base_dir, f"{date:%Y}", f"{date:%m}", f"{date:%d}.md")


def level2_sections(text):
    """`## 見出し` ごとに (見出しの文字, 本文) を返す。本文は次の `#`・`##` の見出しの手前まで（`###` は含める）。"""
    sections = []
    title, body = None, []
    for line in text.replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^(#{1,2})(?!#)\s*(.*)$", line)
        if heading:
            if title is not None:
                sections.append((title, "\n".join(body).strip()))
            title, body = (heading.group(2).strip() if heading.group(1) == "##" else None), []
            continue
        if title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, "\n".join(body).strip()))
    return sections


def find_section(sections, pattern):
    """pattern に合う最初の節を (見出し, 本文) で返す。本文が空なら None。"""
    for title, body in sections:
        if pattern.search(title) and body:
            return title, _clip(body)
    return None


def heading_date_matches(title, date):
    """見出しに日付があれば、それが date と同じか。日付が無ければ確かめようがないので True。"""
    match = HEADING_DATE_RE.search(title)
    if not match:
        return True
    return (int(match.group(1)), int(match.group(2))) == (date.month, date.day)


def load_morning_context(date, base_dir):
    """date（D 日）の日報に使う、D 日の予定と D+1 日の振り返りを読む。"""
    next_day = date + datetime.timedelta(days=1)
    context = MorningContext(date)

    plan_page = _read(page_path(base_dir, date))
    if plan_page is None:
        context.notices.append(f"{_short(date)}のモーニングページがありません（予定は使いません）")
    else:
        found = find_section(level2_sections(plan_page), PLAN_RE)
        if found is None:
            context.notices.append(f"{_short(date)}のモーニングページに「今日の予定」の節がありません")
        elif not heading_date_matches(found[0], date):
            context.notices.append(f"{_short(date)}のページの予定の見出し（{found[0]}）の日付が違うので使いません")
        else:
            context.plan = found[1]

    retro_page = _read(page_path(base_dir, next_day))
    if retro_page is None:
        context.notices.append(f"{_short(next_day)}のモーニングページがありません（振り返りは使いません）")
    else:
        sections = level2_sections(retro_page)
        found = find_section(sections, RETRO_RE)
        if found is None:
            context.notices.append(f"{_short(next_day)}のモーニングページに「昨日の振り返り」の節がありません（サマリをまだ貼っていない？）")
        elif not heading_date_matches(found[0], date):
            # 前の日にページを書かなかったときなど、「昨日」が D 日でないことがある
            context.notices.append(f"{_short(next_day)}のページの振り返りの見出し（{found[0]}）が{_short(date)}ではないので使いません")
        else:
            context.retro = found[1]
            thoughts = find_section(sections, THOUGHTS_RE)
            context.thoughts = thoughts[1] if thoughts else None
    return context


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _clip(text):
    if len(text) <= MAX_SECTION_CHARS:
        return text
    return text[:MAX_SECTION_CHARS] + "\n（長いので以下省略）"


def _short(date):
    return f"{date.month}/{date.day}"
