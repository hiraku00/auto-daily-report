import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError, run_claude
from src.report_generator import ReportError
from src.summary_generator import SUMMARY_DIR, Period, build_summary_prompt, finish_summary, load_reports


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
    parser = argparse.ArgumentParser(description="期間内の日報から、週・月ごとのサマリを Claude（claude -p）に書かせて outputs/summaries/ に保存します。")
    parser.add_argument("kind", choices=["week", "month"], help="week: 月曜〜日曜 / month: 1日〜末日")
    parser.add_argument("when", nargs="?", help="週は YYMMDD（その週のどの日でもよい）、月は YYMM。省略時は直近の終わった週・月。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet、opus）。省略時は Claude Code の既定。")
    parser.add_argument("--force", action="store_true", help="同じ期間のサマリがあっても上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="Claude に送らず、プロンプトを標準出力に表示するだけ。")
    args = parser.parse_args()

    period = parse_period(args.kind, args.when)
    output_path = os.path.join(SUMMARY_DIR, period.filename)
    if os.path.exists(output_path) and not args.force and not args.dry_run:
        sys.exit(f"Error: {output_path} は既にあります。作り直すときは --force を付けてください。")

    try:
        header, prompt = build_summary_prompt(period, load_reports(period))
    except ReportError as e:
        sys.exit(f"Error: {e}")

    if args.dry_run:
        print(prompt)
        return

    print(f"{period.name}（{period.range_text}）のサマリを Claude に書かせています（数分かかります）...")
    try:
        summary = finish_summary(header, run_claude(prompt, model=args.model))
    except (ClaudeError, ReportError) as e:
        sys.exit(f"Error: {e}")

    os.makedirs(SUMMARY_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"サマリを保存しました: {output_path}")


if __name__ == "__main__":
    main()
