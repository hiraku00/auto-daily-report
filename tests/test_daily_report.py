import argparse
import datetime
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import daily_report
from daily_report import target_dates


def args(date=None, date_from=None, date_to=None):
    return argparse.Namespace(date=date, date_from=date_from, date_to=date_to)


def test_no_date_targets_yesterday():
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    assert target_dates(args()) == [yesterday]


def test_single_date():
    assert target_dates(args(date=["261103"])) == [datetime.date(2026, 11, 3)]


def test_multiple_dates_are_sorted_and_deduplicated():
    dates = target_dates(args(date=["261107", "261103,261105", "261103"]))
    assert dates == [datetime.date(2026, 11, 3), datetime.date(2026, 11, 5), datetime.date(2026, 11, 7)]


def test_date_range_includes_both_ends():
    dates = target_dates(args(date_from="261030", date_to="261102"))
    assert dates[0] == datetime.date(2026, 10, 30)
    assert dates[-1] == datetime.date(2026, 11, 2)
    assert len(dates) == 4


@pytest.mark.parametrize(
    "bad",
    [
        args(date=["261103"], date_from="261101"),
        args(date_to="261103"),
        args(date_from="261105", date_to="261103"),
        args(date=["2026-11-03"]),
    ],
)
def test_invalid_combinations_exit(bad):
    with pytest.raises(SystemExit):
        target_dates(bad)


def test_multiple_dates_continue_after_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(daily_report, "OUTPUT_DIR", str(tmp_path))
    (tmp_path / "daily_report_2026-11-05.md").write_text("既存", encoding="utf-8")
    made = []

    def fake_make_report(date, _args):
        if date == datetime.date(2026, 11, 3):
            raise daily_report.ReportError("ログがありません")
        made.append(date)

    monkeypatch.setattr(daily_report, "make_report", fake_make_report)
    monkeypatch.setattr(sys, "argv", ["daily_report.py", "--date", "261107", "261105", "261103"])

    with pytest.raises(SystemExit) as e:
        daily_report.main()

    assert e.value.code == 1
    assert made == [datetime.date(2026, 11, 7)]
    out = capsys.readouterr().out
    assert "2026-11-03〜2026-11-07（3 日）: 作成 1 件、既存のため省略 1 件、失敗 1 件" in out


def write_page(base, date, time_cell):
    folder = base / f"{date:%Y}" / f"{date:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{date:%d}.md").write_text(f"| 時間 | {time_cell} |\n| 場所 | 自宅 |\n\n本文です。\n", encoding="utf-8")


def test_record_morning_pages_records_only_next_morning(tmp_path, monkeypatch):
    base = tmp_path / "pages"
    cache = tmp_path / "cache"
    day = datetime.date(2026, 11, 22)
    write_page(base, day, "08:51 ~ 09:41")
    write_page(base, day + datetime.timedelta(days=1), "08:00 ~ 08:30")
    real_make_record = daily_report.make_record
    monkeypatch.setattr(daily_report, "make_record", lambda *a, **k: real_make_record(*a, cache_dir=str(cache), **k))
    sent = []
    monkeypatch.setattr(daily_report, "send_morning_pages", lambda records: sent.extend(records) or {})
    monkeypatch.setattr(daily_report, "print_summary", lambda *_a, **_k: None)

    daily_report.record_morning_pages(day, str(base), argparse.Namespace(model=None, no_sync=False))

    assert [(r["date"], r["minutes"], r["extracted"]) for r in sent] == [("2026-11-23", 30, False)]


def test_record_morning_pages_rereads_header_after_page_is_edited(tmp_path, monkeypatch):
    base = tmp_path / "pages"
    cache = tmp_path / "cache"
    day = datetime.date(2026, 11, 22)
    real_make_record = daily_report.make_record
    monkeypatch.setattr(daily_report, "make_record", lambda *a, **k: real_make_record(*a, cache_dir=str(cache), **k))
    sent = []
    monkeypatch.setattr(daily_report, "send_morning_pages", lambda records: sent.extend(records) or {})
    monkeypatch.setattr(daily_report, "print_summary", lambda *_a, **_k: None)
    opts = argparse.Namespace(model=None, no_sync=False)

    next_morning = day + datetime.timedelta(days=1)
    write_page(base, next_morning, "08:51 ~")
    daily_report.record_morning_pages(day, str(base), opts)
    write_page(base, next_morning, "08:51 ~ 09:41")
    daily_report.record_morning_pages(day, str(base), opts)

    assert [r["minutes"] for r in sent] == [30, 50]


def test_record_morning_pages_skips_future_and_missing_pages_without_sync(tmp_path, monkeypatch):
    base = tmp_path / "pages"
    today = datetime.date.today()
    write_page(base, today, "08:00 ~ 08:20")
    yesterday = today - datetime.timedelta(days=1)
    real_make_record = daily_report.make_record
    asked = []

    def spy(day, *a, **k):
        asked.append(day)
        return real_make_record(day, *a, cache_dir=str(tmp_path / "cache"), **k)

    monkeypatch.setattr(daily_report, "make_record", spy)
    monkeypatch.setattr(daily_report, "send_morning_pages", lambda records: pytest.fail("--no-sync なのに送った"))

    daily_report.record_morning_pages(today, str(base), argparse.Namespace(model=None, no_sync=True))
    daily_report.record_morning_pages(yesterday, str(base), argparse.Namespace(model=None, no_sync=True))
    daily_report.record_morning_pages(today - datetime.timedelta(days=5), str(base), argparse.Namespace(model=None, no_sync=True))

    assert asked == [today, today - datetime.timedelta(days=4)]
    assert (tmp_path / "cache" / f"{today.isoformat()}.json").exists()
