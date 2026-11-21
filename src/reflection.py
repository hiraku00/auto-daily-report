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
# 本文から読んだ日（--raw-morning）だけ、プロンプトの {raw_note} に入れる注意
RAW_NOTE = """# 追加の注意（この日のモーニングページは整理されていない）

- 下の「対象日の予定」「翌朝の振り返り」のうち「（本文）」と付いたものは、整理された節ではなく、本人がその朝に書いた（または話した）**本文そのもの**です。
- 対象日の朝の本文には前日の振り返りも混ざっています。予定として使うのは、**対象日にやるつもりのこと**（「今日は〜」「【ToDo】の ○今日」など）だけです。
- 翌朝の本文から振り返りとして使うのは、**対象日（その朝から見た「昨日」）のこと**（「昨日は〜」「【ToDo】の ○昨日 の『済』」など）だけです。翌日の予定や雑談は使いません。
- 本文に予定がはっきり書かれていなければ、「予定と実績」は書かれている分だけでよい。毎日の決まった作業（Anki など）を「予定外」にしない。
- 貼り付けたメモ・設定手順・引用などは無視します。

"""
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
        "{raw_note}": RAW_NOTE if context.raw else "",
        "{plan}": _labeled(context.plan, context.plan_raw),
        "{retro}": _labeled(context.retro, context.retro_raw),
        "{thoughts}": context.thoughts or "（なし）",
    }
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(key, value)
    return prompt


def _labeled(text, raw):
    if not text:
        return "（なし）"
    return f"（本文）\n\n{text}" if raw else text


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
