"""1日分の作業ログ(jsonl)を、日報を書くのに必要な分だけに要約する。

画面OCRの全文は1日で数百KBになり、そのままではLLMに渡せない(上限に当たり、使用量も大きい)。
30分ごとのブロックに分け、訪問したドメインと、その日の中でそのブロックに特徴的な語だけを残す。
日報の見出し(記録期間・キャプチャ回数)とログ欠落は、LLMに数えさせずにここで正確に計算する。
"""

import collections
import json
import os
import re

LOG_DIR = "logs"
BLOCK_SECONDS = 30 * 60
GAP_SECONDS = 30 * 60
# その日の全キャプチャの1割より多くに出てくる語は、メニューバーなどの決まり文句として除く
COMMON_TOKEN_RATIO = 0.10
WORDS_PER_BLOCK = 12
DOMAINS_PER_BLOCK = 4

DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+(?:com|jp|net|org|io|dev|co\.jp|ai|app|me|tv|co|info|us))(?:/[^\s]{0,40})?",
    re.I,
)


def load_entries(date_str, log_dir=LOG_DIR):
    """daily_log_YYYY-MM-DD.jsonl を読む。壊れた行は飛ばす。ファイルが無ければ空のリスト。"""
    path = os.path.join(log_dir, f"daily_log_{date_str}.jsonl")
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and _seconds(entry.get("timestamp")) is not None:
                entries.append(entry)
    return entries


def _seconds(timestamp):
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", str(timestamp or ""))
    if not match:
        return None
    hours, minutes, seconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _hhmm(seconds):
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def find_gaps(entries, min_seconds=GAP_SECONDS):
    """キャプチャの間隔が min_seconds 以上空いた区間を (開始HH:MM, 終了HH:MM, 分) で返す。"""
    times = [_seconds(e["timestamp"]) for e in entries]
    return [
        (_hhmm(a), _hhmm(b), (b - a) // 60)
        for a, b in zip(times, times[1:])
        if b - a >= min_seconds
    ]


def build_header(date_str, entries):
    """日報の先頭3行。記録期間は最初と最後のキャプチャの時刻から計算する。"""
    first = _seconds(entries[0]["timestamp"])
    last = _seconds(entries[-1]["timestamp"])
    minutes = (last - first) // 60
    return (
        f"# 作業日報 {date_str[2:]}\n"
        f"記録期間: {_hhmm(first)}~{_hhmm(last)}(約{minutes // 60}時間{minutes % 60:02d}分)\n"
        f"キャプチャ回数: {len(entries)}回"
    )


def app_counts(entries):
    """記録上のアプリ名ごとのキャプチャ回数(多い順)。"""
    return collections.Counter(e.get("app_name") or "Unknown" for e in entries).most_common()


def build_digest(entries):
    """30分ごとのブロックの要約。1行 = `[HH:MM n=キャプチャ数] アプリ | ドメイン | 特徴的な語`。"""
    if not entries:
        return ""
    tokens = [set(str(e.get("text_summary", "")).split()) for e in entries]
    document_frequency = collections.Counter(t for words in tokens for t in words)
    common = {t for t, c in document_frequency.items() if c > COMMON_TOKEN_RATIO * len(entries)}

    blocks = collections.defaultdict(list)
    for index, entry in enumerate(entries):
        blocks[_seconds(entry["timestamp"]) // BLOCK_SECONDS].append(index)

    lines = []
    for block in sorted(blocks):
        indexes = blocks[block]
        apps = collections.Counter(entries[i].get("app_name") or "Unknown" for i in indexes)
        domains = collections.Counter()
        words = collections.Counter()
        for i in indexes:
            text = str(entries[i].get("text_summary", ""))
            for domain in {d.lower() for d in DOMAIN_RE.findall(text)}:
                domains[domain] += 1
            for token in tokens[i] - common:
                if len(token) >= 3 and not re.fullmatch(r"[\W\d_]+", token):
                    words[token] += 1
        top_words = [t for t, c in words.most_common(40) if c >= 2][:WORDS_PER_BLOCK]
        lines.append(
            f"[{_hhmm(block * BLOCK_SECONDS)} n={len(indexes)}] "
            f"{','.join(a for a, _ in apps.most_common(2))} | "
            f"{','.join(d for d, _ in domains.most_common(DOMAINS_PER_BLOCK))} | "
            f"{' '.join(top_words)}"
        )
    return "\n".join(lines)
