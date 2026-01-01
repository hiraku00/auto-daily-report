import datetime
import os
import sys
import argparse

# Ensure src is in sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.report_generator import generate_prompt_parts

def main():
    parser = argparse.ArgumentParser(description='Generate daily report prompt and optionally submit to Perplexity.')
    parser.add_argument('--date', type=str, help='Target date in YYMMDD format (e.g., 241225). Defaults to today.', default=datetime.datetime.now().strftime("%y%m%d"))
    
    args = parser.parse_args()
    input_date_str = args.date
    
    # 1. Parse YYMMDD -> Date Object
    try:
        target_date_obj = datetime.datetime.strptime(input_date_str, "%y%m%d")
    except ValueError:
        print("Error: Date must be in YYMMDD format (e.g., 251224 for 2025-12-24)")
        sys.exit(1)

    # 2. Convert to YYYY-MM-DD string for internal use
    target_date_str = target_date_obj.strftime("%Y-%m-%d")

    # 3. Generate Parts
    print(f"{target_date_str} の日報プロンプトを生成しています...\n")
    instructions, logs = generate_prompt_parts(target_date_str)
    
    if not instructions:
        print("Error: Prompt generation failed. Check if template exists.")
        sys.exit(1)
    
    # Ensure outputs dir exists
    OUTPUT_DIR = "outputs"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 4. Save Instructions
    output_file = os.path.join(OUTPUT_DIR, "daily_report_prompt.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(instructions)
        
    print(f"プロンプト（指示書のみ）を保存しました: {output_file}")
    
    # 5. Handle submission
    print("\n--- 自動送信 ---")
    choice = input("Perplexityにブラウザ経由で自動送信しますか？ (y/n): ").strip().lower()
    
    if choice == 'y':
        print("ブラウザを操作しています...")
        from src.perplexity_automator import submit_to_perplexity
        
        response = submit_to_perplexity({
            "指示とカレンダー": instructions,
            "作業ログデータ (統計含む)": logs
        })
        
        report_filename = os.path.join(OUTPUT_DIR, f"daily_report_{target_date_str}.md")
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(response)
        
        print(f"\n日報を保存しました: {report_filename}")
    else:
        print("\n--- プロンプトのプレビュー ---\n")
        print(instructions[:500] + "\n...(省略)...")

if __name__ == "__main__":
    main()
