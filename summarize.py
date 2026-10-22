import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError
from src.dashboard_sync import DashboardSyncError, send_summaries
from src.report_generator import ReportError
from src.summary_generator import Period, build_summary_prompt, generate_summary, load_reports, summary_path
from sync_dashboard import print_summary


def create_and_send(period, model=None, sync=True):
    """サマリを作って保存し、dashboard へ送る。作れなければ例外、送れなければ表示だけして続ける。"""
    print(f"{period.name}（{period.range_text}）のサマリを Claude に書かせています（数分かかります）...")
    path = generate_summary(period, model=model)
    print(f"サマリを保存しました: {path}")
    if not sync:
        return
    try:
        print_summary(send_summaries([(period, path)]))
    except DashboardSyncError as e:
        print(f"dashboard への送信に失敗しました: {e}\n  送り直すには: python sync_dashboard.py --summaries")


def parse_period(kind, value):
    today = datetime.date.today()
    if not value:
        return Period.previous(kind, today)
    try:
        if kind == "week":
            return Period.week_of(datetime.datetime.strptime(value, "%y%m%d").date())
        return Period.month_of(datetime.datetime.strptime(value, "%y%m").date())
    except ValueError:
        sys.exit("Error: 週は YYMMDD（その週のどの日でもよい）、月は YYMM の形式で指定してください（例: week 261021 / month 2610）")


def main():
    parser = argparse.ArgumentParser(description="期間内の日報から、週・月ごとのサマリを Claude（claude -p）に書かせて outputs/summaries/ に保存し、dashboard へ送ります。")
    parser.add_argument("kind", choices=["week", "month"], help="week: 月曜〜日曜 / month: 1日〜末日")
    parser.add_argument("when", nargs="?", help="週は YYMMDD（その週のどの日でもよい）、月は YYMM。省略時は直近の終わった週・月。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet、opus）。省略時は Claude Code の既定。")
    parser.add_argument("--force", action="store_true", help="同じ期間のサマリがあっても上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="Claude に送らず、プロンプトを標準出力に表示するだけ。")
    parser.add_argument("--no-sync", action="store_true", help="保存したサマリを dashboard へ送らない。")
    args = parser.parse_args()

    period = parse_period(args.kind, args.when)
    output_path = summary_path(period)
    if os.path.exists(output_path) and not args.force and not args.dry_run:
        sys.exit(f"Error: {output_path} は既にあります。作り直すときは --force を付けてください。")

    if args.dry_run:
        try:
            print(build_summary_prompt(period, load_reports(period))[1])
        except ReportError as e:
            sys.exit(f"Error: {e}")
        return

    try:
        create_and_send(period, model=args.model, sync=not args.no_sync)
    except (ClaudeError, ReportError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
