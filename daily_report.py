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

def generate_prompt_parts():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    print(f"{today} の日報プロンプトを生成しています...\n")
    
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
        log_content = "（ログファイルが見つかりません。）"

    # Load Template
    template_path = os.path.join(os.path.dirname(__file__), "templates", "report_prompt_template.txt")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        print(f"Error: Template file not found at {template_path}")
        return None, None

    # Split template into instructions and data
    parts = template.split("{daily_logs}")
    instructions = parts[0].format(calendar_events=events_text)
    
    # We'll send these as two distinct pastes
    return instructions, log_content

if __name__ == "__main__":
    instructions, logs = generate_prompt_parts()
    
    if not instructions:
        sys.exit(1)
    
    # For the local text file, we still save the full combined version for reference
    full_prompt = instructions + "\n" + logs
    
    # Ensure outputs dir exists
    OUTPUT_DIR = "outputs"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save to a text file for easy copying
    output_file = os.path.join(OUTPUT_DIR, "daily_report_prompt.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_prompt)
        
    print(f"プロンプトを保存しました: {output_file}")
    
    # Ask user if they want to run automation
    print("\n--- 自動送信 ---")
    choice = input("Perplexityにブラウザ経由で自動送信しますか？ (y/n): ").strip().lower()
    
    if choice == 'y':
        print("ブラウザを操作しています...")
        from src.perplexity_automator import submit_to_perplexity
        
        # Pass titled parts for better terminal feedback
        response = submit_to_perplexity({
            "指示とカレンダー": instructions,
            "作業ログデータ": logs
        })
        
        report_filename = os.path.join(OUTPUT_DIR, f"daily_report_{datetime.datetime.now().strftime('%Y-%m-%d')}.md")
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(response)
        
        print(f"\n日報を保存しました: {report_filename}")
    else:
        print("\n--- プロンプトのプレビュー ---\n")
        print(prompt[:500] + "\n...(省略)...")

