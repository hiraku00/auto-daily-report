import os
import time
import webbrowser
import configparser
import pyautogui
import pyperclip

PROMPT_FILE_PATH = "./outputs/daily_report_prompt.txt"
PERPLEXITY_URL = "https://www.perplexity.ai/"
CONFIG_FILE_PATH = "./config/perplexity_coordinates.ini"

# pyautoguiの設定
pyautogui.PAUSE = 0.1

def load_config():
    """
    Load all coordinates and settings from config file.
    Strictly enforced: raises KeyError if any required value is missing.
    """
    if not os.path.exists(CONFIG_FILE_PATH):
        raise FileNotFoundError(f"設定ファイルが見つかりません: {CONFIG_FILE_PATH}")

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH)
    
    result = {}
    
    try:
        # 1. 座標の取得 (全て必須)
        if not config.has_section('coordinates'):
            raise KeyError("設定ファイルに [coordinates] セクションがありません。")
        
        coords = config['coordinates']
        result['input_field'] = (coords.getint('input_field_x'), coords.getint('input_field_y'))
        result['submit_button'] = (coords.getint('submit_button_x'), coords.getint('submit_button_y'))
        result['copy_button'] = (coords.getint('copy_button_x'), coords.getint('copy_button_y'))
        result['scroll_focus'] = (coords.getint('scroll_focus_x'), coords.getint('scroll_focus_y'))
                
        # 2. 検索モードの取得 (全て必須)
        if not config.has_section('search_modes'):
            raise KeyError("設定ファイルに [search_modes] セクションがありません。")
            
        modes = config['search_modes']
        result['normal_search'] = (modes.getint('normal_x'), modes.getint('normal_y'))
        result['deep_research'] = (modes.getint('deep_x'), modes.getint('deep_y'))
                
        # 3. 設定値の取得 (全て必須)
        if not config.has_section('settings'):
            raise KeyError("設定ファイルに [settings] セクションがありません。")
            
        settings = config['settings']
        result['wait_time'] = settings.getint('wait_time')
        result['browser_load_time'] = settings.getint('browser_load_time')
        result['paste_delay'] = settings.getint('paste_delay')
                
    except (configparser.Error, ValueError, KeyError) as e:
        print(f"\n[ERROR] 設定ファイルが不完全または不正です: {CONFIG_FILE_PATH}")
        print(f"詳細: {e}")
        print("\n修正するか、再度 'python daily_report.py' を実行して座標設定をやり直してください。")
        raise
    
    return result

def save_config(config_data):
    """Save all coordinates and settings to config file."""
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    
    config = configparser.ConfigParser()
    
    # Coordinates section
    config['coordinates'] = {}
    if config_data['input_field'][0] is not None:
        config['coordinates']['input_field_x'] = str(config_data['input_field'][0])
        config['coordinates']['input_field_y'] = str(config_data['input_field'][1])
    if config_data['submit_button'][0] is not None:
        config['coordinates']['submit_button_x'] = str(config_data['submit_button'][0])
        config['coordinates']['submit_button_y'] = str(config_data['submit_button'][1])
    if config_data['copy_button'][0] is not None:
        config['coordinates']['copy_button_x'] = str(config_data['copy_button'][0])
        config['coordinates']['copy_button_y'] = str(config_data['copy_button'][1])
    if config_data['scroll_focus'][0] is not None:
        config['coordinates']['scroll_focus_x'] = str(config_data['scroll_focus'][0])
        config['coordinates']['scroll_focus_y'] = str(config_data['scroll_focus'][1])
    
    # Search Modes section
    config['search_modes'] = {}
    if config_data['normal_search'][0] is not None:
        config['search_modes']['normal_x'] = str(config_data['normal_search'][0])
        config['search_modes']['normal_y'] = str(config_data['normal_search'][1])
    if config_data['deep_research'][0] is not None:
        config['search_modes']['deep_x'] = str(config_data['deep_research'][0])
        config['search_modes']['deep_y'] = str(config_data['deep_research'][1])
        
    # Settings section
    config['settings'] = {
        'wait_time': str(config_data['wait_time']),
        'browser_load_time': str(config_data['browser_load_time']),
        'paste_delay': str(config_data['paste_delay'])
    }
    
    with open(CONFIG_FILE_PATH, 'w') as f:
        config.write(f)
    
    print(f"設定を保存しました: {CONFIG_FILE_PATH}")

def get_position(description):
    """Get current mouse position using pyautogui."""
    print(f"{description}の位置にマウスを移動してください。")
    input("準備ができたらEnterキーを押してください...")
    position = pyautogui.position()
    print(f"取得した座標: {position}")
    return position.x, position.y

def setup_coordinates():
    """Interactively set up all coordinates."""
    config_data = load_config()
    
    # Check if all required coordinates exist
    all_set = (
        config_data['input_field'][0] is not None and
        config_data['submit_button'][0] is not None and
        config_data['copy_button'][0] is not None and
        config_data['scroll_focus'][0] is not None and
        config_data['normal_search'][0] is not None and
        config_data['deep_research'][0] is not None
    )
    
    if all_set:
        print(f"\n--- 現在の設定 ---")
        print(f"  [座標]")
        print(f"    入力エリア: {config_data['input_field']}")
        print(f"    送信ボタン: {config_data['submit_button']}")
        print(f"    コピーボタン: {config_data['copy_button']}")
        print(f"    スクロール位置: {config_data['scroll_focus']}")
        print(f"  [モード]")
        print(f"    Normal: {config_data['normal_search']}")
        print(f"    Deep: {config_data['deep_research']}")
        print(f"  [待機設定]")
        print(f"    回答待ち時間: {config_data['wait_time']}s")
        print(f"    ブラウザ読み込み: {config_data['browser_load_time']}s")
        print(f"    貼り付け後待機: {config_data['paste_delay']}s")
        
        choice = input("\nこの設定で実行しますか？ (y=はい / n=座標を再設定): ").strip().lower()
        if choice == 'y':
            return config_data
    
    # Set up coordinates
    print("\n--- 座標設定モード ---")
    print("各ボタンの位置を順番に設定します。")
    
    x, y = get_position("入力フィールド(Ask anything...)")
    config_data['input_field'] = (x, y)
    
    x, y = get_position("検索ボタン(→アイコン)")
    config_data['submit_button'] = (x, y)
    
    x, y = get_position("回答のコピーボタン(回答生成後のアイコン)")
    config_data['copy_button'] = (x, y)
    
    x, y = get_position("スクロール用フォーカス解除位置(画面上の何もない場所)")
    config_data['scroll_focus'] = (x, y)
    
    x, y = get_position("Normal検索ボタン")
    config_data['normal_search'] = (x, y)
    
    x, y = get_position("Deep Researchボタン")
    config_data['deep_research'] = (x, y)
    
    wait_str = input("回答待ち時間を設定してください (秒): ").strip()
    if wait_str.isdigit():
        config_data['wait_time'] = int(wait_str)
    
    save_config(config_data)
    return config_data

def select_search_mode():
    """Select search mode."""
    print("\n検索モードを選択してください:")
    print("1: Normal検索")
    print("2: Deep Research")
    while True:
        choice = input("選択 (1 または 2): ").strip()
        if choice == '1':
            return 'normal'
        elif choice == '2':
            return 'deep'
        else:
            print("1または2で選択してください。")

def submit_to_perplexity(prompt_parts):
    """
    Submits the prompt(s) to Perplexity using pyautogui.
    prompt_parts can be a string, list, or dict.
    """
    if isinstance(prompt_parts, str):
        prompt_parts = {"プロンプト": prompt_parts}
    elif isinstance(prompt_parts, list):
        prompt_parts = {f"パーツ {i+1}": p for i, p in enumerate(prompt_parts)}
        
    print("Perplexityに送信します...")
    total_len = sum(len(p) for p in prompt_parts.values())
    print(f"プロンプト合計長: {total_len}文字 (分割数: {len(prompt_parts)})")
    
    # Get coordinates
    config_data = setup_coordinates()
    
    # Select search mode
    search_mode = select_search_mode()
    
    # Open Perplexity in default browser (Brave)
    print(f"Perplexityを開いています: {PERPLEXITY_URL}")
    webbrowser.open(PERPLEXITY_URL)
    
    # Wait for browser to load
    load_time = config_data['browser_load_time']
    print(f"ブラウザの読み込みを待機中 ({load_time}秒)...")
    time.sleep(load_time)
    
    # Click search mode button
    if search_mode == 'normal':
        mode_pos = config_data['normal_search']
        print(f"Normal検索モードをクリック中 ({mode_pos[0]}, {mode_pos[1]})...")
    else:
        mode_pos = config_data['deep_research']
        print(f"Deep Researchモードをクリック中 ({mode_pos[0]}, {mode_pos[1]})...")
    
    pyautogui.click(mode_pos[0], mode_pos[1])
    time.sleep(1)
    
    # Click at the input field position
    input_pos = config_data['input_field']
    print(f"入力フィールドをクリック中 ({input_pos[0]}, {input_pos[1]})...")
    pyautogui.click(input_pos[0], input_pos[1])
    time.sleep(0.3)
    pyautogui.click(input_pos[0], input_pos[1])
    time.sleep(2)
    
    # Paste each part
    for title, content in prompt_parts.items():
        print(f"「{title}」を貼り付け中...")
        pyperclip.copy(content)
        time.sleep(0.5)
        
        pyautogui.keyDown('command')
        time.sleep(0.1)
        pyautogui.press('v')
        time.sleep(0.1)
        pyautogui.keyUp('command')
        
        # Small delay between pastes
        time.sleep(1)
    
    # Wait for all pastes to complete
    paste_delay = config_data['paste_delay']
    print(f"貼り付け完了を待機中 ({paste_delay}秒)...")
    time.sleep(paste_delay)
    
    # Click submit button
    submit_pos = config_data['submit_button']
    print(f"検索ボタンをクリック中 ({submit_pos[0]}, {submit_pos[1]})...")
    pyautogui.click(submit_pos[0], submit_pos[1])
    
    print("検索を実行しました！")
    
    # Automatic post-submission sequence
    wait_sec = config_data['wait_time']
    print(f"\n回答生成を待機中 ({wait_sec}秒)...")
    for i in range(wait_sec, 0, -1):
        print(f"残り: {i}秒 ", end='\r')
        time.sleep(1)
    print("\n待機完了。")
    
    # Click neutral area to lose focus from input field
    scroll_focus_pos = config_data['scroll_focus']
    print(f"フォーカスを外すため指定位置をクリック中 ({scroll_focus_pos[0]}, {scroll_focus_pos[1]})...")
    pyautogui.click(scroll_focus_pos[0], scroll_focus_pos[1])
    time.sleep(0.5)
    
    # Scroll to bottom
    print("一番下までスクロール中...")
    pyautogui.press('end')
    time.sleep(3)
    
    # Click copy button
    copy_pos = config_data['copy_button']
    print(f"コピーボタンをクリック中 ({copy_pos[0]}, {copy_pos[1]})...")
    pyautogui.click(copy_pos[0], copy_pos[1])
    time.sleep(0.5)
    
    print("回答をコピーしました！")
    
    response = pyperclip.paste()
    
    if not response:
        return "エラー: クリップボードが空でした。"
    
    # Clean up response preamble
    # The template starts with titles like "作業日報 YY-MM-DD" or similar.
    # We look for the first occurrence of "# 作業日報" or simply "作業日報" to find the start.
    target_marker = "作業日報"
    if target_marker in response:
        start_index = response.find(target_marker)
        # If there's a '#' before it, include it.
        if start_index > 0 and response[start_index-1] == "#":
            start_index -= 1
        
        print(f"回答から導入文を検出しました。キーワード '{target_marker}' 以降を抽出します。")
        response = response[start_index:].strip()
    
    return response

def submit_to_gemini(prompt, prompt_file_path=None):
    """Wrapper function for backward compatibility."""
    return submit_to_perplexity(prompt)

if __name__ == "__main__":
    if os.path.exists(PROMPT_FILE_PATH):
        with open(PROMPT_FILE_PATH, 'r', encoding='utf-8') as f:
            prompt = f.read()
        print(f"プロンプトファイルを読み込みました: {len(prompt)}文字")
        result = submit_to_perplexity(prompt)
        print("\n--- 回答 ---")
        print(result[:500] + "..." if len(result) > 500 else result)
    else:
        prompt = "Hello! Please tell me a joke."
        print(submit_to_perplexity(prompt))
