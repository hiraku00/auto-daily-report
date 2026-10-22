import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError, run_claude
from src.dashboard_sync import DashboardSyncError, send_reports
from src.report_generator import ReportError, build_prompt, finish_report
from sync_dashboard import print_summary

OUTPUT_DIR = "outputs"


def main():
    parser = argparse.ArgumentParser(description="作業ログから日報を作り、Claude（claude -p）に書かせて outputs/ に保存します。")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%y%m%d"),
                        help="対象日（YYMMDD形式、例: 261021）。省略時は今日。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet、opus）。省略時は Claude Code の既定。")
    parser.add_argument("--force", action="store_true", help="同じ日付の日報があっても上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="Claude に送らず、プロンプトを標準出力に表示するだけ。")
    parser.add_argument("--no-sync", action="store_true", help="保存した日報を dashboard へ送らない。")
    args = parser.parse_args()

    try:
        target_date = datetime.datetime.strptime(args.date, "%y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        sys.exit("Error: --date は YYMMDD 形式で指定してください（例: 261021）")

    output_path = os.path.join(OUTPUT_DIR, f"daily_report_{target_date}.md")
    if os.path.exists(output_path) and not args.force and not args.dry_run:
        sys.exit(f"Error: {output_path} は既にあります。作り直すときは --force を付けてください。")

    try:
        header, prompt = build_prompt(target_date)
    except ReportError as e:
        sys.exit(f"Error: {e}")

    if args.dry_run:
        print(prompt)
        return

    print(f"{target_date} の日報を Claude に書かせています（数分かかります）...")
    try:
        report = finish_report(header, run_claude(prompt, model=args.model))
    except (ClaudeError, ReportError) as e:
        sys.exit(f"Error: {e}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"日報を保存しました: {output_path}")

    if args.no_sync:
        return
    # 送信に失敗しても日報は保存済みなので、失敗扱いにはせず、送り直す方法だけ示す
    try:
        totals = send_reports([(target_date, output_path)])
    except DashboardSyncError as e:
        print(f"dashboard への送信に失敗しました: {e}\n  送り直すには: python sync_dashboard.py {args.date}")
        return
    print_summary(totals)


if __name__ == "__main__":
    main()
