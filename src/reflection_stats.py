"""日報の6節目「予定と振り返り」(src/reflection.py が書き足す)の表を読み、期間の集計を作る。

週・月のサマリ(summary_generator)に渡す数値は、Claude に数えさせず、ここで計算する。
6節目の形は templates/morning_prompt_template.md で決めている:

    ### 予定と実績      | 予定 | 結果 | 状態 |     状態 = 済・一部・未・記録なし・予定外
    ### PCの外の活動    | 時刻 | 活動 | 種類 |     種類 = 食事・外出・買い物・運動・睡眠・連絡・その他
    ### 気になったこと・持ち越し   - [持ち越し] … / - [気がかり] …

dashboard 側の解析(app/lib/daily-report-reflection.ts)と同じ読み方にしている。
"""

import re
from collections import Counter

SECTION_TITLE = "予定と振り返り"
STATUSES = ["済", "一部", "未", "記録なし", "予定外"]
KINDS = ["食事", "外出・買い物", "運動", "睡眠", "連絡", "その他"]
NOTE_RE = re.compile(r"^\s*[-*・]\s+[\[［]\s*(持ち越し|気がかり)\s*[\]］]\s*(.+)$")


def _status(raw):
    text = re.sub(r"\s+", "", raw)
    if "予定外" in text:
        return "予定外"
    if re.search(r"記録なし|不明", text):
        return "記録なし"
    if re.search(r"一部|途中", text):
        return "一部"
    if re.match(r"未|未着手|やらず|やっていない", text):
        return "未"
    if re.search(r"済|完了|達成", text):
        return "済"
    return "記録なし"


def _kind(raw):
    if "食" in raw:
        return "食事"
    if re.search(r"外出|買い物|買物", raw):
        return "外出・買い物"
    if re.search(r"運動|筋トレ|散歩", raw):
        return "運動"
    if re.search(r"睡眠|就寝|起床", raw):
        return "睡眠"
    if "連絡" in raw:
        return "連絡"
    return "その他"


def _table_rows(lines):
    """表の本文の行を、セルの並びで返す(見出し行と区切り行は除く)。"""
    rows = [
        [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        for line in lines
        if line.strip().startswith("|")
    ]
    rows = [cells for cells in rows if not all(re.fullmatch(r":?-+:?", cell) for cell in cells)]
    return rows[1:]  # 1行目は列名


def parse_reflection(body):
    """6節目の本文(見出しの下)から、状態・種類・持ち越し/気がかりを読む。表の形でなければ structured=False。"""
    sections = {"plans": [], "activities": [], "notes": []}
    current = None
    for line in body.split("\n"):
        heading = re.match(r"^###(?!#)\s*(.*)$", line)
        if heading:
            title = heading.group(1)
            current = "plans" if "予定" in title else "activities" if re.search(r"PC|活動", title) else "notes" if re.search(r"持ち越し|気にな|気がかり", title) else None
            continue
        if current:
            sections[current].append(line)

    statuses = [_status(cells[2]) for cells in _table_rows(sections["plans"]) if len(cells) >= 3 and cells[0]]
    kinds = [_kind(cells[2]) for cells in _table_rows(sections["activities"]) if len(cells) >= 3 and cells[1]]
    notes = [(m.group(1), m.group(2).strip()) for m in (NOTE_RE.match(line) for line in sections["notes"]) if m]
    return {
        "statuses": statuses,
        "kinds": kinds,
        "notes": notes,
        "structured": bool(statuses or kinds or notes),
        # 整理された節ではなく本文から読んだ日(「…の本文から」)は、確かさが落ちる
        "raw": bool(re.search(r">\s*モーニングページ[:：].*本文", body)),
    }


def reflection_stats(day_bodies):
    """{日付: 6節目の本文} から、サマリのプロンプトに渡す集計の行を作る。6節目のある日が無ければ空文字。"""
    parsed = {day: parse_reflection(body) for day, body in day_bodies.items() if body.strip()}
    structured = {day: p for day, p in parsed.items() if p["structured"]}
    if not parsed:
        return ""
    statuses, kinds = Counter(), Counter()
    carryovers, concerns = 0, 0
    for p in structured.values():
        statuses.update(p["statuses"])
        kinds.update(p["kinds"])
        carryovers += sum(1 for kind, _ in p["notes"] if kind == "持ち越し")
        concerns += sum(1 for kind, _ in p["notes"] if kind == "気がかり")
    planned = statuses["済"] + statuses["一部"] + statuses["未"] + statuses["記録なし"]
    lines = [f"- 予定と振り返りのある日: {len(parsed)}日（うち表の形で読めた日 {len(structured)}日）"]
    if planned:
        rate = round(statuses["済"] / planned * 100)
        lines.append(
            f"- 予定の達成: 予定{planned}件のうち 済{statuses['済']}・一部{statuses['一部']}・未{statuses['未']}・記録なし{statuses['記録なし']}"
            f"（済の割合 {rate}%）。予定外 {statuses['予定外']}件"
        )
    else:
        lines.append("- 予定の達成: 予定の記録なし")
    if kinds:
        lines.append("- PCの外の活動: " + "、".join(f"{kind}{kinds[kind]}件" for kind in KINDS if kinds[kind]))
    lines.append(f"- 持ち越し {carryovers}件、気がかり {concerns}件")
    raw_days = sum(1 for p in parsed.values() if p["raw"])
    if raw_days:
        lines.append(f"- うち{raw_days}日は整理されていないモーニングページの本文から読んだもので、予定の判定は確かさが低い")
    return "\n".join(lines)


def notes_digest(body):
    """月次のサマリに渡す、6節目の持ち越し・気がかりだけの箇条書き(表は渡さない)。無ければ空文字。"""
    return "\n".join(f"- [{kind}] {text}" for kind, text in parse_reflection(body)["notes"])
