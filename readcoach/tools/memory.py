"""工具四：把复习结果写进学习者档案（长期记忆 + 复习调度）。

记忆不是让模型「记住聊天内容」，而是落成一份可读、可改、可版本管理的 JSON。
下一次会话开始时，这份档案会被拼进系统提示词，于是 Agent 知道
「这个人考 CET-6、上次栽在 mitigation 和 incentive 上」。

这里还有第二个职责：**复习调度**（简化版 SM-2）。
只记「这个词错了 3 次」是没用的。同类软件真正的护城河不是词典，
而是「这个词该在哪天重新出现在你面前」。所以每个词条除了 count，
还带四个字段：

    interval  当前间隔（天）
    ease      难度系数（越难越小，1.3 封底）
    due       下次该复习的日期
    reps      连续答对次数

    答错 → reps 归零，ease 降 0.2，间隔回到 1 天（明天再来）
    答对 → reps+1，ease 升 0.05，间隔按 1 → 3 → 上次×ease 递增

关键点：日期完全由代码算，模型没有能力自己说「这个词七天后复习」。
它只能引用工具返回的 due 字段——和考纲等级、音标是同一套纪律。
"""

import json
import re
from datetime import date, datetime, timedelta

from langchain_core.tools import tool

from config import DATA_DIR

PROFILE_PATH = DATA_DIR / "learner_profile.json"

EASE_DEFAULT = 2.5
EASE_MIN = 1.3
EASE_MAX = 3.0


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_profile(profile: dict) -> None:
    profile["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PROFILE_PATH.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _today() -> date:
    return date.today()


def _clean(tokens: str) -> list[str]:
    return [
        t.strip().lower().strip(".,!?;:\"'()[]")
        for t in re.split(r"[,\n|、;；\s]+", tokens or "")
        if t.strip()
    ]


def _new_entry(word: str, note: str = "") -> dict:
    return {
        "word": word,
        "count": 1,
        "first_seen": _today().isoformat(),
        "last_seen": _today().isoformat(),
        "note": note,
        "reps": 0,
        "ease": EASE_DEFAULT,
        "interval": 0,
        "due": _today().isoformat(),
    }


def _ensure_fields(entry: dict) -> dict:
    """老档案里没有调度字段的补上，due 设为今天——从没排过期的词，今天就该复习。"""
    entry.setdefault("count", 1)
    entry.setdefault("reps", 0)
    entry.setdefault("ease", EASE_DEFAULT)
    entry.setdefault("interval", 0)
    entry.setdefault("due", _today().isoformat())
    return entry


def _mark_fail(entry: dict) -> None:
    entry["reps"] = 0
    entry["ease"] = max(EASE_MIN, round(float(entry["ease"]) - 0.2, 2))
    entry["interval"] = 1
    entry["due"] = (_today() + timedelta(days=1)).isoformat()
    entry["last_seen"] = _today().isoformat()


def _mark_pass(entry: dict) -> None:
    reps = int(entry["reps"]) + 1
    ease = min(EASE_MAX, round(float(entry["ease"]) + 0.05, 2))
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 3
    else:
        interval = max(1, round(int(entry["interval"]) * ease or ease))
    entry.update(
        reps=reps,
        ease=ease,
        interval=interval,
        due=(_today() + timedelta(days=interval)).isoformat(),
        last_seen=_today().isoformat(),
    )


def due_words(limit: int = 8) -> list[dict]:
    """今天到期（due ≤ 今天）的词，最久没复习的排前面。给提示词用，不是工具。"""
    profile = load_profile()
    today = _today()
    due = []
    for raw in profile.get("mistakes", []):
        entry = _ensure_fields(dict(raw))
        try:
            due_date = date.fromisoformat(str(entry["due"])[:10])
        except (ValueError, TypeError):
            due_date = today
        if due_date <= today:
            due.append(entry)
    due.sort(key=lambda e: (str(e["due"]), -int(e.get("count", 1))))
    return due[:limit]


@tool
def record_mistakes(words: str = "", note: str = "", known: str = "") -> str:
    """记录这一轮复习的结果，写进本地错词本并排好下次复习日期。

    两个参数各管一边：
    - words：这一轮**没记住**的词，逗号分隔，例如 "mitigate,incentive"。
      这些词的复习间隔会作废，明天重来。
    - known：这一轮**确认记住了**的词，逗号分隔，例如 "cumulative"。
      这些词的复习间隔会按 1 天 → 3 天 → 上次×难度系数 往后推。
    - note：可选，一句话说明错在哪，例如「混淆了 mitigate 和 mediate」。

    只有用户明确表达了「没记住 / 记住了 / 又错了」时才调用。
    用户只是让你生成材料，不要顺手记录。
    """
    fail_words = _clean(words)
    pass_words = [w for w in _clean(known) if w not in fail_words]
    if not fail_words and not pass_words:
        return (
            "ERROR: words 和 known 都是空的，没有记录任何词。"
            "没记住的词填 words，记住了的填 known。"
        )

    profile = load_profile()
    book = {
        m["word"]: _ensure_fields(dict(m))
        for m in profile.get("mistakes", [])
        if "word" in m
    }

    added, bumped, advanced = [], [], []
    for w in fail_words:
        if w in book:
            book[w]["count"] = int(book[w].get("count", 1)) + 1
            if note.strip():
                book[w]["note"] = note.strip()
            bumped.append(w)
        else:
            book[w] = _new_entry(w, note.strip())
            added.append(w)
        _mark_fail(book[w])

    for w in pass_words:
        if w not in book:
            book[w] = _new_entry(w, note.strip())
            added.append(w)
        _mark_pass(book[w])
        advanced.append(w)

    profile["mistakes"] = sorted(
        book.values(), key=lambda m: (-int(m.get("count", 1)), m["word"])
    )
    profile["sessions"] = int(profile.get("sessions", 0)) + 1
    save_profile(profile)

    schedule = {
        m["word"]: {
            "due": m["due"],
            "interval_days": m["interval"],
            "ease": m["ease"],
            "reps": m["reps"],
            "count": m["count"],
        }
        for m in profile["mistakes"]
        if m["word"] in fail_words or m["word"] in pass_words
    }
    due_today = [e["word"] for e in due_words(limit=99)]

    return json.dumps(
        {
            "status": "ok",
            "added": added,
            "bumped": bumped,
            "advanced": advanced,
            "total_in_notebook": len(profile["mistakes"]),
            "schedule": schedule,
            "due_today": due_today,
            "top_weak_words": [m["word"] for m in profile["mistakes"][:5]],
            # 只给词名不够：系统提示词里的档案是「本轮开始前」的快照，
            # 模型拿旧快照报次数会慢一格（实测报 4 次、实际已 5 次）。
            # 这里把写盘后的准确次数一并给出，回复数字才不会说谎。
            "counts": {m["word"]: int(m.get("count", 1)) for m in profile["mistakes"]},
            "written_to": "data/learner_profile.json",
            "integration": "仅写入本地 JSON 档案；本项目没有接入任何 App、"
            "游戏或云端词库服务，也没有写入任何外部数据库。若用户想要可导入的"
            "词表，需另外调用 make_wordlist_csv 产出 CSV。",
            "reply_rule": "只能如实说「已记进本地错词本档案」并引用 schedule 里的"
            "due 日期；不得声称已同步到 App、已导入某款软件或打开就能看见；"
            "不得自己推算复习日期（例如说「七天后」），日期只能抄 due 字段；"
            "次数以 counts 字段为准，不要用提示词里的旧档案推算。",
        },
        ensure_ascii=False,
    )
