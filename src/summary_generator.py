"""週・月ごとのサマリを、期間内の日報(outputs/daily_report_*.md)から作る。

時間や回数の集計は dashboard の D1 で SQL を書けば出せるが、「何をして何が進んだか」の文章は
日報を読んでまとめ直す必要があるので、Claude(claude -p)に書かせる。数値はここで計算して渡し、
Claude には計算させない。
"""

import datetime
import os
import re

from src.report_generator import ReportError, extract_body

OUTPUT_DIR = "outputs"
SUMMARY_DIR = os.path.join(OUTPUT_DIR, "summaries")
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "summary_prompt_template.md")

SUMMARY_HEADINGS = ["## 1. 概要", "## 2. 主な取り組み", "## 3. 成果・進捗", "## 4. 得られた知見", "## 5. 次に向けて"]
# 月次は日数が多く、日報をすべて渡すとプロンプトが大きくなるので、作業の概要と知見の節だけを渡す
SECTIONS_BY_KIND = {
    "week": ("本日のメイン作業", "作業詳細", "得られた知見", "作業中だったファイル"),
    "month": ("本日のメイン作業", "得られた知見"),
}
WEEKDAYS = "月火水木金土日"


class Period:
    """サマリの対象期間(週は月曜〜日曜、月は1日〜末日)。"""

    def __init__(self, kind, start, end):
        self.kind, self.start, self.end = kind, start, end

    @classmethod
    def week_of(cls, day):
        start = day - datetime.timedelta(days=day.weekday())
        return cls("week", start, start + datetime.timedelta(days=6))

    @classmethod
    def month_of(cls, day):
        start = day.replace(day=1)
        next_month = (start + datetime.timedelta(days=32)).replace(day=1)
        return cls("month", start, next_month - datetime.timedelta(days=1))

    @classmethod
    def previous(cls, kind, today):
        """今日を含まない、直近の終わった週・月。"""
        if kind == "week":
            return cls.week_of(today - datetime.timedelta(days=7))
        return cls.month_of(today.replace(day=1) - datetime.timedelta(days=1))

    def days(self):
        return [self.start + datetime.timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    @property
    def label(self):
        return "週" if self.kind == "week" else "月"

    @property
    def name(self):
        if self.kind == "week":
            return f"{self.start.isocalendar()[0]}年 第{self.start.isocalendar()[1]}週"
        return f"{self.start.year}年{self.start.month}月"

    @property
    def range_text(self):
        return f"{self.start:%Y-%m-%d}〜{self.end:%Y-%m-%d}"

    @property
    def filename(self):
        if self.kind == "week":
            return f"weekly_{self.start:%Y-%m-%d}.md"
        return f"monthly_{self.start:%Y-%m}.md"


def load_reports(period, output_dir=OUTPUT_DIR):
    """期間内にある日報を {date: Markdown} で返す(無い日は含めない)。"""
    reports = {}
    for day in period.days():
        path = os.path.join(output_dir, f"daily_report_{day:%Y-%m-%d}.md")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                reports[day] = f.read()
    return reports


def split_sections(markdown):
    """`## N. 見出し` ごとに {見出し: 本文} へ分ける。"""
    sections = {}
    current = None
    for line in markdown.split("\n"):
        heading = re.match(r"##(?!#)\s*\d*\.?\s*(.+)", line)
        if heading:
            current = heading.group(1).strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def _minutes(text):
    match = re.search(r"(\d+(?:\.\d+)?)\s*時間\s*(?:(\d+)\s*分)?", text) or re.search(r"()(\d+)\s*分", text)
    if not match:
        return 0
    return round(float(match.group(1) or 0) * 60 + int(match.group(2) or 0))


def report_stats(markdown):
    """日報1件の (記録分, ログ欠落分, キャプチャ回数)。読めない値は0。"""
    recorded = re.search(r"記録期間[:：][^\n(（]*[(（]([^)）]*)[)）]", markdown)
    captures = re.search(r"キャプチャ回数\s*[:：]\s*(\d[\d,]*)", markdown)
    gap = 0
    for line in markdown.split("\n"):
        if line.startswith("|") and re.search(r"ログなし|記録なし|記録欠落|データ欠落|ギャップ", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            gap += _minutes(cells[-1]) if cells else 0
    return (
        _minutes(recorded.group(1)) if recorded else 0,
        gap,
        int(captures.group(1).replace(",", "")) if captures else 0,
    )


def _hours(minutes):
    return f"約{minutes // 60}時間{minutes % 60:02d}分"


def build_stats(period, reports):
    recorded = gap = captures = 0
    for markdown in reports.values():
        r, g, c = report_stats(markdown)
        recorded, gap, captures = recorded + r, gap + g, captures + c
    missing = [day for day in period.days() if day not in reports]
    lines = [
        f"- 日報のある日: {len(reports)}日 / {len(period.days())}日",
        f"- 記録時間の合計: {_hours(recorded)}（1日平均 {_hours(recorded // max(len(reports), 1))}）",
        f"- ログ欠落の合計: {_hours(gap)}",
        f"- キャプチャ回数の合計: {captures}回",
    ]
    if missing:
        lines.append("- 日報の無い日: " + "、".join(f"{d:%m/%d}" for d in missing))
    return "\n".join(lines), recorded, gap


def build_summary_prompt(period, reports):
    """(サマリの見出し, Claudeに渡すプロンプト) を返す。"""
    if not reports:
        raise ReportError(f"{period.range_text} の日報がありません")
    stats, recorded, gap = build_stats(period, reports)
    wanted = SECTIONS_BY_KIND[period.kind]
    blocks = []
    for day, markdown in sorted(reports.items()):
        sections = split_sections(markdown)
        # 日付を ##、節を ###、日報内の分類(###)を #### にして、見出しの階層が日付の下に収まるようにする
        parts = [
            f"### {title}\n" + re.sub(r"^###(?!#)", "####", body, flags=re.M)
            for title, body in sections.items()
            if any(w in title for w in wanted)
        ]
        blocks.append(f"## {day:%Y-%m-%d}（{WEEKDAYS[day.weekday()]}）\n\n" + "\n\n".join(parts))

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    values = {
        "{period_label}": period.label,
        "{period_name}": period.name,
        "{period_range}": period.range_text,
        "{stats}": stats,
        "{reports}": "\n\n".join(blocks),
    }
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(key, value)

    title = "週次サマリ" if period.kind == "week" else "月次サマリ"
    header = (
        f"# {title} {period.name}（{period.range_text}）\n"
        f"対象: 日報{len(reports)}日分 / 記録時間 {_hours(recorded)} / ログ欠落 {_hours(gap)}"
    )
    return header, prompt


def finish_summary(header, response):
    return f"{header}\n\n{extract_body(response, SUMMARY_HEADINGS)}\n"
