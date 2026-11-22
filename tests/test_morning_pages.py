import argparse
import datetime
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import morning_pages
from src import morning_pages as mp

D = datetime.date

OLD_PAGE = """|   |   |
|---|---|
|時間|09:53 ~ 10:31(38 min)|
|場所|自宅（槻木）|
|モーニングページ|598日目|
|文字数||
> [!info] https://example.com/count

## 本文 :
昨日の22時くらいに帰ってきた。今日は洗濯物を干す。
[https://example.com/a](https://example.com/a)
ちょっと気になることがある。
"""


def write_page(base, date, text, month=None):
    folder = base / f"{date:%Y}" / (month or f"{date:%m}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{date:%d}.md").write_text(text, encoding="utf-8")


def test_page_path_uses_english_months_for_old_folders_and_numbers_for_2026(tmp_path):
    write_page(tmp_path, D(2024, 4, 15), OLD_PAGE, month="Apr")
    write_page(tmp_path, D(2026, 2, 3), OLD_PAGE)
    assert mp.page_path(str(tmp_path), D(2024, 4, 15)).endswith("2024/Apr/15.md")
    assert mp.page_path(str(tmp_path), D(2026, 2, 3)).endswith("2026/02/03.md")
    # どちらも無い日は、存在しないパスを返す（呼び出し側が exists で判定する）
    assert not os.path.exists(mp.page_path(str(tmp_path), D(2024, 4, 16)))


def test_header_reads_time_and_place_and_drops_outliers():
    assert mp.parse_header(OLD_PAGE) == ("09:53", "10:31", 38, "自宅（槻木）")
    # 日付をまたいだような長い所要時間は、書き間違いとして使わない（時刻は残す）
    assert mp.parse_header("|時間|23:50 ~ 18:10 (x)|\n|場所|ホテル|\n") == ("23:50", "18:10", None, "ホテル")
    # 2026年の「9:( m)」のような壊れた欄は、読めない
    assert mp.parse_header("|時間|8:57 ~ 9:( m)|\n") == (None, None, None, "")
    assert mp.parse_header("本文だけ") == (None, None, None, "")


def test_chars_count_the_body_without_url_lines_or_spaces():
    chars = mp.count_chars(OLD_PAGE)
    assert chars == len("昨日の22時くらいに帰ってきた。今日は洗濯物を干す。ちょっと気になることがある。")
    # 2023〜2025年の見出し「## 本文 :」でも、本文の前のヘッダーの表は数えない（上の assert が 40 字ちょうどであること）
    assert mp.count_chars("|時間|08:00 ~ 08:30|\n") is not None  # 見出しが無いページは全体を本文として数える


def test_extraction_drops_no_entry_marks_and_the_concern_prefix():
    response = "### 昨日のこと\n- 22時ごろに帰宅した\n- 記載なし\n\n### 今日の予定\n- 洗濯物を干す\n\n### 気になったこと・考えたこと\n- [気がかり] 木漏れ日のメタファー\n- 記載なし。\n"
    assert mp.parse_extraction(response) == {"yesterday": ["22時ごろに帰宅した"], "plan": ["洗濯物を干す"], "notes": ["木漏れ日のメタファー"]}
    assert mp.parse_extraction("### 昨日のこと\n- 記載なし\n") == {"yesterday": [], "plan": [], "notes": []}
    long = "あ" * 1000
    assert len(mp.parse_extraction(f"### 今日の予定\n- {long}\n")["plan"][0]) == mp.MAX_ITEM_CHARS


def test_only_pages_before_the_daily_reports_are_extracted():
    assert mp.needs_extraction(D(2025, 12, 22))
    assert not mp.needs_extraction(D(2025, 12, 23))
    assert not mp.needs_extraction(D(2024, 4, 15), header_only=True)
    assert mp.needs_extraction(D(2026, 3, 1), extract_all=True)


def test_make_record_extracts_once_and_reuses_the_saved_result(tmp_path, monkeypatch):
    base, cache = tmp_path / "pages", str(tmp_path / "cache")
    write_page(base, D(2024, 4, 15), OLD_PAGE, month="Apr")
    calls = []
    monkeypatch.setattr(mp, "run_claude", lambda prompt, model=None: calls.append(prompt) or "### 昨日のこと\n- 帰宅した\n### 今日の予定\n- 洗濯物を干す\n### 気になったこと・考えたこと\n- 記載なし\n")

    record = mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache)
    assert record == {"date": "2024-04-15", "startedAt": "09:53", "endedAt": "10:31", "minutes": 38, "place": "自宅（槻木）", "chars": mp.count_chars(OLD_PAGE),
                      "yesterday": ["帰宅した"], "plan": ["洗濯物を干す"], "notes": [], "extracted": True}
    assert len(calls) == 1 and "example.com" not in calls[0]

    assert mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache) == record
    assert len(calls) == 1  # 保存済みなので、Claude を呼ばない
    mp.make_record(D(2024, 4, 15), str(base), force=True, cache_dir=cache)
    assert len(calls) == 2
    assert mp.make_record(D(2024, 4, 16), str(base), cache_dir=cache) is None  # ページが無い日


def test_header_only_record_is_upgraded_when_extraction_is_wanted(tmp_path, monkeypatch):
    base, cache = tmp_path / "pages", str(tmp_path / "cache")
    write_page(base, D(2024, 4, 15), OLD_PAGE, month="Apr")
    monkeypatch.setattr(mp, "run_claude", lambda prompt, model=None: "### 今日の予定\n- 洗濯物を干す\n")
    assert mp.make_record(D(2024, 4, 15), str(base), header_only=True, cache_dir=cache)["extracted"] is False
    assert mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache)["extracted"] is True


def test_cli_date_selection():
    def args(**kw):
        values = dict(date=None, date_from=None, date_to=None)
        values.update(kw)
        return argparse.Namespace(**values)

    assert morning_pages.target_dates(args(date=["240415,240416", "240415"])) == [D(2024, 4, 15), D(2024, 4, 16)]
    dates = morning_pages.target_dates(args(date_from="240430", date_to="240502"))
    assert dates == [D(2024, 4, 30), D(2024, 5, 1), D(2024, 5, 2)]
    assert morning_pages.target_dates(args())[0] == morning_pages.FIRST_PAGE
    with pytest.raises(SystemExit):
        morning_pages.target_dates(args(date_from="240502", date_to="240430"))
