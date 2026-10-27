"""外刊精读教练 —— Streamlit 界面入口。

界面只做三件事：接收一句话、把 Agent 的每一步摊开给用户看、把产出文件交出去。
业务逻辑全在 agent/ 和 tools/ 里，这里不写任何提示词或工具实现。
"""

import json
import os
import re
from datetime import date
from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import config
from agent import languages as langs
from agent.graph import get_graph
from agent.prompts import build_system_prompt
from tools import daily
from tools.memory import due_words, load_profile, save_profile
from tools.reader import load_user_article, save_user_article

SESSION_FILE = config.DATA_DIR / "session.json"

# 每个语种一套演示话术。语种一换，话术里的等级、词例都得跟着换——
# 否则切成日语还弹「挑 10 个 CET-6 生词」，一眼就是没做适配。
DEMO_BY_LANG = {
    "en": [
        "帮我精读 demo 里那篇校园碳排的文章，挑出 10 个 CET-6 生词",
        "把这几个词做成一份 CSV 词表，我要导到 Excel 里背：mitigate, incentive, cumulative",
        "生成一份精读练习页，把这些词在原文里挖空",
        "我这次又把 mitigate 和 incentive 记混了，帮我记下来",
        "今天该复习哪几个词？用它们给我出一道挖空练习",
    ],
    "ja": [
        "帮我精读今天推送的日语文章，挑出 6 个 JLPT N3 生词",
        "把这几个词做成一份词表：影響、課題、取り組む",
        "生成一份精读练习页，把这些词在原文里挖空",
        "我又把 影響 和 影響力 记混了，帮我记下来",
        "今天该复习哪几个词？用它们给我出一道挖空练习",
    ],
    "fr": [
        "帮我精读今天推送的法语文章，挑出 6 个 DELF B1 生词",
        "把这几个词做成一份词表：mesure、enjeu、davantage",
        "生成一份精读练习页，把这些词在原文里挖空",
        "我又把 enjeu 和 jeu 记混了，帮我记下来",
        "今天该复习哪几个词？用它们给我出一道挖空练习",
    ],
    "de": [
        "帮我精读今天推送的德语文章，挑出 6 个 Goethe B1 生词",
        "把这几个词做成一份词表：Maßnahme、Vorbereitung、nachhaltig",
        "生成一份精读练习页，把这些词在原文里挖空",
        "我又把 Maßnahme 和 Massnahme 记混了，帮我记下来",
        "今天该复习哪几个词？用它们给我出一道挖空练习",
    ],
    "es": [
        "帮我精读今天推送的西语文章，挑出 6 个 DELE B1 生词",
        "把这几个词做成一份词表：medida、preparativo、sostenible",
        "生成一份精读练习页，把这些词在原文里挖空",
        "我又把 medida 和 mediada 记混了，帮我记下来",
        "今天该复习哪几个词？用它们给我出一道挖空练习",
    ],
}


def demo_prompts(code: str) -> list[str]:
    return DEMO_BY_LANG.get(code, DEMO_BY_LANG["en"])

MIME = {
    ".csv": "text/csv",
    ".html": "text/html",
    ".md": "text/markdown",
    ".json": "application/json",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 模型在回复里只会写 `outputs/xxx.csv` 这种相对路径。用户拿这段去资源管理器里找，
# 必然找不到（没有盘符），于是反馈「生成的文件打不开」。
# 所以：① 工具回传 absolute_path；② 这里把回复里点名的文件就地挂成按钮。
OUTPUT_NAME_RE = re.compile(r"outputs[\\/]([^\\/\s`'\"()（）]+\.(?:csv|html|md|docx))")

# 匹配「任何看起来像产物路径的串」，前面允许出现盘符或 /home/ubuntu 这类前缀。
ANY_OUTPUT_PATH_RE = re.compile(
    r"[^\s`'\"（）()]*outputs[\\/][^\s`'\"（）()\\/]+\.(?:csv|html|md|docx)", re.I
)


def snapshot_outputs() -> dict:
    """记录产物目录当前的名字→修改时间，用来判断本轮到底写了没有。"""
    if not config.OUTPUT_DIR.exists():
        return {}
    return {
        p.name: p.stat().st_mtime
        for p in config.OUTPUT_DIR.glob("*")
        if p.is_file() and p.name != ".gitkeep"
    }


def normalize_output_paths(text: str) -> str:
    """把回复里写的产物路径，换成磁盘上真实存在的绝对路径。

    实测模型会写 `/home/ubuntu/outputs/xxx.csv`——那是它训练数据里的容器路径，
    本机根本没有这个目录。工具明明回传了 `absolute_path`，它还是会照着旧习惯编。
    这种错误不能靠提示词，只能在出口处做一次确定性替换。
    """
    if not text:
        return text

    def _fix(m):
        name = Path(m.group(0)).name
        real = config.OUTPUT_DIR / name
        return str(real) if real.is_file() else m.group(0)

    return ANY_OUTPUT_PATH_RE.sub(_fix, text)


def list_outputs(limit: int = 10) -> list:
    """按修改时间倒序列出 outputs/ 里的产物（不含 .gitkeep 与 Word 锁文件）。"""
    if not config.OUTPUT_DIR.exists():
        return []
    files = [
        p
        for p in config.OUTPUT_DIR.glob("*")
        # ~$xxx 是 Word/Excel 打开文件时生成的锁文件，用户点它没意义
        if p.is_file() and p.name != ".gitkeep" and not p.name.startswith("~$")
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def open_in_explorer(path=None) -> None:
    """用系统默认程序打开文件；传目录则在资源管理器里定位。失败不抛异常。"""
    target = str(path or config.OUTPUT_DIR)
    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
        else:  # 非 Windows 只做兜底，课程演示机是 Windows
            import subprocess

            subprocess.Popen(["xdg-open", target])
    except Exception:
        st.caption(f"系统没能自动打开，请手动打开：{target}")


def attach_outputs(text: str, key_prefix: str) -> None:
    """把回复里提到的产物做成「下载 / 直接打开」两个按钮。

    这是「文件名打不开」的直接解法：文件已经写到磁盘上了，
    但用户从聊天里拿到的是一个没人能点的字符串。
    """
    names: list[str] = []
    for m in OUTPUT_NAME_RE.finditer(text or ""):
        name = m.group(1)
        if name not in names:
            names.append(name)

    shown = 0
    for name in names:
        path = config.OUTPUT_DIR / name
        if not path.is_file():
            continue
        col_dl, col_open = st.columns([2, 1])
        with col_dl:
            st.download_button(
                label=f"⬇ 下载 {name}",
                data=path.read_bytes(),
                file_name=name,
                mime=MIME.get(path.suffix.lower(), "application/octet-stream"),
                use_container_width=True,
                key=f"{key_prefix}_dl_{shown}",
            )
        with col_open:
            if st.button(
                "↗ 直接打开",
                key=f"{key_prefix}_op_{shown}",
                use_container_width=True,
                help="用 Excel / 浏览器打开这个文件",
            ):
                open_in_explorer(path)
        st.caption(f"完整路径：`{path}`")
        shown += 1

# 一次工具调用要吃掉 2 个超步（agent 一步 + tools 一步）。
# 主路径是「读文章 + 8 次查词 + 词表 + 练习页」= 11 次工具调用 = 22 步以上。
# 这里曾经设成 15，结果跑到第 7 次工具调用就抛 GraphRecursionError：
# 界面上只显示半截轨迹、助手回复也没写回会话，而且异常类型不直观，很难查。
# 留足余量设成 60，够 30 次工具调用。
RECURSION_LIMIT = 60

st.set_page_config(page_title="外刊精读教练", page_icon="📖", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 1180px; }
      .step-line { font-size: 13px; color: #4b5563; margin: 2px 0; }
      .step-line code { background: #eef2ff; color: #1d4ed8; padding: 1px 6px; border-radius: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_session() -> list:
    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            return [m for m in data if m.get("role") in ("user", "assistant")]
        except json.JSONDecodeError:
            return []
    return []


def save_session(messages: list) -> None:
    SESSION_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clip(text, limit: int = 240) -> str:
    t = str(text or "").replace("\n", " ").strip()
    return t if len(t) <= limit else t[:limit] + " …"


def friendly_error(exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    low = detail.lower()
    if "recursion" in low:
        return (
            "调用失败：这一轮工具调用次数超出上限，Agent 被强制中断。\n\n"
            "可以把任务拆小一点（比如一次只挑 4 个词），"
            "或调大 app.py 里的 RECURSION_LIMIT。"
        )
    if "401" in low or "invalid_api_key" in low or "unauthorized" in low:
        return (
            "调用失败：API Key 无效或已过期（401）。\n\n"
            "请打开项目根目录的 .env，确认 DASHSCOPE_API_KEY 是完整的一串，"
            "保存后重新运行程序。"
        )
    if "429" in low or "rate" in low:
        return "调用失败：请求太频繁或免费额度用尽（429）。等一两分钟再试。"
    if "timeout" in low or "connection" in low or "network" in low or "resolve" in low:
        return "调用失败：连不上模型服务。先确认网络能打开 bailian.console.aliyun.com，再重试。"
    return f"调用失败：{detail}\n\n可以先把这段报错截图，再看是不是 .env 配错了。"


def run_agent(lc_messages: list, model: str, temperature: float):
    """把 LangGraph 的执行过程转成事件流，交给界面边跑边显示。"""
    graph = get_graph(model, temperature)
    final_text = ""

    for update in graph.stream(
        {"messages": lc_messages},
        config={"recursion_limit": RECURSION_LIMIT},
        stream_mode="updates",
    ):
        for node, payload in update.items():
            msgs = (payload or {}).get("messages") or []

            if node == "agent" and msgs:
                msg = msgs[-1]
                calls = getattr(msg, "tool_calls", None) or []
                for call in calls:
                    args = json.dumps(call.get("args", {}), ensure_ascii=False)
                    yield ("call", call.get("name", "unknown"), args)
                if not calls and getattr(msg, "content", ""):
                    content = msg.content
                    final_text = (
                        content if isinstance(content, str) else str(content)
                    )

            elif node == "tools":
                for m in msgs:
                    yield (
                        "result",
                        getattr(m, "name", "tool"),
                        clip(getattr(m, "content", "")),
                    )

    yield ("final", final_text or "（模型这一轮没有返回文字，可以换个说法再试一次。）")


# ---------------- 侧边栏 ----------------
with st.sidebar:
    # ---- 语种与目标等级 ----
    # 这两项必须先于「学习档案」渲染：档案区、今日推送卡片、演示话术
    # 都要读它们，放进下面会在第一次渲染时拿到旧值。
    st.markdown("### 学习设置")
    profile = load_profile()
    cur_code = (profile.get("language") or "en").strip().lower()
    if cur_code not in langs.codes():
        cur_code = "en"
    chosen = st.selectbox(
        "学习语种",
        langs.codes(),
        index=langs.codes().index(cur_code),
        format_func=lambda c: langs.names()[c],
        key="lang_select",
    )
    lang = langs.get(chosen)
    cur_level = (profile.get("target_exam") or "").strip()
    if not langs.level_belongs(chosen, cur_level):
        cur_level = lang["default_level"]
    level = st.selectbox(
        "目标等级",
        lang["levels"],
        index=lang["levels"].index(cur_level),
        key=f"level_{chosen}",
        help="不同语种是四套不同的分档，切换语种会自动换成该语种的等级体系。",
    )
    if (profile.get("language") or "") != chosen or (profile.get("target_exam") or "") != level:
        profile["language"] = chosen
        profile["target_exam"] = level
        save_profile(profile)

    st.caption(
        f"{lang['flag']} {lang['name']} ｜ 注音：{lang['sound']} ｜ "
        + ("词库可核验" if lang["lexicon"] else "**无本地词库**（释义/注音为模型推断）")
    )

    st.divider()
    st.markdown("### 学习档案")
    if profile:
        st.caption(
            f"目标考试 **{profile.get('target_exam', '—')}** ｜ "
            f"水平 {profile.get('level', '—')} ｜ "
            f"已练 {profile.get('sessions', 0)} 次"
        )
        st.caption(profile.get("goal", ""))
        mistakes = profile.get("mistakes", [])
        if mistakes:
            st.markdown("**错词本**")
            for m in mistakes[:6]:
                st.markdown(
                    f"<div class='step-line'>· {m['word']} "
                    f"<span style='color:#9ca3af'>({m.get('count', 1)} 次)</span></div>",
                    unsafe_allow_html=True,
                )
        due = due_words(limit=8)
        if due:
            st.markdown(
                "<div class='step-line'><b>今日待复习</b> "
                f"{len(due)} 个："
                + "、".join(f"{e['word']}({str(e['due'])[5:]})" for e in due[:4])
                + ("…" if len(due) > 4 else "")
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("今日没有到期的复习词")
    else:
        st.caption("暂无档案")

    st.divider()
    st.markdown("### 产出文件")
    st.caption(f"目录：`{config.OUTPUT_DIR}`")
    if st.button("📂 打开 outputs 文件夹", use_container_width=True, key="open_folder_side"):
        open_in_explorer()
    # 这里只占个位置，真正的内容在脚本最后填。
    # Streamlit 自上而下执行：如果把文件列表写在这一段，它在「发消息」之前就跑完了，
    # 这一轮 Agent 新生成的文件不会出现在里面——用户会以为文件根本没生成。
    output_slot = st.container()

    st.divider()
    with st.expander("模型设置"):
        model = st.text_input("模型", value=config.MODEL_NAME)
        temperature = st.slider("温度", 0.0, 1.0, 0.3, 0.1)

    if st.button("清空当前会话", use_container_width=True):
        st.session_state.messages = []
        save_session([])
        st.rerun()

    st.caption(
        "本项目为课程期末考查作品。"
        + (
            "词义与考纲等级来自项目内置词库（6161 条），仅供参考，请以权威词典为准。"
            if lang["lexicon"]
            else f"{lang['name']}暂无本地词库：释义、注音与等级均由模型生成，"
            "请以教材或权威辞典为准。"
        )
    )

# ---------------- 主区 ----------------
st.title("外刊精读教练")
st.caption(
    f"每天推送一篇{lang['name']}新闻，丢给它就读完查词、分级、出词表和一份挖空练习页。"
    " ｜ 五语种 · LangGraph + 百炼 + Streamlit"
)

if "messages" not in st.session_state:
    st.session_state.messages = load_session()

if not config.has_api_key():
    st.warning(config.missing_key_hint())

# ---------------- 今日推送 ----------------
# 卡片是「每日任务」的入口，逻辑和多邻国首页那个任务卡一致：
# 今天读什么、我连续几天了、点一下就开始。
# 抓取结果按「语种+日期」缓存在 session_state，避免每次重跑都去敲对方站点。
daily_key = f"daily_{lang['code']}_{date.today().isoformat()}"
if daily_key not in st.session_state:
    with st.spinner(f"正在取今天的{lang['name']}文章…"):
        st.session_state[daily_key] = daily.pick(lang["code"])
today = st.session_state[daily_key]
stats = daily.status(lang["code"])

with st.container(border=True):
    left, right = st.columns([3, 1.1])
    with left:
        origin_label = {"live": "今天新抓", "pool": "离线快照"}.get(today.get("origin"), "未取到")
        st.markdown(
            f"<span class='step-line'>**今日推送** ｜ {today['date']} ｜ "
            f"{lang['flag']} {lang['name']} · {level} ｜ {origin_label}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {today['title']}")
        if today.get("text"):
            st.caption(
                f"来源：{today['source']} ｜ {len(today['text'])} 字符 ｜ "
                f"建议挑 {daily.suggest_words(today['text'])} 个词 ｜ {today.get('note', '')}".rstrip(" ｜")
            )
            st.caption(daily.preview(today, 110))
        else:
            st.caption(today.get("note", "今天没有取到可用文章"))
    with right:
        st.metric("连续打卡", f"{stats['streak']} 天")
        st.caption(
            f"累计 {stats['total']} 篇 · " + ("今天已读" if stats["done_today"] else "今天还没读")
        )

    if today.get("text"):
        b1, b2, b3 = st.columns([1.1, 1, 2.4])
        if b1.button("开始今天的精读", type="primary", use_container_width=True, key="start_daily"):
            save_user_article(today["text"])
            daily.record_done(lang["code"])
            st.session_state.pending = (
                f"今天推送的{lang['name']}文章已经放进文章槽"
                f"（标题：{today['title']}；来源：{today['source']}）。"
                f"请用 load_text 读出正文，挑 {daily.suggest_words(today['text'])} 个"
                f"对 {level} 有区分度的词，"
                + ("逐个用 lookup_word 查证，" if lang["lexicon"] else "给出释义与注音（本语种无本地词库，必须标注未经校验），")
                + "然后生成词表和挖空练习页。"
            )
            st.rerun()
        if b2.button("换一篇", use_container_width=True, key="reroll_daily"):
            # 只在本会话内换：换的是快照池里的下一篇，不重新打对方服务器。
            pool_items = daily.pool(lang["code"])
            if len(pool_items) > 1:
                cur_title = today["title"]
                nxt = next((x for x in pool_items if x["title"] != cur_title), pool_items[0])
                item = dict(nxt)
                item.update(origin="pool", date=today["date"],
                            note=f"离线快照（抓取于 {nxt.get('fetched_at', '未知')}）")
                st.session_state[daily_key] = item
                st.rerun()
            else:
                st.caption("快照池里只有一篇，先跑 scripts/fetch_pool.py 补几篇。")
        b3.caption(
            "「开始」会把这篇放进文章槽并记一次打卡。"
            "标题、来源与抓取方式都来自抓取结果，不是生成的文案。"
        )

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            attach_outputs(msg["content"], f"h{idx}")

with st.expander("四句话就能演示完（点一下直接填入）", expanded=not st.session_state.messages):
    cols = st.columns(2)
    for i, text in enumerate(demo_prompts(lang["code"])):
        if cols[i % 2].button(text, key=f"demo_{i}", use_container_width=True):
            st.session_state.pending = text
            st.rerun()

with st.expander(f"粘贴自己的{lang['name']}材料（不想只用今天的推送的话，用这里）", expanded=False):
    st.caption(
        f"外刊、教材、老师当场给的一段{lang['name']}材料，都可以。"
        "程序只会把它保存到 data/current_article.txt 这一个固定位置，"
        "Agent 读的也是这个固定槽位，没有路径参数可传——"
        "所以「打开入口」和「守住边界」在这里不冲突。"
    )
    slot_chars = len(load_user_article())
    if slot_chars:
        st.caption(f"当前文章槽已有 {slot_chars} 字符。重贴会覆盖。")
    pasted = st.text_area(
        f"{lang['name']}原文",
        height=170,
        key="paste_area",
        placeholder="Paste any English article here …",
        label_visibility="collapsed",
    )
    col_a, col_b = st.columns([2, 1])
    if col_a.button("用这篇开始精读", type="primary", use_container_width=True):
        n = save_user_article(pasted)
        if n < 40:
            st.warning(f"正文只有 {n} 字符，太短了，至少 40 字符。")
        else:
            st.session_state.pending = (
                f"我贴了一篇新的{lang['name']}原文，已经在当前文章槽里。"
                f"请用 load_text 读出正文，挑 8～10 个对 {level} 有区分度的词，"
                + (
                    "逐个 lookup_word 查证，然后生成词表和挖空练习页。"
                    if lang["lexicon"]
                    else "给出释义与注音（本语种无本地词库，必须标注未经校验），"
                    "然后生成词表和挖空练习页。"
                )
            )
            st.rerun()
    if col_b.button("清空文章槽", use_container_width=True):
        save_user_article("")
        st.rerun()

prompt = st.chat_input(f"试试：今天推了什么？帮我挑 8 个 {level} 生词精读")
if st.session_state.get("pending"):
    prompt = st.session_state.pop("pending")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if not config.has_api_key():
        st.error("请先按上面的提示配置 .env 里的 API Key。")
    else:
        # 只取最近几轮「用户」说的话。技能触发要看上下文，不能只看当前这一句：
        # 第一轮说「精读这篇」，第二轮只说「再来一份」——只看当前句，技能就掉了。
        recent_user = " ".join(
            m["content"]
            for m in st.session_state.messages[-4:]
            if m["role"] == "user"
        )
        lc_messages = [
            SystemMessage(content=build_system_prompt(prompt, recent_user))
        ]
        for m in st.session_state.messages:
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            else:
                lc_messages.append(AIMessage(content=m["content"]))

        try:
            before = snapshot_outputs()
            with st.status("Agent 正在工作…", expanded=True) as status:
                steps = st.container()
                answer = ""
                for evt in run_agent(lc_messages, model, temperature):
                    if evt[0] == "call":
                        steps.markdown(
                            f"<div class='step-line'>→ 调用工具 "
                            f"<code>{evt[1]}</code>　参数 {evt[2]}</div>",
                            unsafe_allow_html=True,
                        )
                    elif evt[0] == "result":
                        steps.markdown(
                            f"<div class='step-line'>✓ <code>{evt[1]}</code> 返回 {evt[2]}</div>",
                            unsafe_allow_html=True,
                        )
                    elif evt[0] == "final":
                        answer = evt[1]
                status.update(label="完成", state="complete", expanded=False)

            # 出口处两道核对：路径换成真路径；确认文件真的写出来了。
            # 实测两次：模型写过 `/home/ubuntu/outputs/x.csv`（本机不存在），
            # 也曾经一个写盘工具都没调就在回复里说「两份文件已生成」。
            answer = normalize_output_paths(answer)
            after = snapshot_outputs()
            new_files = [
                n for n, t in after.items() if before.get(n) != t
            ]
            wrote_anything = bool(new_files)
            # 模型会换着说法撒谎：「已生成」「已基于查词结果生成」「两份文件在这里」。
            # 所以不看语气，看它有没有提到产物文件——提了却没写盘，就必须当场说明。
            mentions_file = bool(re.search(r"\.(?:csv|html|docx)", answer, re.I))
            claimed_write = bool(
                re.search(
                    r"(已|刚刚|这轮)[^。\n]{0,10}(生成|写入|保存|产出|做好)"
                    r"|生成完成|已生成",
                    answer,
                )
            )

            with st.chat_message("assistant"):
                if not wrote_anything and mentions_file:
                    existed = [n for n in re.findall(
                        r"([^\\/\s`'\"（）()]+\.(?:csv|html|docx))", answer, re.I
                    ) if n in after]
                    if claimed_write:
                        st.warning(
                            "⚠️ **本轮没有真正写出新文件。**\n\n"
                            "回复里写了「已生成」，但 `outputs/` 里没有出现本轮的新文件"
                            + (
                                "——它提到的是**之前几轮**就存在的 "
                                + "、".join(f"`{n}`" for n in dict.fromkeys(existed))
                                + "，不是这次生成的。"
                                if existed
                                else "——文件确实不存在。"
                            )
                            + "\n\n点下面按钮重跑一次（通常是它跳过了写文件那一步）。"
                        )
                        if st.button("↻ 重跑这一条", key="retry_write"):
                            st.session_state.pending = prompt
                            st.rerun()
                    else:
                        st.caption("↑ 这些文件是之前几轮生成的，本轮没有重新写盘。")
                st.markdown(answer)
                if new_files:
                    st.caption(
                        "本次新生成："
                        + "、".join(f"`{n}`" for n in new_files)
                    )
                attach_outputs(answer, "live")

            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )
            save_session(st.session_state.messages)

        except Exception as exc:
            st.error(friendly_error(exc))

# ---------------- 侧边栏：产出文件（最后填） ----------------
# 放在最后执行，才能把本轮刚生成的文件也列进去。
with output_slot:
    files = list_outputs()
    if not files:
        st.caption("还没有生成文件。跑一次精读试试。")
    # 排版按钮的结果要跨 rerun 保留一句提示，否则一闪就没了。
    _msg = st.session_state.pop("_docx_msg", None)
    if _msg:
        st.success(_msg)
    for i, p in enumerate(files):
        col_dl, col_open = st.columns([3, 1])
        with col_dl:
            st.download_button(
                label=f"⬇ {p.name}",
                data=p.read_bytes(),
                file_name=p.name,
                mime=MIME.get(p.suffix.lower(), "application/octet-stream"),
                use_container_width=True,
                key=f"side_dl_{i}_{p.name}",
            )
        with col_open:
            if st.button(
                "↗",
                key=f"side_op_{i}_{p.name}",
                use_container_width=True,
                help="用默认程序打开（CSV → Excel，HTML → 浏览器）",
            ):
                open_in_explorer(p)
        # CSV 旁边给一个「排成 Word 笔记」的确定性入口：
        # 不经过模型，点一下就把同名 .docx 排出来。
        # 这是「Word 打开 CSV 很乱」的兜底——模型忘了排版也不影响用户拿到成品。
        if p.suffix.lower() == ".csv":
            has_docx = p.with_suffix(".docx").exists()
            if st.button(
                "↻ 重排 Word 笔记" if has_docx else "▤ 排成 Word 笔记",
                key=f"side_docx_{i}_{p.name}",
                use_container_width=True,
                help="把这个 CSV 排成逐词分块的 Word（只排版，不改内容）",
            ):
                try:
                    from tools.vocabdoc import render_csv_file

                    out = render_csv_file(p, language=lang["code"])
                    st.session_state["_docx_msg"] = f"已生成 {out.name}（见上面列表）"
                except Exception as exc:
                    st.session_state["_docx_msg"] = f"排版失败：{exc}"
                st.rerun()
