import json
import datetime
import os
from src.calendar_utils import get_todays_events

LOG_DIR = "logs"
TEMPLATE_DIR = "templates"

def calculate_app_usage_stats(date_str):
    """
    Logs data からアプリごとの使用回数を集計し、
    概要テキストを生成する。
    """
    filename = os.path.join(LOG_DIR, f"daily_log_{date_str}.jsonl")
    if not os.path.exists(filename):
        return ""
    
    stats = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line)
                app_name = entry.get('app_name', 'Unknown')
                stats[app_name] = stats.get(app_name, 0) + 1
            except json.JSONDecodeError:
                continue

    if not stats:
        return ""

    # Sort by frequency
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    
    lines = ["\n### アプリ使用統計 (キャプチャ頻度)"]
    lines.append("| アプリケーション | キャプチャ回数 |")
    lines.append("|---|---|")
    for app, count in sorted_stats:
        lines.append(f"| {app} | {count}回 |")
    
    return "\n".join(lines)

def get_log_content(date_str):
    filename = os.path.join(LOG_DIR, f"daily_log_{date_str}.jsonl")
    if not os.path.exists(filename):
        return None
    
    log_lines = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line)
                # Reformat for the prompt
                log_lines.append(f"{entry['timestamp']} | {entry['app_name']} | {entry.get('text_summary', '')}")
            except json.JSONDecodeError:
                continue
    
    return "\n".join(log_lines)

def generate_prompt_parts(target_date_str):
    """
    Generate the prompt sections for given date.
    Returns (instructions, logs_with_stats)
    """
    # 1. Get Calendar Events
    target_date = datetime.datetime.strptime(target_date_str, "%Y-%m-%d")
    try:
        events = get_todays_events(target_date)
        events_text = ""
        if events:
            for start, summary in events:
                events_text += f"- {start}: {summary}\n"
        else:
            events_text = "（予定なし）"
    except Exception as e:
        events_text = f"（カレンダー取得エラー: {e}）"

    # 2. Get Work Logs
    log_content = get_log_content(target_date_str)
    if not log_content:
        log_content = "（ログファイルが見つかりません。）"

    # 3. Calculate Stats
    stats_text = calculate_app_usage_stats(target_date_str)
    
    full_logs_with_stats = log_content + "\n" + stats_text

    # 4. Load Template
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), TEMPLATE_DIR, "report_prompt_template.txt")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        return None, None

    # 5. Build instructions
    parts = template.split("{daily_logs}")
    instructions = parts[0].format(calendar_events=events_text, date=target_date_str).strip() + "\n"
    
    return instructions, full_logs_with_stats
