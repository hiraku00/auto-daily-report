import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError, run_claude
from src.dashboard_sync import DashboardSyncError, send_reports
from src.report_generator import ReportError, build_prompt, finish_report
from src.summary_generator import due_periods
from summarize import create_and_send
from sync_dashboard import print_summary

OUTPUT_DIR = "outputs"


def parse_date(value, option):
    try:
        return datetime.datetime.strptime(value, "%y%m%d").date()
    except ValueError:
        sys.exit(f"Error: {option} は YYMMDD 形式で指定してください（例: 261021）")


def target_dates(args):
    """--date、または --from 〜 --to（両端を含む）の日付を古い順に返す。"""
    if args.date_from is None:
        if args.date_to is not None:
            sys.exit("Error: --to は --from と一緒に指定してください")
        return [parse_date(args.date or datetime.date.today().strftime("%y%m%d"), "--date")]
    if args.date is not None:
        sys.exit("Error: --date と --from は一緒に指定できません")
    start = parse_date(args.date_from, "--from")
    end = parse_date(args.date_to, "--to") if args.date_to else datetime.date.today()
    if start > end:
        sys.exit("Error: --from は --to より前の日付にしてください")
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def make_report(date, args):
    """1日分の日報を作って保存し、dashboard への送信と週末・月末のサマリまで行う。"""
    target_date = date.isoformat()
    output_path = os.path.join(OUTPUT_DIR, f"daily_report_{target_date}.md")
    header, prompt = build_prompt(target_date)

    if args.dry_run:
        print(prompt)
        return

    print(f"{target_date} の日報を Claude に書かせています（数分かかります）...")
    report = finish_report(header, run_claude(prompt, model=args.model))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"日報を保存しました: {output_path}")

    if not args.no_sync:
        # 送信に失敗しても日報は保存済みなので、失敗扱いにはせず、送り直す方法だけ示す
        try:
            print_summary(send_reports([(target_date, output_path)]))
        except DashboardSyncError as e:
            print(f"dashboard への送信に失敗しました: {e}\n  送り直すには: python sync_dashboard.py {date:%y%m%d}")

    if args.no_summary:
        return
    # 日曜の日報ならその週、月末の日報ならその月のサマリを作る(作り忘れた直前の週・月も、まだ無ければ作る)
    for period in due_periods(date):
        try:
            create_and_send(period, model=args.model, sync=not args.no_sync)
        except (ClaudeError, ReportError) as e:
            print(f"{period.name}のサマリを作れませんでした: {e}\n  作り直すには: python summarize.py {period.kind} {period.start:%y%m%d}")


def main():
    parser = argparse.ArgumentParser(description="作業ログから日報を作り、Claude（claude -p）に書かせて outputs/ に保存します。")
    parser.add_argument("--date", help="対象日（YYMMDD形式、例: 261021）。省略時は今日。")
    parser.add_argument("--from", dest="date_from", help="期間でまとめて作るときの最初の日（YYMMDD形式）。--date とは一緒に使えない。")
    parser.add_argument("--to", dest="date_to", help="期間でまとめて作るときの最後の日（YYMMDD形式）。省略時は今日。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet、opus）。省略時は Claude Code の既定。")
    parser.add_argument("--force", action="store_true", help="同じ日付の日報があっても上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="Claude に送らず、プロンプトを標準出力に表示するだけ。")
    parser.add_argument("--no-sync", action="store_true", help="保存した日報・サマリを dashboard へ送らない。")
    parser.add_argument("--no-summary", action="store_true", help="週末・月末のサマリを作らない。")
    args = parser.parse_args()

    dates = target_dates(args)
    if len(dates) == 1:
        output_path = os.path.join(OUTPUT_DIR, f"daily_report_{dates[0].isoformat()}.md")
        if os.path.exists(output_path) and not args.force and not args.dry_run:
            sys.exit(f"Error: {output_path} は既にあります。作り直すときは --force を付けてください。")
        try:
            make_report(dates[0], args)
        except (ClaudeError, ReportError) as e:
            sys.exit(f"Error: {e}")
        return

    # 期間指定では、1日失敗しても残りの日は続け、最後に結果をまとめる
    done, skipped, failed = [], [], []
    for date in dates:
        output_path = os.path.join(OUTPUT_DIR, f"daily_report_{date.isoformat()}.md")
        if os.path.exists(output_path) and not args.force and not args.dry_run:
            print(f"{date.isoformat()}: 日報が既にあるので飛ばします（作り直すときは --force）")
            skipped.append(date)
            continue
        try:
            make_report(date, args)
            done.append(date)
        except (ClaudeError, ReportError) as e:
            print(f"{date.isoformat()}: 日報を作れませんでした: {e}")
            failed.append(date)

    print(f"\n{dates[0].isoformat()}〜{dates[-1].isoformat()}: 作成 {len(done)} 件、既存のため省略 {len(skipped)} 件、失敗 {len(failed)} 件")
    if failed:
        print("  失敗した日: " + ", ".join(d.isoformat() for d in failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
