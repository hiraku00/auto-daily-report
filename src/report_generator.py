"""日報のプロンプトを作り、Claudeの回答を日報のMarkdownに仕上げる。"""

import datetime
import os
import re

from src.calendar_utils import get_todays_events
from src.log_digest import app_counts, build_digest, build_header, find_gaps, load_entries

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "report_prompt_template.md")

SECTION_HEADINGS = [
    "## 1. 本日のメイン作業",
    "## 2. アプリ使用状況",
    "## 3. 作業詳細",
    "## 4. 得られた知見･メモ",
    "## 5. 作業中だったファイル",
]


class ReportError(RuntimeError):
    """日報を作れない(ログが無い、回答の形式が違う、など)。"""


def _calendar_text(date_str):
    try:
        events = get_todays_events(datetime.datetime.strptime(date_str, "%Y-%m-%d"))
    except Exception as e:  # カレンダーが取れなくても日報は作る
        return f"（カレンダー取得エラー: {e}）"
    return "\n".join(f"- {start}: {summary}" for start, summary in events) or "（予定なし）"


def build_prompt(date_str, log_dir="logs", calendar_text=None):
    """(日報の見出し3行, Claudeに渡すプロンプト) を返す。"""
    entries = load_entries(date_str, log_dir)
    if not entries:
        raise ReportError(f"{date_str} の作業ログ（{log_dir}/daily_log_{date_str}.jsonl）がありません")

    header = build_header(date_str, entries)
    gaps = find_gaps(entries)
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    # str.format() はログ中の { } を置き換え項目と誤解するので使わない(#11 の KeyError)
    values = {
        "{date}": date_str,
        "{header}": header,
        "{gaps}": "\n".join(f"- {a}～{b}（{m // 60}時間{m % 60}分）" for a, b, m in gaps) or "（なし）",
        "{app_counts}": "\n".join(f"- {app}: {count}回" for app, count in app_counts(entries)),
        "{calendar_events}": calendar_text if calendar_text is not None else _calendar_text(date_str),
        "{digest}": build_digest(entries),
    }
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(key, value)
    return header, prompt


def extract_body(response, headings):
    """Claudeの回答から、最初の `## 1.` 以降の本文を取り出す。前置きとコードブロックの記号は除き、
    headings の節(番号で判定)がそろっていなければ ReportError にする。"""
    lines = [line for line in response.replace("\r\n", "\n").split("\n") if not line.strip().startswith("```")]
    start = next((i for i, line in enumerate(lines) if re.match(r"\s*##\s*1\.", line)), None)
    if start is None:
        raise ReportError(f"回答に「{headings[0]}」がありません")
    body = "\n".join(lines[start:]).strip()
    missing = [h for h in headings if h.split(".")[0] + "." not in body]
    if missing:
        raise ReportError(f"回答に次の節がありません: {', '.join(missing)}")
    return body


def finish_report(header, response):
    """Claudeの回答から本文(## 1. 〜 ## 5.)だけを取り出し、見出しを付けて日報にする。"""
    return f"{header}\n\n{extract_body(response, SECTION_HEADINGS)}\n"
