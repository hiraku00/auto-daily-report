import argparse
import datetime
import os
import sys

from src.claude_runner import ClaudeError, run_claude
from src.dashboard_sync import DashboardSyncError, send_morning_pages, send_reports
from src.morning_page import DIR_ENV, load_morning_context, morning_page_dir
from src.morning_pages import make_record, needs_extraction
from src.reflection import append_reflection, build_reflection_prompt, extract_reflection
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
    """--date（複数可）、または --from 〜 --to（両端を含む）の日付を古い順に返す。省略時は前日。"""
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    if args.date_from is None:
        if args.date_to is not None:
            sys.exit("Error: --to は --from と一緒に指定してください")
        if not args.date:
            return [yesterday]
        # 「--date 261103 261105」「--date 261103,261105」のどちらでも受け付け、重複は1つにまとめる
        values = [v for arg in args.date for v in arg.split(",") if v]
        return sorted({parse_date(v, "--date") for v in values})
    if args.date is not None:
        sys.exit("Error: --date と --from は一緒に指定できません")
    start = parse_date(args.date_from, "--from")
    end = parse_date(args.date_to, "--to") if args.date_to else yesterday
    if start > end:
        sys.exit("Error: --from は --to より前の日付にしてください")
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def report_path(date):
    return os.path.join(OUTPUT_DIR, f"daily_report_{date.isoformat()}.md")


def morning_dir(args):
    """モーニングページのフォルダ。--no-morning か未設定なら None（6節目を付けない）。"""
    if args.no_morning:
        return None
    base = morning_page_dir()
    if base and not os.path.isdir(base):
        print(f"{DIR_ENV}（{base}）がフォルダではないので、モーニングページは使いません")
        return None
    return base


def load_context(date, base, raw=False):
    context = load_morning_context(date, base, raw=raw)
    for notice in context.notices:
        print(f"  {notice}")
    return context


def add_reflection(date, report, base, model=None, raw=False):
    """日報に6節目「予定と振り返り」を付けて返す。モーニングページの予定も振り返りも無ければ ReportError。"""
    context = load_context(date, base, raw=raw)
    if context.empty:
        raise ReportError("モーニングページの予定も振り返りも見つからないので、6節目を書けません")
    print(f"{date.isoformat()} の6節目（予定と振り返り）を Claude に書かせています...")
    body = extract_reflection(run_claude(build_reflection_prompt(date.isoformat(), report, context), model=model))
    if context.retro is None and date + datetime.timedelta(days=1) >= datetime.date.today():
        print(f"  翌朝の振り返りが無いまま書きました。サマリを貼ったら次で書き直せます: python daily_report.py --date {date:%y%m%d} --morning-only")
    return append_reflection(report, context, body)


def save_and_sync(date, path, report, args):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"日報を保存しました: {path}")
    if args.no_sync:
        return
    # 送信に失敗しても日報は保存済みなので、失敗扱いにはせず、送り直す方法だけ示す
    try:
        print_summary(send_reports([(date.isoformat(), path)]), label="日報")
    except DashboardSyncError as e:
        print(f"dashboard への送信に失敗しました: {e}\n  送り直すには: python sync_dashboard.py {date:%y%m%d}")


def record_morning_pages(date, base, args):
    """6節目に使う翌朝(D+1)のページの記録を作り、dashboard の「モーニングページ」画面へ送る。
    毎日実行すれば当日朝(D)のページは前日の日報で送り済みなので、1回の実行で送るのは翌朝の1枚だけにする。
    ヘッダーだけの記録は Claude を使わないので毎回読み直す(あとで書き足したページの時間・文字数を反映する)。
    記録を作れなくても日報は保存済みなので、止めずに作り直す方法だけ示す。"""
    day = date + datetime.timedelta(days=1)
    if day > datetime.date.today():
        return
    retry = f"python morning_pages.py --date {day:%y%m%d}"
    try:
        record = make_record(day, base, force=not needs_extraction(day), model=args.model)
    except (ClaudeError, OSError) as e:
        print(f"モーニングページ {day.isoformat()}（翌朝）の記録を作れませんでした: {e}\n  作り直すには: {retry}")
        return
    if record is None:
        return
    print(f"モーニングページの記録を作りました: {day.isoformat()}（翌朝）")
    if args.no_sync:
        return
    try:
        print_summary(send_morning_pages([record]), label="モーニングページ", show_skipped=True)
    except DashboardSyncError as e:
        print(f"モーニングページの記録の送信に失敗しました: {e}\n  送り直すには: {retry}")


def make_report(date, args):
    """1日分の日報を作って保存し、モーニングページの6節目、dashboard への送信、週末・月末のサマリまで行う。"""
    target_date = date.isoformat()
    output_path = report_path(date)
    header, prompt = build_prompt(target_date)
    base = morning_dir(args)

    if args.dry_run:
        print(prompt)
        if base:
            # 段2のプロンプトは日報ができてから作るので、ここでは抜き出したモーニングページだけを見せる
            context = load_context(date, base, raw=args.raw_morning)
            print(f"\n===== 6節目に使うモーニングページ =====\n## 予定\n{context.plan or '（なし）'}\n\n## 振り返り\n{context.retro or '（なし）'}\n\n## 気になること\n{context.thoughts or '（なし）'}")
        return

    print(f"{target_date} の日報を Claude に書かせています（数分かかります）...")
    report = finish_report(header, run_claude(prompt, model=args.model))
    if base:
        # 6節目が書けなくても、1〜5節の日報は保存して送る
        try:
            report = add_reflection(date, report, base, model=args.model, raw=args.raw_morning)
        except (ClaudeError, ReportError) as e:
            print(f"6節目（予定と振り返り）を付けられませんでした: {e}\n  あとで足すには: python daily_report.py --date {date:%y%m%d} --morning-only")
    save_and_sync(date, output_path, report, args)
    if base:
        record_morning_pages(date, base, args)

    if args.no_summary:
        return
    # 日曜の日報ならその週、月末の日報ならその月のサマリを作る(作り忘れた直前の週・月も、まだ無ければ作る)
    for period in due_periods(date):
        try:
            create_and_send(period, model=args.model, sync=not args.no_sync)
        except (ClaudeError, ReportError) as e:
            print(f"{period.name}のサマリを作れませんでした: {e}\n  作り直すには: python summarize.py {period.kind} {period.start:%y%m%d}")


def add_morning_only(date, args):
    """既にある日報の1〜5節はそのままに、6節目だけを付け直して保存・送信する。"""
    output_path = report_path(date)
    if not os.path.exists(output_path):
        raise ReportError(f"{output_path} がありません（先に日報を作ってください）")
    base = morning_dir(args)
    if not base:
        sys.exit(f"Error: --morning-only には .env の {DIR_ENV}（モーニングページのフォルダ）が必要です")
    with open(output_path, encoding="utf-8") as f:
        report = f.read()
    if args.dry_run:
        print(build_reflection_prompt(date.isoformat(), report, load_context(date, base, raw=args.raw_morning)))
        return
    save_and_sync(date, output_path, add_reflection(date, report, base, model=args.model, raw=args.raw_morning), args)
    record_morning_pages(date, base, args)


def blocks_overwrite(path, args):
    """日報を作り直すことになるのに --force が無い。--morning-only は既にある日報に足すので止めない。"""
    return os.path.exists(path) and not (args.force or args.dry_run or args.morning_only)


def main():
    parser = argparse.ArgumentParser(description="作業ログから日報を作り、Claude（claude -p）に書かせて outputs/ に保存します。")
    parser.add_argument("--date", nargs="+", help="対象日（YYMMDD形式、例: 261021）。複数指定可（例: --date 261103 261105）。省略時は前日。")
    parser.add_argument("--from", dest="date_from", help="期間でまとめて作るときの最初の日（YYMMDD形式）。--date とは一緒に使えない。")
    parser.add_argument("--to", dest="date_to", help="期間でまとめて作るときの最後の日（YYMMDD形式）。省略時は前日。")
    parser.add_argument("--model", help="claude に渡すモデル（例: sonnet、opus）。省略時は Claude Code の既定。")
    parser.add_argument("--force", action="store_true", help="同じ日付の日報があっても上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="Claude に送らず、プロンプトを標準出力に表示するだけ。")
    parser.add_argument("--no-sync", action="store_true", help="保存した日報・サマリを dashboard へ送らない。")
    parser.add_argument("--no-summary", action="store_true", help="週末・月末のサマリを作らない。")
    parser.add_argument("--no-morning", action="store_true", help="モーニングページから6節目（予定と振り返り）を書き足さない。")
    parser.add_argument("--morning-only", action="store_true", help="既にある日報の1〜5節はそのままに、6節目だけを付け直す（週・月のサマリは作らない）。")
    parser.add_argument("--raw-morning", action="store_true", help="整理された節の無い古いモーニングページは、本文そのものから6節目を書かせる（過去分を作るとき用）。")
    args = parser.parse_args()
    if args.raw_morning and args.no_morning:
        sys.exit("Error: --raw-morning と --no-morning は一緒に指定できません")
    if args.no_morning and args.morning_only:
        sys.exit("Error: --no-morning と --morning-only は一緒に指定できません")
    run = add_morning_only if args.morning_only else make_report

    dates = target_dates(args)
    if len(dates) == 1:
        output_path = report_path(dates[0])
        if blocks_overwrite(output_path, args):
            sys.exit(f"Error: {output_path} は既にあります。作り直すときは --force を、6節目だけ付け直すときは --morning-only を付けてください。")
        try:
            run(dates[0], args)
        except (ClaudeError, ReportError) as e:
            sys.exit(f"Error: {e}")
        return

    # 複数日の指定では、1日失敗しても残りの日は続け、最後に結果をまとめる
    done, skipped, failed = [], [], []
    for date in dates:
        output_path = report_path(date)
        if blocks_overwrite(output_path, args):
            print(f"{date.isoformat()}: 日報が既にあるので飛ばします（作り直すときは --force）")
            skipped.append(date)
            continue
        try:
            run(date, args)
            done.append(date)
        except (ClaudeError, ReportError) as e:
            print(f"{date.isoformat()}: 日報を作れませんでした: {e}")
            failed.append(date)

    print(f"\n{dates[0].isoformat()}〜{dates[-1].isoformat()}（{len(dates)} 日）: 作成 {len(done)} 件、既存のため省略 {len(skipped)} 件、失敗 {len(failed)} 件")
    if failed:
        print("  失敗した日: " + ", ".join(d.isoformat() for d in failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
