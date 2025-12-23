import time
import datetime
import json
import os
import sys

# Ensure src is in sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.ocr_utils import get_screen_text
from src.app_utils import get_active_window_info

LOG_DIR = "logs"

def ensure_log_dir():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def get_log_filename():
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"daily_log_{date_str}.jsonl")

def append_log(app_name, text):
    filename = get_log_filename()
    
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    # Simple deduplication or cleanup could be added here
    # For now, we save everything as requested, but maybe truncate very long text
    text_summary = text.replace("\n", " ")[:500] # Limit to 500 chars for summary column

    log_entry = {
        'timestamp': timestamp,
        'app_name': app_name,
        'text_summary': text_summary
    }

    with open(filename, 'a', encoding='utf-8') as f:
        json.dump(log_entry, f, ensure_ascii=False)
        f.write('\n')
    
    print(f"[{timestamp}] Saved log for {app_name}")

def main_loop():
    print("Starting Auto Daily Report Tool...")
    print("Press Ctrl+C to stop.")
    ensure_log_dir()
    
    try:
        while True:
            # Capture data
            app_name = get_active_window_info()
            text = get_screen_text()
            
            # Log data
            if text.strip(): # Only log if there is text
                append_log(app_name, text)
            else:
                 print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] No text detected in {app_name}")

            # Wait for 60 seconds
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nStopping tool.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        # Optionally log the error to a file
        time.sleep(60) # Wait before retrying to avoid rapid failure loops

if __name__ == "__main__":
    main_loop()
