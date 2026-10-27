"""演示前重置：把项目恢复成「干净的初始状态」。

为什么需要它：演示前必须清空 outputs/，否则上一轮生成的 CSV / 练习页
会和新产物混在一起，讲到「这次生成了什么」时自己都分不清。同时错词本
的次数会随着每次试跑累积，次数一旦离谱（比如 mitigate 12 次），现场
讲「长期记忆」就像在讲一个坏掉的计数器。

    .venv\\Scripts\\python scripts\\reset_demo.py          # 重置
    .venv\\Scripts\\python scripts\\reset_demo.py --keep   # 只看会动什么

做三件事：
1. outputs/ 下的产物全部删除（保留 .gitkeep）；
2. data/learner_profile.json 恢复为虚构的初始样例；
3. 删除 data/session.json（会话历史）。
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OUTPUT_DIR = ROOT / "outputs"
PROFILE = ROOT / "data" / "learner_profile.json"
SESSION = ROOT / "data" / "session.json"


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def initial_profile() -> dict:
    """与 data/learner_profile.json 的初始样例一致，纯虚构。

    复习日期用相对天数生成，而不是写死日期——每次重置出来的都是
    「一个已到期、一个逾期、一个还没到期」，正好能演示复习调度在挑词。
    """
    return {
        "name": "样例同学",
        "target_exam": "CET-6",
        "level": "B1+",
        "goal": "六周内把外刊精读变成习惯，重点补学术词汇",
        "mistakes": [
            {
                "word": "mitigate",
                "count": 3,
                "first_seen": _day(-12),
                "last_seen": _day(-1),
                "note": "总是和 mediate 混",
                "reps": 0,
                "ease": 2.1,
                "interval": 1,
                "due": _day(0),
            },
            {
                "word": "incentive",
                "count": 2,
                "first_seen": _day(-10),
                "last_seen": _day(-3),
                "note": "知道意思但写不出例句",
                "reps": 1,
                "ease": 2.3,
                "interval": 1,
                "due": _day(-2),
            },
            {
                "word": "cumulative",
                "count": 1,
                "first_seen": _day(-6),
                "last_seen": _day(-4),
                "note": "",
                "reps": 2,
                "ease": 2.55,
                "interval": 3,
                "due": _day(2),
            },
        ],
        "sessions": 2,
        "updated_at": _day(0) + " 21:30:00",
    }


def main() -> None:
    dry = "--keep" in sys.argv

    products = sorted(
        p for p in OUTPUT_DIR.glob("*") if p.is_file() and p.name != ".gitkeep"
    )

    print("将要处理：")
    print(f"  outputs/        {len(products)} 个产物文件")
    for p in products:
        print(f"                  - {p.name}")
    print("  learner_profile 恢复初始样例（错词 3 条，sessions=2）")
    print(f"  session.json    {'存在，将删除' if SESSION.exists() else '不存在，跳过'}")

    if dry:
        print("\n--keep 模式，未做任何改动。")
        return

    for p in products:
        p.unlink()
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / ".gitkeep").touch()

    PROFILE.write_text(
        json.dumps(initial_profile(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if SESSION.exists():
        SESSION.unlink()

    print("\n已重置。现在可以从干净状态开始演示了。")


if __name__ == "__main__":
    main()
