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
