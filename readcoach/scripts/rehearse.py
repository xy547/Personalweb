"""演示话术前彩排脚本。

按 README 里的推荐话术逐条跑一遍，把工具调用轨迹、最终回复、耗时写进
logs/rehearse_<时间戳>.md。用途有两个：

1. 演示前自查：确认每条话术的预期效果还成立（尤其第 5 条拒绝代写）；
2. 出问题时有据可查：哪一步工具没被调用、哪一轮回复跑偏了。

用法：
    .venv\\Scripts\\python scripts\\rehearse.py            # 全部话术
    .venv\\Scripts\\python scripts\\rehearse.py 5           # 只跑第 5 条
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from agent.graph import get_graph  # noqa: E402
from agent.prompts import build_system_prompt  # noqa: E402

RECURSION_LIMIT = 60
LOG_DIR = ROOT / "logs"

# 第 6 条话术要用的「用户自贴文章」。故意换一个和内置示例完全不同的主题，
# 这样才能看出模型读的是贴进来的这篇，而不是又去读 demo/。
SAMPLE_ARTICLE = """Why We Forget What We Read

Most students treat reading as a transfer of information: the eyes pass over the
page, the brain records what it sees, and the knowledge stays. Cognitive research
suggests otherwise. Comprehension is not a passive receipt but an active
reconstruction, and memory for what we read decays within days unless it is
retrieved.

The implication is uncomfortable. Highlighting feels productive because it is
visible, yet it leaves no durable trace. Retrieval practice, by contrast, feels
laborious and often fails in the moment, which is precisely why it works.

A second finding concerns coherence. Readers who pause to summarise a paragraph
in their own words retain materially more than those who reread it twice. The
effort of compression forces the reader to discriminate between what the argument
depends on and what merely decorates it.

None of this requires new technology. It requires a willingness to be tested,
which almost nobody enjoys."""

# 顺序与现场演示一致：主路径 → 工具单调用 → 读记忆 → 写记忆 → 边界。
# 「先读后写」不能反：写记忆会让次数变化，先写再读就看不出记忆是真的被读过。
CASES = [
    (1, "主路径", "帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词"),
    (2, "工具单调用", "把这几个词做成一份 CSV 词表，我要导到 Excel 里背：mitigate, incentive, cumulative, viable"),
    (3, "读长期记忆", "我的错词本里现在有哪些词？"),
    (4, "写长期记忆", "我这次又把 mitigate 和 incentive 记混了，帮我记下来"),
    (5, "边界：拒绝代写", "帮我把这篇文章翻译成中文，我要抄到作业里交"),
    (6, "自贴文章", "我贴了一篇新的英文原文（在当前文章槽里），帮我精读，挑 6 个 CET-6 生词，生成词表和练习页"),
    (7, "复习调度", "今天该复习哪几个词？用它们给我出一道挖空练习"),
]


def run_case(idx: int, label: str, query: str) -> dict:
    if idx == 6:
        # 走 load_text 这条路：先把正文写进文章槽，再由模型自己取。
        from tools.reader import save_user_article

        save_user_article(SAMPLE_ARTICLE)
    graph = get_graph()
    msgs = [SystemMessage(content=build_system_prompt(query)), HumanMessage(content=query)]

    trace: list[str] = []
    tool_names: list[str] = []
    final, steps = "", 0
    t0 = time.time()

    try:
        for update in graph.stream(
            {"messages": msgs},
            config={"recursion_limit": RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for _node, payload in update.items():
                for m in payload.get("messages", []):
                    steps += 1
                    calls = getattr(m, "tool_calls", None) or []
                    if calls:
                        for c in calls:
                            tool_names.append(c["name"])
                            trace.append(
                                f"→ {c['name']}({json.dumps(c['args'], ensure_ascii=False)[:150]})"
                            )
                    elif type(m).__name__ == "ToolMessage":
                        trace.append(f"← {m.name} · {str(m.content)[:120]}")
                    elif getattr(m, "content", ""):
                        final = m.content
    except Exception as e:  # noqa: BLE001
        final = f"[异常] {type(e).__name__}: {e}"

    return {
        "idx": idx,
        "label": label,
        "query": query,
        "steps": steps,
        "elapsed": round(time.time() - t0, 1),
        "tools": dict(Counter(tool_names)),
        "trace": trace,
        "final": final,
    }


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = []

    for idx, label, query in CASES:
        if only and str(idx) != only:
            continue
        print(f"\n{'=' * 60}\n[{idx}] {label}：{query}\n{'=' * 60}")
        r = run_case(idx, label, query)
        results.append(r)
        print(f"工具调用：{r['tools'] or '无'} | {r['steps']} 步 | {r['elapsed']}s")
        for line in r["trace"]:
            print("  " + line)
        print(f"回复：{r['final'][:400]}")
        time.sleep(2)

    if not results:
        print("没有匹配的话术编号。")
        return

    LOG_DIR.mkdir(exist_ok=True)
    out = LOG_DIR / f"rehearse_{datetime.now():%Y%m%d_%H%M%S}.md"
    lines = [f"# 话术彩排记录 {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for r in results:
        lines += [
            f"## [{r['idx']}] {r['label']}",
            "",
            f"**话术**：{r['query']}",
            "",
            f"**工具调用**：`{r['tools'] or '无'}`　**步数**：{r['steps']}　**耗时**：{r['elapsed']}s",
            "",
            "**轨迹**：",
            "```",
            *r["trace"],
            "```",
            "",
            "**回复**：",
            "",
            r["final"],
            "",
            "---",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n日志已写入：{out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
