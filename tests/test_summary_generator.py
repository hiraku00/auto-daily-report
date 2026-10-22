import datetime
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.report_generator import ReportError
from src.summary_generator import Period, build_summary_prompt, due_periods, finish_summary, load_reports, report_stats, split_sections, summary_files

D = datetime.date

REPORT = """# 作業日報 26-10-13
記録期間: 08:00~18:00(約10時間00分)
キャプチャ回数: 500回

## 1. 本日のメイン作業

### 1.英語学習
- Ankiで復習

## 2. アプリ使用状況

| アプリ/ツール | 使用回数 | 主な用途 |
|---|---|---|
| Brave | 300+ | 動画 |

## 3. 作業詳細

| 時間帯 | 作業内容 | 所要時間 |
|---|---|---|
| 08:00～09:00 | 英語学習 | 1時間 |
| 09:00～10:30 | （ログなし：記録欠落） | 1時間30分 |

## 4. 得られた知見･メモ

- 例文は声に出すと覚えやすい

## 5. 作業中だったファイル

- anki
"""


def test_periods_are_monday_to_sunday_and_whole_months():
    week = Period.week_of(D(2026, 10, 15))
    assert (week.start, week.end, week.filename) == (D(2026, 10, 12), D(2026, 10, 18), "weekly_2026-10-12.md")
    assert week.name == "2026年 第42週"
    month = Period.month_of(D(2026, 2, 10))
    assert (month.start, month.end, month.filename) == (D(2026, 2, 1), D(2026, 2, 28), "monthly_2026-02.md")
    # 今日を含まない、直近の終わった週・月
    assert Period.previous("week", D(2026, 10, 22)).start == D(2026, 10, 12)
    assert Period.previous("month", D(2026, 1, 5)).start == D(2025, 12, 1)


def test_report_stats_reads_header_and_gap_rows():
    assert report_stats(REPORT) == (600, 90, 500)
    assert report_stats("中身のない日報") == (0, 0, 0)


def test_split_sections_keeps_titles_without_numbers():
    sections = split_sections(REPORT)
    assert list(sections) == ["本日のメイン作業", "アプリ使用状況", "作業詳細", "得られた知見･メモ", "作業中だったファイル"]
    assert sections["得られた知見･メモ"] == "- 例文は声に出すと覚えやすい"


def write(tmp_path, day, text=REPORT):
    (tmp_path / f"daily_report_{day:%Y-%m-%d}.md").write_text(text, encoding="utf-8")


def test_weekly_prompt_has_stats_missing_days_and_selected_sections(tmp_path):
    write(tmp_path, D(2026, 10, 13))
    write(tmp_path, D(2026, 10, 14))
    write(tmp_path, D(2026, 10, 20))  # 期間外
    period = Period.week_of(D(2026, 10, 13))
    reports = load_reports(period, str(tmp_path))
    header, prompt = build_summary_prompt(period, reports)

    assert header == "# 週次サマリ 2026年 第42週（2026-10-12〜2026-10-18）\n対象: 日報2日分 / 記録時間 約20時間00分 / ログ欠落 約3時間00分"
    assert "- 日報のある日: 2日 / 7日" in prompt
    assert "- 日報の無い日: 10/12、10/15、10/16、10/17、10/18" in prompt
    assert "## 2026-10-13（火）" in prompt
    assert "#### 1.英語学習" in prompt  # 日報内の分類は日付・節より下の階層にする
    assert "### 作業詳細" in prompt and "| Brave | 300+ |" not in prompt  # アプリ使用状況は渡さない
    assert "{" not in prompt.split("# 期間の集計")[0]


def test_monthly_prompt_includes_only_overview_and_insights(tmp_path):
    write(tmp_path, D(2026, 10, 13))
    period = Period.month_of(D(2026, 10, 1))
    _, prompt = build_summary_prompt(period, load_reports(period, str(tmp_path)))
    assert "### 本日のメイン作業" in prompt and "### 得られた知見･メモ" in prompt
    assert "### 作業詳細" not in prompt


def test_build_summary_prompt_without_reports_raises():
    with pytest.raises(ReportError):
        build_summary_prompt(Period.week_of(D(2026, 1, 1)), {})


def test_finish_summary_requires_all_sections():
    body = "\n".join(["## 1. 概要", "文", "## 2. 主な取り組み", "## 3. 成果・進捗", "## 4. 得られた知見", "## 5. 次に向けて", "- 続き"])
    assert finish_summary("# 週次サマリ", f"まとめます。\n```\n{body}\n```") == f"# 週次サマリ\n\n{body}\n"
    with pytest.raises(ReportError):
        finish_summary("# h", body.split("## 5.")[0])


def test_period_round_trips_through_its_filename(tmp_path):
    for period in (Period.week_of(D(2026, 10, 15)), Period.month_of(D(2026, 2, 3))):
        restored = Period.from_filename(period.filename)
        assert (restored.kind, restored.start, restored.end) == (period.kind, period.start, period.end)
    assert Period.from_filename("weekly_2026-10-13.md") is None  # 月曜でない
    assert Period.from_filename("memo.md") is None

    (tmp_path / "monthly_2026-09.md").write_text("x", encoding="utf-8")
    (tmp_path / "weekly_2026-10-12.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    assert [(p.kind, p.start) for p, _ in summary_files(str(tmp_path))] == [("month", D(2026, 9, 1)), ("week", D(2026, 10, 12))]


def test_due_periods_follow_sundays_and_month_ends_and_catch_up_once(tmp_path):
    reports, summaries = tmp_path / "outputs", tmp_path / "summaries"
    reports.mkdir()
    summaries.mkdir()
    for day in (D(2026, 9, 28), D(2026, 9, 30), D(2026, 10, 4), D(2026, 10, 7)):
        write(reports, day)

    def due(day):
        return [(p.kind, p.start) for p in due_periods(day, str(reports), str(summaries))]

    # 月末(水曜): その月と、直前の終わった週(日報が無いので対象外)
    assert due(D(2026, 9, 30)) == [("month", D(2026, 9, 1))]
    # 日曜: その週。9月のサマリはまだ無いので一緒に作る
    assert due(D(2026, 10, 4)) == [("week", D(2026, 9, 28)), ("month", D(2026, 9, 1))]
    # 作った後は対象にならない。日曜を作り忘れても、翌週の日報で直前の週が対象になる
    (summaries / "monthly_2026-09.md").write_text("x", encoding="utf-8")
    assert due(D(2026, 10, 7)) == [("week", D(2026, 9, 28))]
    (summaries / "weekly_2026-09-28.md").write_text("x", encoding="utf-8")
    assert due(D(2026, 10, 7)) == []
