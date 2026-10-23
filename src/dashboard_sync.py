"""outputs/ の日報と、週・月のサマリを dashboard（Cloudflare Workers + D1）へ送る。

送るのは日報の Markdown だけで、作業ログ（logs/*.jsonl）は送らない。
dashboard 側が本文の sha256 で変更を判定し、同じ内容なら何も書かずに skipped を返すので、
こちらは送信の状態を持たず、何度送り直してもよい。
"""

import json
import os
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv

OUTPUT_DIR = "outputs"
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
# dashboard 側の上限（1リクエスト20件）に合わせる
BATCH_SIZE = 20
REPORT_FILE_RE = re.compile(r"^daily_report_(\d{4}-\d{2}-\d{2})\.md$")
# 再解析は1回で最大20件ずつ進むので、1,000日分あっても足りる回数で打ち切る
MAX_REPARSE_ROUNDS = 60


class DashboardSyncError(RuntimeError):
    """設定が無い、通信に失敗した、応答が不正だった。"""


def report_files(output_dir=OUTPUT_DIR, dates=None):
    """outputs/ にある日報を (日付, パス) の日付順で返す。dates を渡すとその日付だけ。"""
    if not os.path.isdir(output_dir):
        return []
    found = {}
    for name in os.listdir(output_dir):
        match = REPORT_FILE_RE.match(name)
        if match:
            found[match.group(1)] = os.path.join(output_dir, name)
    if dates is not None:
        missing = sorted(set(dates) - set(found))
        if missing:
            raise DashboardSyncError(f"日報がありません: {', '.join(missing)}")
        found = {d: found[d] for d in dates}
    return sorted(found.items())


def send_reports(files, *, base_url=None):
    """日報を20件ずつ送り、件数の合計と件ごとの結果を返す。"""
    items = []
    for date, path in files:
        with open(path, encoding="utf-8") as f:
            items.append({"date": date, "markdown": f.read()})
    return _send_batches(_config(base_url), "/api/daily-reports", "reports", items)


def send_summaries(summaries, *, base_url=None):
    """週・月のサマリを送る。summaries は (Period, パス) の並び。"""
    items = []
    for period, path in summaries:
        with open(path, encoding="utf-8") as f:
            items.append({
                "kind": period.kind,
                "periodStart": period.start.isoformat(),
                "periodEnd": period.end.isoformat(),
                "markdown": f.read(),
            })
    return _send_batches(_config(base_url), "/api/daily-report-summaries", "summaries", items)


def _send_batches(config, path, key, items):
    totals = {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "results": []}
    for start in range(0, len(items), BATCH_SIZE):
        result = _request_json(config, path, {key: items[start : start + BATCH_SIZE]})
        for name in ("created", "updated", "skipped", "errors"):
            totals[name] += int(result.get(name, 0))
        totals["results"].extend(result.get("results", []))
    return totals


def reparse_all(*, base_url=None):
    """解析の規則が古い日報を、dashboard 側で作り直させる。作り直した件数を返す。"""
    config = _config(base_url)
    total = 0
    for _ in range(MAX_REPARSE_ROUNDS):
        result = _request_json(config, "/api/daily-reports/reparse", {})
        total += int(result.get("reparsed", 0))
        if int(result.get("remaining", 0)) <= 0:
            return total
    raise DashboardSyncError(f"再解析が {MAX_REPARSE_ROUNDS} 回で終わりませんでした（{total}件まで完了）")


def delete_report(date, *, base_url=None):
    """dashboard から1日分の日報を消す（付随データと改訂履歴も消える）。無かったときは False。"""
    try:
        _request_json(_config(base_url), f"/api/daily-reports/{date}", method="DELETE")
    except DashboardSyncError as error:
        if getattr(error, "status", None) == 404:
            return False
        raise
    return True


def _config(base_url=None):
    load_dotenv(ENV_PATH)
    url = _base_url(base_url or os.environ.get("DASHBOARD_API_URL", ""))
    if not url:
        raise DashboardSyncError(".env の DASHBOARD_API_URL が設定されていません（.env.example を参照）")
    client_id = _access_credential("DASHBOARD_ACCESS_CLIENT_ID", "CF-Access-Client-Id")
    client_secret = _access_credential("DASHBOARD_ACCESS_CLIENT_SECRET", "CF-Access-Client-Secret")
    if not client_id or not client_secret:
        raise DashboardSyncError(".env の DASHBOARD_ACCESS_CLIENT_ID / DASHBOARD_ACCESS_CLIENT_SECRET が設定されていません")
    return {"url": url, "client_id": client_id, "client_secret": client_secret}


def _request_json(config, path, payload=None, *, method="POST"):
    request = Request(
        config["url"] + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method=method,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "user-agent": "auto-daily-report/1.0",
            "CF-Access-Client-Id": config["client_id"],
            "CF-Access-Client-Secret": config["client_secret"],
        },
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=60, context=context) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        sync_error = DashboardSyncError(f"dashboard が HTTP {error.code} を返しました: {detail}")
        sync_error.status = error.code
        raise sync_error from error
    except (URLError, TimeoutError, OSError) as error:
        raise DashboardSyncError(f"dashboard への接続に失敗しました: {error}") from error
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        # Access の認証が通らないと、JSON ではなくログイン画面の HTML が返る
        raise DashboardSyncError("dashboard の応答が JSON ではありません（Access の service token を確認してください）") from error
    if not isinstance(value, dict):
        raise DashboardSyncError("dashboard の応答形式が不正です")
    return value


def _access_credential(name, header_name):
    """環境変数から Access の認証値を読む（「ヘッダー名: 値」の形で貼っても受け付ける）。"""
    value = os.environ.get(name, "").strip()
    prefix = f"{header_name}:"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix):].strip()
    return value


def _base_url(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
