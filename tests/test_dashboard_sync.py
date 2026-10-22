import io
import json
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import dashboard_sync
from src.dashboard_sync import DashboardSyncError, reparse_all, report_files, send_reports


@pytest.fixture
def env(monkeypatch, tmp_path):
    # 手元の .env を読まないようにして、テスト用の値だけを使う
    monkeypatch.setattr(dashboard_sync, "ENV_PATH", str(tmp_path / "missing.env"))
    monkeypatch.setenv("DASHBOARD_API_URL", "https://dashboard.example.test/")
    monkeypatch.setenv("DASHBOARD_ACCESS_CLIENT_ID", "CF-Access-Client-Id: test-id")
    monkeypatch.setenv("DASHBOARD_ACCESS_CLIENT_SECRET", "test-secret")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(responses, calls):
    def urlopen(request, timeout, context):
        calls.append(request)
        return FakeResponse(responses.pop(0).encode("utf-8"))
    return urlopen


def write_reports(tmp_path, count):
    for day in range(1, count + 1):
        (tmp_path / f"daily_report_2026-01-{day:02d}.md").write_text(f"# 作業日報 26-01-{day:02d}\n", encoding="utf-8")
    (tmp_path / "daily_report_prompt.txt").write_text("x", encoding="utf-8")
    (tmp_path / "memo.md").write_text("x", encoding="utf-8")


def test_report_files_lists_only_daily_reports_in_date_order(tmp_path):
    write_reports(tmp_path, 3)
    files = report_files(str(tmp_path))
    assert [d for d, _ in files] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert [d for d, _ in report_files(str(tmp_path), dates=["2026-01-02"])] == ["2026-01-02"]
    with pytest.raises(DashboardSyncError, match="2026-02-01"):
        report_files(str(tmp_path), dates=["2026-02-01"])


def test_send_reports_batches_by_20_and_sums_results(env, monkeypatch, tmp_path):
    write_reports(tmp_path, 25)
    calls = []
    responses = [
        json.dumps({"created": 19, "updated": 0, "skipped": 1, "errors": 0, "results": [{"date": "2026-01-01", "status": "skipped"}]}),
        json.dumps({"created": 4, "updated": 1, "skipped": 0, "errors": 0, "results": [{"date": "2026-01-25", "status": "updated"}]}),
    ]
    monkeypatch.setattr(dashboard_sync, "urlopen", fake_urlopen(responses, calls))

    totals = send_reports(report_files(str(tmp_path)))

    assert totals["created"] == 23 and totals["updated"] == 1 and totals["skipped"] == 1 and totals["errors"] == 0
    assert len(totals["results"]) == 2
    assert [len(json.loads(c.data)["reports"]) for c in calls] == [20, 5]
    first = calls[0]
    assert first.full_url == "https://dashboard.example.test/api/daily-reports"
    assert first.get_header("Cf-access-client-id") == "test-id"  # 「ヘッダー名: 値」の形でも値だけを送る
    assert first.get_header("Cf-access-client-secret") == "test-secret"
    assert json.loads(first.data)["reports"][0] == {"date": "2026-01-01", "markdown": "# 作業日報 26-01-01\n"}


def test_send_reports_requires_settings(env, monkeypatch):
    monkeypatch.delenv("DASHBOARD_ACCESS_CLIENT_SECRET")
    with pytest.raises(DashboardSyncError, match="DASHBOARD_ACCESS_CLIENT_SECRET"):
        send_reports([])


def test_non_json_response_points_at_access(env, monkeypatch, tmp_path):
    write_reports(tmp_path, 1)
    monkeypatch.setattr(dashboard_sync, "urlopen", fake_urlopen(["<html>Sign in</html>"], []))
    with pytest.raises(DashboardSyncError, match="service token"):
        send_reports(report_files(str(tmp_path)))


def test_reparse_all_repeats_until_nothing_remains(env, monkeypatch):
    calls = []
    responses = [json.dumps({"reparsed": 20, "remaining": 5}), json.dumps({"reparsed": 5, "remaining": 0})]
    monkeypatch.setattr(dashboard_sync, "urlopen", fake_urlopen(responses, calls))
    assert reparse_all() == 25
    assert [c.full_url for c in calls] == ["https://dashboard.example.test/api/daily-reports/reparse"] * 2
