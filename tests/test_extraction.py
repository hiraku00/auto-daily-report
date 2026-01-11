import sys
import os

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.perplexity_automator import clean_response

def test_clean_response():
    cases = [
        # 標準的なケース: # とスペースあり
        ("Here is the report:\n\n# 作業日報 2024-01-11", "# 作業日報 2024-01-11"),
        # # の直後にキーワード
        ("導入文です。\n#作業日報 2024-01-11", "#作業日報 2024-01-11"),
        # ## ヘッダー
        ("Preamble\n## 作業日報", "## 作業日報"),
        # キーワードのみ（ヘッダーなし）
        ("回答:\n作業日報 2024-01-11", "作業日報 2024-01-11"),
        # 行頭にスペースがある場合（インデント等）
        ("Preamble\n   # 作業日報", "# 作業日報"),
        # 前後に余計な改行
        ("\n\n# 作業日報\n\n", "# 作業日報"),
        # キーワードが含まれない場合
        ("普通のテキスト", "普通のテキスト"),
        # 空入力
        ("", "エラー: クリップボードが空でした。")
    ]
    
    success_count = 0
    for i, (input_str, expected) in enumerate(cases):
        actual = clean_response(input_str)
        if actual == expected:
            print(f"Case {i} PASS")
            success_count += 1
        else:
            print(f"Case {i} FAIL")
            print(f"  Input: {repr(input_str)}")
            print(f"  Expected: {repr(expected)}")
            print(f"  Actual:   {repr(actual)}")
    
    print(f"\nResult: {success_count}/{len(cases)} passed")
    return success_count == len(cases)

if __name__ == "__main__":
    if test_clean_response():
        sys.exit(0)
    else:
        sys.exit(1)
