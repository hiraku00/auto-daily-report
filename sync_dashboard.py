import argparse
import datetime
import sys

from src.dashboard_sync import DashboardSyncError, reparse_all, report_files, send_reports, send_summaries
from src.summary_generator import summary_files


def print_summary(totals):
    for result in totals["results"]:
        status = result.get("status", "?")
        if status == "skipped":
            continue
        notes = result.get("error") or "、".join(result.get("warnings") or [])
        target = result.get("date") or f"{result.get('kind')} {result.get('periodStart')}"
        print(f"  {target}: {status}" + (f"（{notes}）" if notes else ""))
    print(f"作成 {totals['created']} / 更新 {totals['updated']} / 変更なし {totals['skipped']} / エラー {totals['errors']}")


def main():
    parser = argparse.ArgumentParser(description="outputs/ の日報を dashboard（D1）へ送ります。内容が変わっていない日報は dashboard 側で何もしません。")
    parser.add_argument("dates", nargs="*", help="送る日付（YYMMDD形式、例: 261021）。複数指定できます。")
    parser.add_argument("--all", action="store_true", help="outputs/ の日報をすべて送る。")
    parser.add_argument("--summaries", action="store_true", help="outputs/summaries/ の週・月のサマリをすべて送る。")
    parser.add_argument("--reparse", action="store_true", help="dashboard 側の解析の規則を変えた後、登録済みの日報を作り直させる。")
    parser.add_argument("--dry-run", action="store_true", help="送らずに、送る対象の一覧を表示するだけ。")
    args = parser.parse_args()

    if args.reparse:
        try:
            print(f"再解析しました: {reparse_all()}件")
        except DashboardSyncError as e:
            sys.exit(f"Error: {e}")
        return

    if args.summaries:
        files = summary_files()
        if not files:
            sys.exit("Error: 送るサマリがありません。")
        if args.dry_run:
            for period, path in files:
                print(f"{period.kind} {period.range_text}  {path}")
            print(f"{len(files)}件（送信はしていません）")
            return
        try:
            totals = send_summaries(files)
        except DashboardSyncError as e:
            sys.exit(f"Error: {e}")
        print_summary(totals)
        sys.exit(1 if totals["errors"] else 0)

    if bool(args.dates) == args.all:
        parser.error("日付を指定するか、--all を付けてください。")
    try:
        dates = None if args.all else [datetime.datetime.strptime(d, "%y%m%d").strftime("%Y-%m-%d") for d in args.dates]
    except ValueError:
        parser.error("日付は YYMMDD 形式で指定してください（例: 261021）。")

    try:
        files = report_files(dates=dates)
        if not files:
            sys.exit("Error: 送る日報がありません。")
        if args.dry_run:
            for date, path in files:
                print(f"{date}  {path}")
            print(f"{len(files)}件（送信はしていません）")
            return
        totals = send_reports(files)
    except DashboardSyncError as e:
        sys.exit(f"Error: {e}")
    print_summary(totals)
    if totals["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
