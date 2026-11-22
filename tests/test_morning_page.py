import argparse
import datetime
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import daily_report
from src.morning_page import level2_sections, load_morning_context
from src.reflection import SECTION_HEADING, append_reflection, build_reflection_prompt, extract_reflection, strip_reflection
from src.report_generator import ReportError

DATE = datetime.date(2026, 3, 10)

# 実物の書式（【本文】＋【サマリ】、見出しの揺れ）をまねた架空のページ
PLAN_PAGE = """---
created: 2026-03-10
---

| 時間 | 8:30 ~ 9:00 |
| --- | --- |

# 【本文】

えーと今日は図書館に行って、午後はブログを書こうかな。

# 【サマリ】

# 3月10日（火）おしゃべり記録

## 08:30 記録開始

- 音が少しうるさかった

## 昨日（3/9・月）の振り返り

- 前の日のこと

## 今日（3/10・火）の予定

- **図書館**で本を返す
- 午後に**ブログ**を書く

## 締めくくり

- 15分で終えた
"""

RETRO_PAGE = """# 【本文】

昨日は図書館に行って、昼はカレーで。

# 【サマリ】

## 昨日（3/10・火）の振り返り

### 午前

- 図書館で本を返した

### 昼

- カレーを食べた（※不確か）

## 気になること・考えたこと

- 自転車のタイヤの空気が少ない

## 今日（3/11・水）の予定

- 次の日の予定
"""


def write_page(base, date, text):
    folder = base / f"{date:%Y}" / f"{date:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{date:%d}.md").write_text(text, encoding="utf-8")


def test_level2_sections_stop_at_next_heading_and_keep_subheadings():
    sections = dict(level2_sections(RETRO_PAGE))
    assert sections["昨日（3/10・火）の振り返り"].startswith("### 午前")
    assert "カレー" in sections["昨日（3/10・火）の振り返り"]
    assert "自転車" not in sections["昨日（3/10・火）の振り返り"]
    # 【本文】の地の文は、どの節にも入らない
    assert all("昼はカレーで" not in body for body in sections.values())


def test_loads_plan_from_the_day_and_retro_from_the_next_morning(tmp_path):
    write_page(tmp_path, DATE, PLAN_PAGE)
    write_page(tmp_path, DATE + datetime.timedelta(days=1), RETRO_PAGE)
    context = load_morning_context(DATE, str(tmp_path))
    assert "図書館" in context.plan and "次の日の予定" not in context.plan
    assert "カレー" in context.retro
    assert "自転車" in context.thoughts
    assert context.notices == []
    assert context.source_line() == "> モーニングページ: 当日朝（3/10）の予定・翌朝（3/11）の振り返り"


def test_missing_next_morning_keeps_the_plan_and_says_why(tmp_path):
    write_page(tmp_path, DATE, PLAN_PAGE)
    context = load_morning_context(DATE, str(tmp_path))
    assert context.plan and context.retro is None and not context.empty
    assert any("3/11のモーニングページがありません" in notice for notice in context.notices)
    assert context.source_line() == "> モーニングページ: 当日朝（3/10）の予定"


def test_retro_for_another_day_is_not_used(tmp_path):
    # 前の日にページを書かず、「昨日」が D 日でないとき
    write_page(tmp_path, DATE + datetime.timedelta(days=1), RETRO_PAGE.replace("3/10・火", "3/8・日"))
    context = load_morning_context(DATE, str(tmp_path))
    assert context.retro is None and context.empty
    assert any("3/10ではない" in notice for notice in context.notices)


def test_headings_without_dates_are_accepted(tmp_path):
    write_page(tmp_path, DATE, "## 今日の予定・作業内容\n\n- 散歩\n")
    write_page(tmp_path, DATE + datetime.timedelta(days=1), "## 昨日の振り返り\n\n- 散歩した\n")
    context = load_morning_context(DATE, str(tmp_path))
    assert context.plan == "- 散歩" and context.retro == "- 散歩した"


REPORT = (
    "# 作業日報 26-03-10\n記録期間: 09:00~10:00(約1時間)\nキャプチャ回数: 60回\n\n"
    "## 1. 本日のメイン作業\n\n- ブログ\n\n## 2. アプリ使用状況\n\n- 略\n\n## 3. 作業詳細\n\n- 略\n\n"
    "## 4. 得られた知見･メモ\n\n- 略\n\n## 5. 作業中だったファイル\n\n- blog.md\n"
)


def context_with_both(tmp_path):
    write_page(tmp_path, DATE, PLAN_PAGE)
    write_page(tmp_path, DATE + datetime.timedelta(days=1), RETRO_PAGE)
    return load_morning_context(DATE, str(tmp_path))


def test_prompt_contains_report_without_old_section6_and_morning_text(tmp_path):
    context = context_with_both(tmp_path)
    old = append_reflection(REPORT, context, "### 予定と実績\n\n- 古い6節目")
    prompt = build_reflection_prompt("2026-03-10", old, context)
    assert "## 5. 作業中だったファイル" in prompt
    assert "古い6節目" not in prompt
    assert "図書館**で本を返す" in prompt and "カレー" in prompt
    assert "{" not in prompt.split("# 対象日のデータ")[1].replace("{date}", "")


def test_extract_reflection_drops_preamble_fences_and_rewritten_sections():
    response = "はい、書きます。\n```markdown\n## 6. 予定と振り返り\n\n### 予定と実績\n\n- 図書館 → 行った\n\n## 1. 本日のメイン作業\n\n- 書き直し\n```\n"
    assert extract_reflection(response) == "### 予定と実績\n\n- 図書館 → 行った"
    with pytest.raises(ReportError):
        extract_reflection("## 1. 本日のメイン作業\n- だけ")
    with pytest.raises(ReportError):
        extract_reflection("## 6. 予定と振り返り\n\n")


def test_append_replaces_existing_section6(tmp_path):
    context = context_with_both(tmp_path)
    once = append_reflection(REPORT, context, "- 1回目")
    twice = append_reflection(once, context, "- 2回目")
    assert twice.count(SECTION_HEADING) == 1
    assert "1回目" not in twice and twice.endswith("- 2回目\n")
    assert strip_reflection(twice) == REPORT
    assert "> モーニングページ: 当日朝（3/10）の予定・翌朝（3/11）の振り返り" in twice


def cli_args(**overrides):
    values = dict(date=None, date_from=None, date_to=None, model=None, force=False, dry_run=False,
                  no_sync=True, no_summary=True, no_morning=False, morning_only=False, raw_morning=False)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_morning_only_rewrites_only_section6(tmp_path, monkeypatch):
    pages = tmp_path / "pages"
    write_page(pages, DATE, PLAN_PAGE)
    write_page(pages, DATE + datetime.timedelta(days=1), RETRO_PAGE)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "daily_report_2026-03-10.md").write_text(REPORT, encoding="utf-8")
    monkeypatch.setattr(daily_report, "OUTPUT_DIR", str(outputs))
    monkeypatch.setattr(daily_report, "morning_page_dir", lambda: str(pages))
    prompts = []
    monkeypatch.setattr(daily_report, "run_claude", lambda prompt, model=None: prompts.append(prompt) or "## 6. 予定と振り返り\n\n- 図書館 → 行った\n")

    daily_report.add_morning_only(DATE, cli_args(morning_only=True))

    saved = (outputs / "daily_report_2026-03-10.md").read_text(encoding="utf-8")
    assert saved.startswith(REPORT.rstrip())
    assert saved.endswith("- 図書館 → 行った\n")
    assert len(prompts) == 1


def test_report_is_kept_when_section6_fails(tmp_path, monkeypatch):
    pages = tmp_path / "pages"
    pages.mkdir()  # モーニングページが1枚も無い
    outputs = tmp_path / "outputs"
    monkeypatch.setattr(daily_report, "OUTPUT_DIR", str(outputs))
    monkeypatch.setattr(daily_report, "morning_page_dir", lambda: str(pages))
    monkeypatch.setattr(daily_report, "build_prompt", lambda date: ("# 作業日報 26-03-10", "prompt"))
    monkeypatch.setattr(daily_report, "run_claude", lambda prompt, model=None: REPORT.split("\n\n", 1)[1])

    daily_report.make_report(DATE, cli_args())

    saved = (outputs / "daily_report_2026-03-10.md").read_text(encoding="utf-8")
    assert "## 5. 作業中だったファイル" in saved and SECTION_HEADING not in saved


def test_morning_only_does_not_block_on_existing_report(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("x", encoding="utf-8")
    assert daily_report.blocks_overwrite(str(path), cli_args())
    assert not daily_report.blocks_overwrite(str(path), cli_args(morning_only=True))


# 整理された節の無い古いページ（本文だけ。URL の行を含む）
OLD_PLAN_PAGE = """---
created: 2026-03-10
---

## 本文

昨日は遅くまで動画を見てしまった。今日は図書館に行って、午後はブログを書く。
[https://example.com/a](https://example.com/a)
https://example.com/b

【ToDo】
○今日
- ブログ
"""

OLD_RETRO_PAGE = """## 本文

昨日は図書館に行って、昼はカレー。ブログは書けなかった。
"""


def test_raw_mode_uses_the_body_when_there_are_no_sections(tmp_path):
    write_page(tmp_path, DATE, OLD_PLAN_PAGE)
    write_page(tmp_path, DATE + datetime.timedelta(days=1), OLD_RETRO_PAGE)
    # 既定（毎朝の実行）では本文を使わない
    assert load_morning_context(DATE, str(tmp_path)).empty
    context = load_morning_context(DATE, str(tmp_path), raw=True)
    assert context.plan_raw and context.retro_raw
    assert context.plan.startswith("昨日は遅くまで") and "【ToDo】" in context.plan
    assert "example.com" not in context.plan and "created" not in context.plan
    assert context.retro == "昨日は図書館に行って、昼はカレー。ブログは書けなかった。"
    assert context.source_line() == "> モーニングページ: 当日朝（3/10）の本文・翌朝（3/11）の本文から"
    prompt = build_reflection_prompt("2026-03-10", REPORT, context)
    assert "この日のモーニングページは整理されていない" in prompt
    assert "（本文）\n\n昨日は図書館に行って" in prompt


def test_raw_mode_still_prefers_organized_sections(tmp_path):
    write_page(tmp_path, DATE, PLAN_PAGE)
    write_page(tmp_path, DATE + datetime.timedelta(days=1), OLD_RETRO_PAGE)
    context = load_morning_context(DATE, str(tmp_path), raw=True)
    assert not context.plan_raw and "図書館**で本を返す" in context.plan
    assert context.retro_raw
    assert context.source_line() == "> モーニングページ: 当日朝（3/10）の予定・翌朝（3/11）の本文から"


def test_prompt_has_no_raw_note_for_organized_pages(tmp_path):
    prompt = build_reflection_prompt("2026-03-10", REPORT, context_with_both(tmp_path))
    assert "整理されていない" not in prompt and "{raw_note}" not in prompt
