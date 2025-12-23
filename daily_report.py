import json
import datetime
import os
import json
import datetime
import os
import sys

# Ensure src is in sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.calendar_utils import get_todays_events

LOG_DIR = "logs"

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

def generate_prompt():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    print(f"Generating report prompt for {today}...\n")
    
    # Get Calendar Events
    try:
        events = get_todays_events()
        events_text = ""
        if events:
            for start, summary in events:
                events_text += f"- {start}: {summary}\n"
        else:
            events_text = "（予定なし）"
    except Exception as e:
        events_text = f"（カレンダー取得エラー: {e}）"

    # Get Work Logs
    log_content = get_log_content(today)
    if not log_content:
        log_content = "（ログファイルが見つかりません。まだ実行されていないか、ログがありません。）"

    prompt = f"""
以下の情報を元に、今日1日の活動報告（日報）をMarkdown形式で作成してください。

# 依頼内容
- 今日の作業ログとカレンダーの予定を照らし合わせ、実際に何に時間を使ったかを推測して要約してください。
- プロジェクトごと、または作業カテゴリごとに時間を集計してください。
- 予定されていた会議等の時間に、別の作業（SlackやVS Codeなど）をしていた場合は、その旨を指摘してください。

# カレンダーの予定（今日のスケジュール）
{events_text}

# 作業ログ（1分ごとのサマリー）
{log_content}
"""

    return prompt

if __name__ == "__main__":
    prompt = generate_prompt()
    
    # Save to a text file for easy copying
    output_file = "daily_report_prompt.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
        
    print(f"Prompt saved to {output_file}")
    print("\n--- Prompt Preview ---\n")
    print(prompt[:500] + "\n...(truncated)...")
