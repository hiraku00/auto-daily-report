"""Claude Code の CLI(`claude -p`)で日報を書かせる。

ログイン済みの Claude のサブスクリプションで動くので、API の従量課金はかからない
(使った分はサブスクリプションの使用量に数えられる)。
"""

import os
import shutil
import subprocess

DEFAULT_TIMEOUT = 600

# `claude setup-token` で作った長期トークンを入れておく、macOS キーチェーンの項目名
KEYCHAIN_SERVICE = "auto-daily-report-claude-oauth-token"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"


class ClaudeError(RuntimeError):
    """claude コマンドが見つからない、失敗した、時間切れになった。"""


def keychain_token():
    """キーチェーンに保存した長期トークンを返す。無ければ（macOS 以外も）None。"""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = result.stdout.strip()
    return token if result.returncode == 0 and token else None


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
    # Claude Code の通常のログインは、更新に失敗して切れることがある。
    # 長期トークンがキーチェーンにあればそちらを使う（環境変数で渡されていればそれを優先）
    if not env.get(TOKEN_ENV):
        token = keychain_token()
        if token:
            env[TOKEN_ENV] = token
    try:
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude が {timeout} 秒以内に応答しませんでした") from e
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()[:500]
        if "authenticate" in message.lower() or "oauth" in message.lower():
            message += (
                "\n→ `claude setup-token` で長期トークンを作り、"
                f"`security add-generic-password -U -a \"$USER\" -s {KEYCHAIN_SERVICE} -w` でキーチェーンに保存してください（README 参照）"
            )
        raise ClaudeError(f"claude が失敗しました（終了コード {result.returncode}）: {message}")
    if not result.stdout.strip():
        raise ClaudeError("claude の回答が空でした")
    return result.stdout
