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
    # 終了時刻を書き忘れたページは、開始時刻だけ読み、所要分は30分とみなす
    assert mp.parse_header("|時間|8:57 ~ 9:( m)|\n") == ("08:57", None, 30, "")
    assert mp.parse_header("|時間|8:57 ~ |\n") == ("08:57", None, 30, "")
    assert mp.parse_header("本文だけ") == (None, None, None, "")
    # 24時を超えた時刻は翌日の同じ時刻として読む(25:23 → 01:23)。所要分は書かれた時刻の差
    assert mp.parse_header("| 時間 | 25:23 ~ 25:48(23 min) |") == ("01:23", "01:48", 25, "")
    assert mp.parse_header("|時間|25:50 ~ 26:13(23 min)|") == ("01:50", "02:13", 23, "")
    assert mp.parse_header("|時間|25:10 ~ 25:( min)|") == ("01:10", None, 30, "")
    assert mp.parse_header("|時間|23:50 ~ 24:10(20 min)|") == ("23:50", "00:10", 20, "")
    # 複数の区間は、最初の開始・最後の終了・所要分の合計（2+40=42）。読めない区間は無視する
    assert mp.parse_header("| 時間 | 10:00 ~ 10:02(2 m)<br>10:10 ~ 10:50(40 m) |\n| 場所 | Focus3 |\n") == ("10:00", "10:50", 42, "Focus3")
    assert mp.parse_header("|時間|15:35 ~ 15:50(15 min) <br>16:06 ~ 16:21(15 min)|") == ("15:35", "16:21", 30, "")
    assert mp.parse_header("| 時間 | 10:36 ~ 10:56(20 m)<br>11: ~ 11:( m) |") == ("10:36", "10:56", 20, "")


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


EMPTY_LAYER = {"item": "", "brand": ""}


def test_outfit_splits_each_layer_into_item_and_brand():
    page = "| 場所 | Sky Lounge2 |\n| 服装 | 上:ストライプシャツ (UNIQLO)<br>中:Tシャツ (WHITESVILLE)<br>下:白デニム (UNIQLO) |\n| 文字数 | |\n"
    assert mp.parse_outfit(page) == {
        "top": {"item": "ストライプシャツ", "brand": "UNIQLO"},
        "middle": {"item": "Tシャツ", "brand": "WHITESVILLE"},
        "bottom": {"item": "白デニム", "brand": "UNIQLO"},
    }
    # 全角のコロン・括弧、括弧の無い値、順不同、欠けた段・空の段
    assert mp.parse_outfit("|服装|下：短パン<br/>上: Tシャツ（Uniqlo U）<br>中:|") == {
        "top": {"item": "Tシャツ", "brand": "Uniqlo U"}, "middle": EMPTY_LAYER, "bottom": {"item": "短パン", "brand": ""},
    }
    # 着ていない段: 「-」だけ・空欄・空の括弧は、書かなかった段と同じく空
    for middle in ["中:- (-)", "中:- ()", "中:－（ー）", "中:-", "中:", "中: ( )", "中:（）"]:
        outfit = mp.parse_outfit(f"| 服装 | 上:白シャツ (MB)<br>{middle}<br>下:カーゴショーツ (UNIQLO) |")
        assert outfit == {"top": {"item": "白シャツ", "brand": "MB"}, "middle": EMPTY_LAYER, "bottom": {"item": "カーゴショーツ", "brand": "UNIQLO"}}, middle
    # 品名の中のハイフンは消さない
    assert mp.parse_outfit("|服装|上:T-シャツ (-)|")["top"] == {"item": "T-シャツ", "brand": ""}
    assert mp.parse_outfit(OLD_PAGE) == {"top": EMPTY_LAYER, "middle": EMPTY_LAYER, "bottom": EMPTY_LAYER}
    assert mp.parse_outfit("|服装|上:" + "あ" * 150 + "|")["top"]["item"] == "あ" * mp.MAX_OUTFIT_CHARS


def test_make_record_rereads_the_header_but_keeps_the_extraction(tmp_path, monkeypatch):
    base, cache = tmp_path / "pages", str(tmp_path / "cache")
    write_page(base, D(2024, 4, 15), OLD_PAGE, month="Apr")
    monkeypatch.setattr(mp, "run_claude", lambda prompt, model=None: "### 今日の予定\n- 洗濯物を干す\n")
    assert mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache)["outfit"]["top"] == EMPTY_LAYER
    write_page(base, D(2024, 4, 15), OLD_PAGE.replace("|文字数||", "|服装|上:シャツ (UNIQLO)|\n|文字数||"), month="Apr")
    monkeypatch.setattr(mp, "run_claude", lambda prompt, model=None: pytest.fail("取り出し済みなので呼ばない"))
    record = mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache)
    assert record["outfit"]["top"] == {"item": "シャツ", "brand": "UNIQLO"} and record["plan"] == ["洗濯物を干す"]
    # ヘッダーだけの記録も、ページを書き足せば読み直す
    write_page(base, D(2026, 2, 3), "|時間|8:00 ~ 8:30|\n")
    assert mp.make_record(D(2026, 2, 3), str(base), cache_dir=cache)["outfit"]["bottom"] == EMPTY_LAYER
    write_page(base, D(2026, 2, 3), "|時間|8:00 ~ 8:30|\n|服装|下:白デニム (UNIQLO)|\n")
    assert mp.make_record(D(2026, 2, 3), str(base), cache_dir=cache)["outfit"]["bottom"] == {"item": "白デニム", "brand": "UNIQLO"}


def test_make_record_extracts_once_and_reuses_the_saved_result(tmp_path, monkeypatch):
    base, cache = tmp_path / "pages", str(tmp_path / "cache")
    write_page(base, D(2024, 4, 15), OLD_PAGE, month="Apr")
    calls = []
    monkeypatch.setattr(mp, "run_claude", lambda prompt, model=None: calls.append(prompt) or "### 昨日のこと\n- 帰宅した\n### 今日の予定\n- 洗濯物を干す\n### 気になったこと・考えたこと\n- 記載なし\n")

    record = mp.make_record(D(2024, 4, 15), str(base), cache_dir=cache)
    assert record == {"date": "2024-04-15", "startedAt": "09:53", "endedAt": "10:31", "minutes": 38, "place": "自宅（槻木）", "chars": mp.count_chars(OLD_PAGE),
                      "outfit": {"top": EMPTY_LAYER, "middle": EMPTY_LAYER, "bottom": EMPTY_LAYER}, "yesterday": ["帰宅した"], "plan": ["洗濯物を干す"], "notes": [], "extracted": True}
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
