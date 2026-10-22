import json
import os
import subprocess
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import claude_runner
from src.claude_runner import ClaudeError, run_claude
from src.log_digest import build_digest, build_header, find_gaps, load_entries
from src.report_generator import ReportError, build_prompt, finish_report

DATE = "2026-10-21"


def write_log(tmp_path, entries):
    path = tmp_path / f"daily_log_{DATE}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.write("{壊れた行\n")
    return str(tmp_path)


ENTRIES = [
    {"timestamp": "08:06:21", "app_name": "Ghostty", "text_summary": "File Edit gemini.google.com 英単語 英作文"},
    {"timestamp": "08:07:23", "app_name": "Ghostty", "text_summary": "File Edit gemini.google.com 英単語 英作文"},
    {"timestamp": "09:10:00", "app_name": "Ghostty", "text_summary": "File Edit github.com robotics-roadmap CHECKLIST.md"},
    {"timestamp": "09:11:00", "app_name": "Brave", "text_summary": "File Edit github.com robotics-roadmap CHECKLIST.md"},
] + [
    # 全キャプチャに出る「File」「Edit」は決まり文句として除かれ、2ブロックの語は1割未満なので残る
    {"timestamp": f"09:{20 + i}:00", "app_name": "Brave", "text_summary": f"File Edit youtube.com 動画{i}"}
    for i in range(20)
]


def test_load_entries_skips_broken_lines_and_missing_files(tmp_path):
    log_dir = write_log(tmp_path, ENTRIES)
    assert len(load_entries(DATE, log_dir)) == 24
    assert load_entries("2000-01-01", log_dir) == []


def test_header_and_gaps_are_computed_from_timestamps():
    assert build_header(DATE, ENTRIES) == "# 作業日報 26-10-21\n記録期間: 08:06~09:39(約1時間32分)\nキャプチャ回数: 24回"
    assert find_gaps(ENTRIES) == [("08:07", "09:10", 62)]


def test_digest_keeps_domains_and_block_specific_words():
    lines = build_digest(ENTRIES).split("\n")
    assert lines[0].startswith("[08:00 n=2] Ghostty | gemini.google.com | ")
    assert "英単語" in lines[0]
    assert lines[1].startswith("[09:00 n=12] Brave,Ghostty | youtube.com,github.com | ")
    assert "robotics-roadmap" in lines[1]
    assert "File" not in build_digest(ENTRIES)


def test_build_prompt_fills_every_placeholder(tmp_path):
    log_dir = write_log(tmp_path, ENTRIES)
    header, prompt = build_prompt(DATE, log_dir, calendar_text="- 10:00: {DD} の定例")
    assert header.startswith("# 作業日報 26-10-21")
    assert "- 08:07～09:10（1時間2分）" in prompt
    assert "- Brave: 21回" in prompt
    assert "- 10:00: {DD} の定例" in prompt  # 波括弧を置き換え項目と誤解しない(#11)
    for placeholder in ["{date}", "{header}", "{gaps}", "{app_counts}", "{calendar_events}", "{digest}"]:
        assert placeholder not in prompt


def test_build_prompt_without_log_raises(tmp_path):
    with pytest.raises(ReportError):
        build_prompt(DATE, str(tmp_path), calendar_text="")


BODY = "\n".join([
    "## 1. 本日のメイン作業", "### 1.英語学習", "- 学習",
    "## 2. アプリ使用状況", "| アプリ/ツール | 使用回数 | 主な用途 |",
    "## 3. 作業詳細", "| 時間帯 | 作業内容 | 所要時間 |",
    "## 4. 得られた知見･メモ", "- 知見",
    "## 5. 作業中だったファイル", "- dashboard",
])


def test_finish_report_drops_preamble_and_code_fences():
    report = finish_report("# 作業日報 26-10-21", f"日報を作成します。\n\n```markdown\n{BODY}\n```\n")
    assert report == f"# 作業日報 26-10-21\n\n{BODY}\n"


def test_finish_report_rejects_answers_without_all_sections():
    with pytest.raises(ReportError):
        finish_report("# h", "すみません、作れませんでした。")
    with pytest.raises(ReportError):
        finish_report("# h", BODY.split("## 5.")[0])


def test_run_claude_uses_subscription_and_no_tools(monkeypatch):
    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="## 1. 本日のメイン作業\n", stderr="")

    monkeypatch.setattr(claude_runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert run_claude("prompt", model="sonnet") == "## 1. 本日のメイン作業\n"
    command = calls["command"]
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--tools") + 1] == ""
    assert command[-2:] == ["--model", "sonnet"]
    assert calls["kwargs"]["input"] == "prompt"
    assert "ANTHROPIC_API_KEY" not in calls["kwargs"]["env"]


def test_run_claude_reports_failures(monkeypatch):
    monkeypatch.setattr(claude_runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(claude_runner.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1, stdout="", stderr="not logged in"))
    with pytest.raises(ClaudeError, match="not logged in"):
        run_claude("prompt")
    monkeypatch.setattr(claude_runner.shutil, "which", lambda name: None)
    with pytest.raises(ClaudeError):
        run_claude("prompt")
