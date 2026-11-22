import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError
from src.dashboard_sync import DashboardSyncError, send_morning_pages
from src.morning_page import DIR_ENV, morning_page_dir
from src.morning_pages import EXTRACT_PROMPT, make_record, needs_extraction, page_path
from sync_dashboard import print_summary

# モーニングページの最初の日(Obsidian の 2023年6月)
FIRST_PAGE = datetime.date(2023, 6, 1)
SEND_EVERY = 20


def parse_date(value, option):
    try:
        return datetime.datetime.strptime(value, "%y%m%d").date()
    except ValueError:
        sys.exit(f"Error: {option} は YYMMDD 形式で指定してください（例: 240415）")


def target_dates(args):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    if args.date:
        values = [v for arg in args.date for v in arg.split(",") if v]
        return sorted({parse_date(v, "--date") for v in values})
    start = parse_date(args.date_from, "--from") if args.date_from else FIRST_PAGE
    end = parse_date(args.date_to, "--to") if args.date_to else yesterday
    if start > end:
        sys.exit("Error: --from は --to より前の日付にしてください")
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def flush(batch, no_sync):
    if not batch or no_sync:
        return
    try:
        print_summary(send_morning_pages(batch))
    except DashboardSyncError as e:
        print(f"dashboard への送信に失敗しました: {e}（もう一度実行すると、保存済みの分は Claude を使わずに送り直します）")


def main():
    parser = argparse.ArgumentParser(description="Obsidian のモーニングページ1枚ごとの記録（ヘッダーと、昨日のこと・今日の予定・気がかり）を作り、dashboard へ送ります。")
    parser.add_argument("--date", nargs="+", help="対象日（YYMMDD形式。複数可）。")
    parser.add_argument("--from", dest="date_from", help="期間の最初の日（YYMMDD形式）。省略時は 2023-06-01。")
    parser.add_argument("--to", dest="date_to", help="期間の最後の日（YYMMDD形式）。省略時は前日。")
    parser.add_argument("--header-only", action="store_true", help="Claude を使わず、ヘッダー（時間・場所・文字数）だけを作る。")
    parser.add_argument("--extract-all", action="store_true", help="日報のある期間（2025-12-23 以降）のページも、本文から取り出す。")
    parser.add_argument("--force", action="store_true", help="保存済みの取り出しがあっても、やり直す。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet）。省略時は Claude Code の既定。")
    parser.add_argument("--no-sync", action="store_true", help="dashboard へ送らない。")
    parser.add_argument("--dry-run", action="store_true", help="Claude も dashboard も使わず、対象のページ数と取り出しの有無を表示するだけ。")
    args = parser.parse_args()

    base = morning_page_dir()
    if not base or not os.path.isdir(base):
        sys.exit(f"Error: .env の {DIR_ENV}（モーニングページのフォルダ）が必要です")
    dates = target_dates(args)

    if args.dry_run:
        pages = [d for d in dates if os.path.exists(page_path(base, d))]
        extract = [d for d in pages if needs_extraction(d, args.header_only, args.extract_all)]
        print(f"対象 {len(dates)} 日のうちページがある日 {len(pages)}、Claude で取り出す日 {len(extract)}、ヘッダーだけの日 {len(pages) - len(extract)}")
        print(f"（取り出しのプロンプト: {len(EXTRACT_PROMPT)} 字＋本文）")
        return

    done, failed, missing, batch = 0, [], 0, []
    for date in dates:
        try:
            record = make_record(date, base, header_only=args.header_only, extract_all=args.extract_all, force=args.force, model=args.model)
        except ClaudeError as e:
            print(f"{date.isoformat()}: 取り出せませんでした: {e}")
            failed.append(date)
            continue
        if record is None:
            missing += 1
            continue
        done += 1
        batch.append(record)
        print(f"{date.isoformat()}: {'取り出し' if record['extracted'] else 'ヘッダーのみ'}（昨日{len(record['yesterday'])}・予定{len(record['plan'])}・気がかり{len(record['notes'])}）")
        if len(batch) >= SEND_EVERY:
            flush(batch, args.no_sync)
            batch = []
    flush(batch, args.no_sync)

    print(f"\n{dates[0].isoformat()}〜{dates[-1].isoformat()}（{len(dates)} 日）: 作成 {done} 件、ページ無し {missing} 件、失敗 {len(failed)} 件")
    if failed:
        print("  失敗した日: " + ", ".join(d.isoformat() for d in failed[:20]) + (" ほか" if len(failed) > 20 else ""))
        sys.exit(1)


if __name__ == "__main__":
    main()
