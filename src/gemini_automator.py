from playwright.sync_api import sync_playwright
import time
import subprocess
import os

USER_DATA_DIR = "./browser_data"

def get_clipboard_content():
    """Returns the current content of the macOS clipboard using pbpaste."""
    try:
        process = subprocess.Popen('pbpaste', env={'LANG': 'en_US.UTF-8'}, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        return output.decode('utf-8')
    except Exception as e:
        print(f"Error reading clipboard: {e}")
        return ""

def submit_to_gemini(prompt):
    """
    Submits the prompt to Gemini using Playwright and retrieves the response
    by clicking the 'Copy' button.
    """
    with sync_playwright() as p:
        # Launch browser with persistent context
        print("ブラウザを起動中...")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome", # Attempt to use installed Chrome
            args=["--start-maximized"] # Optional: start maximized
        )
        
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://gemini.google.com/app")
            
            # --- Input Check ---
            print("入力欄を確認中...")
            # Use a more specific selector to avoid strict mode violation (hidden ql-clipboard div)
            input_selector = "div[contenteditable='true'][role='textbox']"
            
            # Quick check if immediately visible
            time.sleep(2) # Give a small buffer for page load
            if not page.locator(input_selector).is_visible():
                print("入力欄が見つかりません。ログインが必要な可能性があります。")
                print(">> 必要な場合はブラウザ上で手動ログインを行ってください <<")
                
                # Wait up to 5 minutes for user to log in
                page.wait_for_selector(input_selector, state="visible", timeout=300000)
                print("入力欄を検知しました！")
            
            # --- Submit Prompt ---
            print("プロンプトを送信中...")
            
            # Count existing copy buttons to detect new one later
            copy_button_selector = "[data-test-id='copy-button']"
            initial_copy_buttons = page.locator(copy_button_selector).count()
            
            page.fill(input_selector, prompt)
            time.sleep(1)
            page.press(input_selector, "Enter")
            
            # --- Wait for Generation ---
            print("回答の生成を待機中...")
            
            # Poll until a NEW copy button appears
            # This indicates the response has been generated (or at least the UI for it is ready)
            new_response_found = False
            for _ in range(120): # Wait up to 2 minutes
                time.sleep(2)
                current_count = page.locator(copy_button_selector).count()
                if current_count > initial_copy_buttons:
                    new_response_found = True
                    print("新しい回答を検知しました！")
                    break
            
            if not new_response_found:
                 print("警告: 新しいコピーボタンが見つかりませんでした。最新のボタンを使用します。")
            
            # Wait a buffer to ensure text generation finishes (streaming completes)
            # The copy button might appear before full text is done in some UI versions.
            print("テキストの描画完了を待機中(3秒)...")
            time.sleep(3)

            # --- Click Copy Button ---
            print("コピーボタンをクリックします...")
            
            # Get all copy buttons
            buttons = page.locator(copy_button_selector).all()
            if not buttons:
                return "エラー: コピーボタンが見つかりませんでした。"
            
            # Click the last one (most recent response)
            last_button = buttons[-1]
            last_button.scroll_into_view_if_needed()
            last_button.click()
            
            print("コピー完了。クリップボードを取得します...")
            time.sleep(2)
            
            # --- Get Clipboard ---
            content = get_clipboard_content()
            
            if not content:
                return "エラー: クリップボードが空でした。"
            
            # Filter out the Gemini Apps Activity warning if present
            footer_marker = "なお、各種アプリのすべての機能を使用するには"
            if footer_marker in content:
                content = content.split(footer_marker)[0].strip()
                
            return content

        except Exception as e:
            return f"自動化中にエラーが発生しました: {e}"
        finally:
            print("ブラウザを終了します...")
            browser.close()

if __name__ == "__main__":
    prompt = "Hello! Please tell me a joke."
    print(submit_to_gemini(prompt))
