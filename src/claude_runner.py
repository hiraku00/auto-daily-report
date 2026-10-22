"""Claude Code の CLI(`claude -p`)で日報を書かせる。

ログイン済みの Claude のサブスクリプションで動くので、API の従量課金はかからない
(使った分はサブスクリプションの使用量に数えられる)。
"""

import os
import shutil
import subprocess

DEFAULT_TIMEOUT = 600


class ClaudeError(RuntimeError):
    """claude コマンドが見つからない、失敗した、時間切れになった。"""


def run_claude(prompt, model=None, timeout=DEFAULT_TIMEOUT):
    """プロンプトを標準入力で渡し、回答のテキストを返す。"""
    if not shutil.which("claude"):
        raise ClaudeError("claude コマンドが見つかりません（Claude Code をインストールしてログインしてください）")

    command = [
        "claude", "-p",
        "--output-format", "text",
        # 文章を書くだけなので、ファイル操作やコマンド実行などのツールとMCPは使わせない
        "--tools", "",
        "--strict-mcp-config",
        # 1日1回の実行が、Claude Code の会話履歴に残らないようにする
        "--no-session-persistence",
    ]
    if model:
        command += ["--model", model]

    # ANTHROPIC_API_KEY があると、サブスクリプションではなく API の従量課金で動いてしまう
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude が {timeout} 秒以内に応答しませんでした") from e
    if result.returncode != 0:
        raise ClaudeError(f"claude が失敗しました（終了コード {result.returncode}）: {(result.stderr or result.stdout).strip()[:500]}")
    if not result.stdout.strip():
        raise ClaudeError("claude の回答が空でした")
    return result.stdout
