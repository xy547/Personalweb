"""读原文的两个入口：内置示例（read_article）与用户自贴（load_text）。

这两个工具解决的是同一个问题——「正文从哪来」，但边界不同：

- read_article：只能读 demo/ 里的内置示例，纯只读。
- load_text：读用户自己贴进来的文章。

为什么 load_text 刻意 **不接受文件路径**：
如果它有个 filename 参数，模型顺着 ../ 就能把 .env 读出来贴进对话，
密钥会直接出现在界面上——这正是答辩时「权限隔离」要举的反例。
所以它读的是一个固定槽位 data/current_article.txt，由界面写入正文；
模型只负责「取」，完全不参与「去哪取」。地址不可控，越权就没有落点。

这是本项目相对同类软件补上的第一个缺口：之前只能精读内置那篇文章，
用户想处理自己手上的材料（外刊、教材、老师发的 PDF 里复制一段）根本进不来。
补法是「多开一个入口」而不是「放开路径」，安全故事一点没破。
"""

import re

from langchain_core.tools import tool

from config import CURRENT_ARTICLE_PATH, DEMO_DIR

MAX_CHARS = 20000
MIN_CHARS = 40


def _normalize(text: str) -> str:
    """统一换行、去掉行尾空白、把 3 个以上空行压成 2 个。"""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def save_user_article(text: str) -> int:
    """界面专用：把用户粘贴的正文写进固定槽位，返回字符数。"""
    body = _normalize(text)
    CURRENT_ARTICLE_PATH.write_text(body, encoding="utf-8")
    return len(body)


def load_user_article() -> str:
    if not CURRENT_ARTICLE_PATH.exists():
        return ""
    return CURRENT_ARTICLE_PATH.read_text(encoding="utf-8").strip()


@tool
def load_text(article: str = "", source_name: str = "") -> str:
    """读取用户要精读的英文原文。按顺序取两个来源：

    1. 用户刚在界面上粘贴过文章 → 不用传任何参数，直接调用本工具，
       它会从「当前文章槽」里取出正文。
    2. 用户把原文直接发在对话里 → 把原文整段放进 article 参数传进来。

    参数 article 里放的是**英文正文本身**，不是文件路径、也不是网址。
    本工具不读任何文件，传路径进来一定会失败。

    source_name 可选，只给材料起个名字（例如 "Economist-2026-09"），
    用于说明产出的材料出自哪里，不影响正文内容。

    拿到返回后，把 ARTICLE START 与 ARTICLE END 之间的全文原样传给
    build_worksheet_html 的 article 参数，不要改写、不要节选。
    """
    pasted = _normalize(article)
    if pasted:
        origin = "对话内粘贴"
        source = (source_name or "对话内粘贴").strip()[:60]
    else:
        pasted = load_user_article()
        origin = "界面粘贴槽（data/current_article.txt）"
        source = (source_name or "界面粘贴").strip()[:60]

    if not pasted:
        return (
            "EMPTY: 当前文章槽是空的，你也没有在 article 参数里传正文。\n"
            "请让用户在界面上的「粘贴自己的文章」里贴一段英文再点开始，"
            "或者请用户直接把原文发在对话里。不要自己编一篇文章来充数。"
        )

    if len(pasted) < MIN_CHARS:
        return (
            f"ERROR: 正文太短（{len(pasted)} 字符），至少需要 {MIN_CHARS} 字符。"
            "如果用户只给了一个标题或一句话，请向他确认要精读的完整段落。"
        )

    truncated = len(pasted) > MAX_CHARS
    body = pasted[:MAX_CHARS] if truncated else pasted
    paragraphs = len([p for p in body.split("\n\n") if p.strip()])

    meta = (
        f"SOURCE: {source}\n"
        f"ORIGIN: {origin}\n"
        f"CHARS: {len(body)}  PARAGRAPHS: {paragraphs}"
        + ("  TRUNCATED: true（超出 20000 字符，已截断，回复里要说明）" if truncated else "")
    )
    return f"{meta}\n--- ARTICLE START ---\n{body}\n--- ARTICLE END ---"


def _read_daily() -> str:
    """取今天推送的那篇，并把正文放进文章槽。

    为什么要顺手写槽：daily 版和 load_text 必须读同一份正文。
    否则用户先说「读今天的」，再说「生成练习页」，练习页可能用上旧文章——
    界面上看不出来，但挖空对不上原文，最容易被追问。
    """
    from agent.languages import get as get_lang
    from tools import daily
    from tools.memory import load_profile

    lang = get_lang(load_profile().get("language", "en"))
    item = daily.pick(lang["code"])
    if not item.get("text"):
        return (
            "EMPTY: 今天的推送没有取到正文（联网抓取失败，本地快照池也为空）。\n"
            f"如实告诉用户「{item.get('date', '今天')} 这篇没取到」，"
            "建议他用自己的文章走粘贴框。**不要自己编一篇文章充数。**"
        )

    save_user_article(item["text"])
    origin = {
        "live": "联网抓取（今天的新文章）",
        "pool": f"离线快照（{item.get('note', '抓取日期未知')}）",
    }.get(item.get("origin", ""), item.get("origin", "未知"))
    n = daily.suggest_words(item["text"])
    mark = daily.record_done(lang["code"])

    return (
        f"SOURCE: {item['source']}\n"
        f"TITLE: {item['title']}\n"
        f"URL: {item['url'] or '（离线快照，无链接）'}\n"
        f"LANGUAGE: {lang['name']}（{lang['level_system']}）\n"
        f"ORIGIN: {origin}\n"
        f"CHARS: {len(item['text'])}\n"
        f"STREAK: 连续 {mark['streak']} 天（今天已计入）\n"
        f"HINT: 建议挑 {n} 个词。正文已写入文章槽，后续用 load_text 取同一份。\n"
        "引用出处时只能抄 SOURCE / URL / ORIGIN 这三个字段，"
        "不要说「来自经济学人」这类没根据的话。\n"
        "--- ARTICLE START ---\n"
        f"{item['text']}\n"
        "--- ARTICLE END ---"
    )


@tool
def read_article(filename: str = "article_sample.txt", source: str = "demo") -> str:
    """读取要精读的文章。两个来源，用 source 区分：

    - source="demo"（默认）：读 demo 目录下的内置示例文章。
      只用于「那篇内置的示例文章」，参数 filename 填纯文件名，例如 "article_sample.txt"。
    - source="daily"：读**今天推送的那篇**（首页「今日推送」卡片上的同一篇，
      按当前语种抓取，网络不通时用离线快照）。用户问「今天推了什么」「读今天的文章」
      「今日任务」时用这个。返回里带标题、来源站点、原文链接和抓取方式，
      引用出处时只能抄这几个字段。

    source="daily" 时会把正文同时写进文章槽，所以后面照常用 load_text
    取同一份正文即可；不要把返回里的正文再复制进别的参数。

    如果返回 NOT_FOUND，会同时列出目录里可用的文件，照那个名字重试；
    不要凭猜测编造文章内容。
    """
    if (source or "").strip().lower() in ("daily", "today", "push", "推送"):
        return _read_daily()

    raw = (filename or "").strip().replace("\\", "/")
    if "/" in raw:
        return "ERROR: filename 只接受纯文件名，不能带目录层级。"
    if not raw:
        raw = "article_sample.txt"

    path = (DEMO_DIR / raw).resolve()
    if path.parent != DEMO_DIR.resolve():
        return "ERROR: 只能读取 demo 目录下的文件。"
    if not path.exists():
        # 只报文件名不够：实测模型会凭文件名瞎猜内容（说 paste_sample.txt 是
        # 「空白占位文件」），然后停下来反问用户「要不要换一篇」，主路径当场卡死。
        # 所以这里把每个候选的**首行**一起给出，并明确要求它自己重试。
        lines = []
        for cand in sorted(DEMO_DIR.glob("*")):
            if not cand.is_file():
                continue
            first = ""
            for ln in cand.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    first = ln.strip()[:60]
                    break
            lines.append(f"{cand.name}（首行：{first}）")
        return (
            f"NOT_FOUND: demo/{raw} 不存在。\n"
            "可用文件：" + "；".join(lines) + "\n"
            "处理办法：**立刻用 article_sample.txt 重新调用本工具**，"
            "不要反问用户「要不要换一篇」，也不要凭文件名猜文章内容。"
            "拿到正文后继续后面的流程；回复里补一句「内置文件名猜错了，已改用 xxx」。"
        )

    text = path.read_text(encoding="utf-8").strip()
    return f"[demo/{raw}]\n\n{text}"
