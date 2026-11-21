"""日報の6節目「予定と振り返り」を、モーニングページから書き足す（段2）。

段1（report_generator）が画面ログから書いた1〜5節はそのまま残し、できた日報とモーニングページを
Claude に渡して6節目だけを書かせ、日報の末尾に付ける。6節目だけを後から足したり書き直したりできるので、
朝のモーニングページを整理し終える前に日報を作っても、あとで `--morning-only` で追記できる。
"""

import os
import re

from src.report_generator import ReportError

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "morning_prompt_template.md")
SECTION_HEADING = "## 6. 予定と振り返り"
SECTION_START_RE = re.compile(r"^\s*##\s*6\s*[.．]")


def strip_reflection(report):
    """日報から6節目（`## 6.` 以降）を除いた本文を返す。作り直すときに、古い6節目を残さないため。"""
    lines = report.replace("\r\n", "\n").split("\n")
    end = next((i for i, line in enumerate(lines) if SECTION_START_RE.match(line)), len(lines))
    return "\n".join(lines[:end]).rstrip() + "\n"


def build_reflection_prompt(date_str, report, context):
    """段2のプロンプト。report は6節目を除いた日報、context は MorningContext。"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    # 本文に { } が入ることがあるので、str.format() は使わない（report_generator と同じ）
    values = {
        "{date}": date_str,
        "{report}": strip_reflection(report).strip(),
        "{plan}": context.plan or "（なし）",
        "{retro}": context.retro or "（なし）",
        "{thoughts}": context.thoughts or "（なし）",
    }
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(key, value)
    return prompt


def extract_reflection(response):
    """Claude の回答から `## 6.` 以降を取り出す。前置きとコードブロックの記号は除く。"""
    lines = [line for line in response.replace("\r\n", "\n").split("\n") if not line.strip().startswith("```")]
    start = next((i for i, line in enumerate(lines) if SECTION_START_RE.match(line)), None)
    if start is None:
        raise ReportError(f"回答に「{SECTION_HEADING}」がありません")
    body = "\n".join(lines[start + 1 :]).strip()
    # 1〜5節を書き直して付けてきたときは、6節目の後ろに続く分を捨てる
    later = re.search(r"^\s*##\s*[1-5]\s*[.．]", body, flags=re.MULTILINE)
    if later:
        body = body[: later.start()].strip()
    if not body:
        raise ReportError(f"回答の「{SECTION_HEADING}」が空です")
    return body


def append_reflection(report, context, body):
    """6節目を除いた日報の末尾に、使ったページの説明と6節目を付ける。"""
    return f"{strip_reflection(report).rstrip()}\n\n{SECTION_HEADING}\n\n{context.source_line()}\n\n{body}\n"
