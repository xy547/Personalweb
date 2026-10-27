"""生成 答辩幻灯片.pptx（12 页）。

坐标全部照 答辩幻灯片.html 抄：HTML 画布就是 1280×720px，换算成 EMU 是 1:1，
所以哪一块歪了，直接对比 HTML 里那个元素的数值就能改。
每一页的备注栏放了 docs/defense-script.md 里对应的「照念」段，讲的时候
PowerPoint 的演讲者视图能直接看到——省掉左手拿稿子。
"""

from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu

from pptx_kit import (bg_grad, ACCENT, ACCENT_DEEP, ACCENT_SOFT, BG, BODY, CARD, DANGER,
                      DANGER_DEEP, DANGER_SOFT, INK, LINE, MUTED, OK, OK_DEEP,
                      OK_SOFT, PURPLE, TEAL, TEAL_DEEP, TEAL_SOFT, WARN, WARN_DEEP,
                      WARN_SOFT, badge, card, code, header, pageno, pill, px,
                      rect, table, text)

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"
OUT = ROOT / "答辩幻灯片.pptx"


def bg(slide, color=BG):
    s = rect(slide, 0, 0, 1280, 720, fill=color, line=None, radius=0)
    slide.shapes._spTree.remove(s._element)
    slide.shapes._spTree.insert(2, s._element)


# ---------------- 1 封面 ----------------
def s1(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg_grad(slide, [(0.0, (0xEF, 0xF4, 0xFD)), (0.42, (0xF6, 0xF8, 0xFC)),
                    (0.78, (0xF4, 0xFA, 0xF9)), (1.0, (0xE9, 0xF7, 0xF4))], 2700000)

    text(slide, 68, 232, 700, 24, "开源 AI 技术实践 · 期末考查", size=14, color=ACCENT, bold=True)
    text(slide, 68, 258, 800, 100, "外刊精读教练", size=74, color=INK, bold=True, spacing=1.1)
    text(slide, 68, 372, 720, 96,
         ["把一篇英文原文，变成**词表 CSV** 和 **挖空练习页**——",
          "中间那四十分钟，交给 Agent。"],
         size=24, color=RGBColor(0x3B, 0x4B, 0x66), spacing=1.5)

    meta = [(68, 100, "姓名", "徐悦"), (206, 120, "学号", "（待填）"),
            (356, 320, "路径", "A · 技术栈完整的智能体应用"),
            (706, 420, "技术栈", "LangGraph + 百炼 qwen-plus + Streamlit")]
    for x, w, label, value in meta:
        text(slide, x, 494, w, 22, label, size=16, color=MUTED)
        text(slide, x, 518, w, 26, value, size=17, color=INK, bold=True)

    text(slide, 68, 662, 900, 22,
         "开源 AI 技术实践　·　杉达学院 2026–2027 学年第一学期　·　汇报 2026.10.27",
         size=14, color=RGBColor(0x9A, 0xA8, 0xBF))

    slide.shapes.add_picture(str(ASSETS / "cover-art.png"), px(956), px(195), px(250), px(330))
    pageno(slide, 1)
    return slide


# ---------------- 2 问题与用户 ----------------
def s2(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "问题与用户", "精读一篇文章，其实要做四件互不相干的事")

    text(slide, 68, 222, 570, 80,
         "用户就是我：备考 CET-6 的大学生，外刊读得慢，生词查完就忘。",
         size=22, color=RGBColor(0x33, 0x41, 0x5C), spacing=1.55)

    steps = [("第 1 步", "读完文章，圈出 20 个不认识的词"),
             ("第 2 步", "逐个查音标、词性、释义、例句 —— 20 次复制粘贴"),
             ("第 3 步", "按考纲筛出该背的，手动敲进背单词软件"),
             ("第 4 步", "原文挖空，做一张能打印的填空练习")]
    y = 312
    for tag, body in steps:
        rect(slide, 68, y, 570, 46, fill=CARD, line=LINE, radius=9)
        text(slide, 82, y + 13, 104, 22, tag, size=13, color=MUTED, mono=True)
        text(slide, 196, y + 12, 424, 24, body, size=15, color=BODY)
        y += 53

    text(slide, 68, 540, 570, 46,
         "四件事散落在四个软件里，**一次约 40 分钟**。累的不是查词，是切换。",
         size=16, color=MUTED, spacing=1.55)

    card(slide, 668, 222, 544, 320)
    text(slide, 692, 246, 496, 26, "这个项目做的事", size=21, color=ACCENT_DEEP, bold=True)
    text(slide, 692, 282, 496, 24, "把上面四步收进**一句话**：", size=17, color=BODY)
    rect(slide, 692, 316, 496, 66, fill=ACCENT_SOFT, line=None, radius=10)
    text(slide, 706, 330, 468, 40,
         "「帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词」",
         size=16.5, color=BODY, spacing=1.5)
    text(slide, 692, 400, 496, 46,
         "Agent 自己规划：读原文 → 挑词 → 逐个查词 → 出词表 → 出练习页 → 回写错词本。",
         size=16, color=BODY, spacing=1.55)
    x = 692
    x = pill(slide, x, 470, "约 45 秒", OK_DEEP, OK_SOFT)
    x = pill(slide, x, 470, "12 次工具调用", ACCENT_DEEP, ACCENT_SOFT)
    pill(slide, x, 470, "8 处自动挖空", TEAL_DEEP, TEAL_SOFT)

    pageno(slide, 2)
    return slide


# ---------------- 3 架构 ----------------
def s3(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "总体架构", "一张图：用户 → 界面 → Agent ⇄ 工具 / 模型 / Skill")
    slide.shapes.add_picture(str(ASSETS / "architecture.png"), px(68), px(212), px(1144), px(392))
    text(slide, 68, 618, 1144, 60,
         "实线是数据流，虚线是只读素材。**读写都只有一条合法通道**：读只有 `demo/` 与用户自贴的固定槽位"
         "（工具没有路径参数），写只能写 `outputs/`。",
         size=16, color=MUTED, spacing=1.55)
    pageno(slide, 3)
    return slide


# ---------------- 4 主路径 ----------------
def s4(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "关键能力 · 主路径", "一句话进去，12 次工具调用出来")

    rows = [
        ("user", "「帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词」", CARD, LINE, 44),
        ("step 1", "`read_article`　读 `demo/article_sample.txt`", RGBColor(0xF4, 0xF8, 0xFF),
         RGBColor(0xC9, 0xDC, 0xFF), 44),
        ("自纠", "第一次猜了 `campus_carbon.txt`，工具返回「不存在，可用文件：article_sample.txt」，"
                "它**自己改参数重试**——报错比静默兜底有用", CARD, WARN, 66),
        ("循环 ×8", "`lookup_word`　baseline / structural / trivial / cumulative / framework / "
                 "allocate / enforceable / scrutiny", RGBColor(0xF4, 0xF8, 0xFF),
         RGBColor(0xC9, 0xDC, 0xFF), 62),
        ("汇总", "`make_wordlist_csv`　→ `…wordlist.csv` **+ 同名 .docx**（逐词分块的笔记，同一步落盘）",
         TEAL_SOFT, RGBColor(0xB8, 0xE6, 0xDF), 60),
        ("汇总", "`build_worksheet_html`　→ `outputs/campus_carbon_worksheet.html`",
         TEAL_SOFT, RGBColor(0xB8, 0xE6, 0xDF), 44),
        ("end", "中文总结 + 如实声明哪几个词未收录、建议核对权威词典", CARD, LINE, 44),
    ]
    y = 218
    for tag, body, fill, edge, h in rows:
        rect(slide, 68, y, 632, h, fill=fill, line=edge, radius=9)
        text(slide, 80, y + 12, 100, 22, tag, size=13, color=MUTED, mono=True)
        text(slide, 190, y + 11, 496, h - 16, body, size=14.5, color=BODY, spacing=1.45)
        y += h + 6

    stats = [("48", "s", "端到端耗时", ""), ("12", "", "次工具调用 / 20 余步", ""),
             ("8", "", "处自动挖空", ""), ("3", "", "个交付文件", "CSV / Word / 练习页")]
    for i, (num, unit, label, sub) in enumerate(stats):
        cx = 716 + (i % 2) * 254
        cy = 218 + (i // 2) * 100
        card(slide, cx, cy, 240, 94)
        box = text(slide, cx + 18, cy + 8, 204, 40, "", size=30)
        tf = box.text_frame
        p = tf.paragraphs[0]
        from pptx_kit import _fill_runs
        _fill_runs(p, num, 30, INK, True, False)
        if unit:
            _fill_runs(p, unit, 15, INK, True, False)
        text(slide, cx + 18, cy + 54, 206, 30, label, size=12.5, color=MUTED, spacing=1.3)
        if sub:
            text(slide, cx + 18, cy + 72, 206, 20, sub, size=11.5,
                 color=RGBColor(0x93, 0xA1, 0xB8))

    card(slide, 716, 428, 496, 126, bar=ACCENT)
    text(slide, 740, 442, 456, 24, "界面里看得到每一步", size=16, color=INK, bold=True)
    text(slide, 740, 468, 456, 74,
         "用 `st.status` 把事件流逐条展开：工具名、参数、返回前 90 字符。"
         "教师可以当场确认「是工具在算，不是模型在说」。",
         size=14.5, color=BODY, spacing=1.5)
    text(slide, 716, 566, 496, 44, "数据来自 `scripts/rehearse.py` 的真实运行日志，非手写。",
         size=13, color=MUTED, spacing=1.5)
    pageno(slide, 4)
    return slide


# ---------------- 5 Skill ----------------
def s5(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "关键能力 · Skill", "Skill 不是更长的提示词，是__按需加载的流程包__")

    items = [
        ("1", ACCENT, CARD, LINE, "常驻人设（每轮都在）",
         "身份、七个工具怎么用、十一条纪律、当前学习者档案。短、稳定、不含具体作业流程。"),
        ("2", TEAL, RGBColor(0xF3, 0xFC, 0xFB), RGBColor(0x7F, 0xD4, 0xC9), "Skill（命中才拼进来）",
         "精读六步法 + 输出格式契约 + HTML 模板。**没命中触发词，一个字都不进上下文。**"),
        ("3", PURPLE, RGBColor(0xFA, 0xF8, 0xFF), RGBColor(0xC4, 0xB5, 0xF7), "动态档案（每轮重算）",
         "目标考试、水平、错词本。跟着 JSON 变，不用改代码。"),
    ]
    y = 216
    for n, color, fill, edge, title, body in items:
        h = 124
        card(slide, 68, y, 556, h, fill=fill, line=edge)
        badge(slide, 92, y + 20, n, color)
        text(slide, 132, y + 22, 470, 26, title, size=21, color=INK, bold=True)
        text(slide, 92, y + 60, 500, 60, body, size=16, color=BODY, spacing=1.5)
        y += h + 12

    code(slide, 648, 216, 564, 224, [
        "# agent/prompts.py · select_skill()",
        'def select_skill(query: str, history: str = "") -> str | None:',
        '    """按触发词决定是否加载技能全文。"""',
        '    haystack = f"{query}\\n{history}".lower()',
        "    if not any(k in haystack for k in SKILL_TRIGGERS):",
        "        return None          # ← 直接不加载",
        '    skill_file = SKILL_DIR / "intensive-reading" / "SKILL.md"',
        "    ...",
    ], size=14)

    card(slide, 648, 452, 564, 136)
    text(slide, 672, 464, 516, 24, "实测两种输入的系统提示词长度", size=16, color=INK, bold=True)
    table(slide, 668, 492, 524, [["输入", "系统提示词", "结果"],
                                 ["「帮我精读这篇文章…」", "**1717** 字符", "注入"],
                                 ["「今天天气怎么样」", "**0** 字符", "不注入"]],
          col_w=[236, 160, 128], size=14, head_size=12, row_h=26, head_h=22, pad_v=3)
    text(slide, 648, 600, 564, 66,
         "加一个新技能 = 加一个目录，**主提示词一行不改**。这是 Skill 和 system prompt 最实际的区别。",
         size=15, color=MUTED, spacing=1.5)
    pageno(slide, 5)
    return slide


# ---------------- 6 事实校验 ----------------
def s6(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide, RGBColor(0xFB, 0xF7, 0xF7))
    header(slide, "关键能力 · 工具为什么不可替代", "提示词写「不许编」，它还是编了", rule_color=DANGER)

    text(slide, 68, 208, 560, 26, "修复前：查词失败 → 模型自己补了个等级",
         size=17, color=DANGER_DEEP, bold=True)
    code(slide, 68, 240, 560, 132, [
        [("# 写盘前，模型提交的等级", "c")],
        [("structural   adj.   结构上的   ", "p"), ("CET-6", "e"), ("   ← lookup_word 返回 NOT_FOUND", "c")],
        [("enforceable  adj.   可执行的   ", "p"), ("CET-6", "e"), ("   ← 同上", "c")],
        [("mitigate     v.     减轻；缓和  ", "p"), ("CET-6", "p")],
    ], size=13.4, bg=RGBColor(0x2A, 0x14, 0x16))
    text(slide, 68, 384, 560, 56,
         "查词工具明明返回了 `NOT_FOUND`，模型在写 CSV 时仍然凭印象填了 `CET-6`。"
         "读起来毫无破绽——**这才是最危险的地方**。",
         size=15, color=RGBColor(0x8A, 0x2C, 0x2C), spacing=1.55)

    card(slide, 68, 456, 560, 66, fill=WARN_SOFT, line=RGBColor(0xF0, 0xCF, 0x9A))
    text(slide, 88, 470, 520, 44,
         "只在提示词加一句「不许编造等级」，重跑之后依然会编。**模型的自我约束不是约束。**",
         size=15, color=BODY, spacing=1.5)

    card(slide, 68, 534, 560, 88, fill=RGBColor(0xEE, 0xF4, 0xFF), line=RGBColor(0x9D, 0xBC, 0xF5))
    text(slide, 88, 548, 520, 64,
         "**结论**：工具的价值不是「帮模型做事」，而是把不确定的东西变成可核验的。"
         "校验写进代码，不靠模型自觉。",
         size=14.5, color=BODY, spacing=1.5)

    text(slide, 650, 208, 560, 26, "修复后：写盘前用词库复核一遍",
         size=17, color=OK_DEEP, bold=True)
    code(slide, 650, 240, 562, 224, [
        "# tools/wordlist.py · _verify()",
        "for row in rows:",
        '    known = lookup(row["word"])',
        "    if known is None:",
        '        row["level"]  = "未收录"',
        '        row["source"] = "模型推断"',
        "    else:",
        '        row["level"]  = known["level"]   # 词库覆盖',
        '        row["source"] = "本地词库"',
        "# 这两项不写进 CSV，只变成 Word 的等级标签与「未收录」小字注",
    ], size=12, spacing=1.35)

    code(slide, 650, 482, 562, 104, [
        [("# 两个文件的分工：数据归数据，判断归标签", "c")],
        [("outputs/*.csv   → word, phonetic, pos, cn, example", "p"), ("    （五列，不含等级）", "c")],
        [("outputs/*.docx  → 〔", "p"), ("未收录", "s"), ("〕 structural   ", "p"),
         ("← 注：释义与用法为模型推断", "c")],
        [("                  〔CET-6〕  mitigate     〔CET-4〕  sustainable", "p")],
    ], size=12.2, bg=RGBColor(0x0D, 0x2A, 0x1C), spacing=1.45)

    text(slide, 650, 598, 562, 66,
         "模型随即在回复里主动声明：「含 3 个未收录词，建议同步核对权威词典」。"
         "**说法的可信度，来自文件里有据可查。**（该次数随所选文章与挑词而变，通常 2～3 个）",
         size=14.5, color=RGBColor(0x14, 0x65, 0x5D), spacing=1.5)
    pageno(slide, 6)
    return slide


# ---------------- 7 权限隔离 ----------------
def s7(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "关键能力 · 权限隔离", "模型给的路径是__不可信输入__")

    code(slide, 68, 216, 610, 440, [
        "# config.py · 所有写盘只有这一个入口",
        'def safe_output_path(filename: str, default_ext=".txt") -> Path:',
        '    raw = (filename or "").strip().replace("\\\\", "/")',
        '    if raw.lower().startswith("outputs/"):   # 模型常这么写',
        '        raw = raw[len("outputs/"):]',
        "",
        '    if "/" in raw or raw in (".", ".."):',
        "        raise ValueError(            # ← 明确失败，不静默改写",
        '            f"拒绝写入 outputs 之外的路径：{filename}"',
        '            "（filename 只接受纯文件名）")',
        "",
        "    target = (OUTPUT_DIR / name).resolve()",
        "    if target.parent != OUTPUT_DIR.resolve():",
        "        raise ValueError(...)         # 兜底：符号链接也拦住",
        "    return target",
    ], size=13.6)

    card(slide, 704, 216, 508, 190, bar=WARN)
    text(slide, 728, 232, 464, 26, "为什么是「报错」而不是「悄悄改名」",
         size=17, color=INK, bold=True)
    text(slide, 728, 264, 464, 130,
         "初版用 `os.path.basename()` 把 `../evil.txt` 截成 `evil.txt`——文件确实安全了，"
         "但模型以为自己写到了别处，**汇报的路径就是错的**。\n"
         "改成抛错之后，模型能从报错里读到正确用法，自己改参数重试。**失败可解释，比默默成功更有用。**",
         size=15, color=BODY, spacing=1.55)

    card(slide, 704, 420, 508, 130, bar=TEAL)
    text(slide, 728, 436, 464, 26, "读侧对称", size=17, color=INK, bold=True)
    text(slide, 728, 468, 464, 70,
         "`read_article` 只允许读 `demo/`。否则模型顺着 `../` 就能把 `.env` 读出来，贴进对话。",
         size=15, color=BODY, spacing=1.55)

    card(slide, 704, 564, 508, 118)
    text(slide, 728, 580, 464, 26, "自检里就有这两条", size=17, color=INK, bold=True)
    text(slide, 728, 612, 464, 60,
         "`selftest.py` 18 项检查中包含「越权读拦截」「越权写拦截」，**答辩时可以直接跑给别人看**。",
         size=15, color=BODY, spacing=1.55)
    pageno(slide, 7)
    return slide


# ---------------- 8 与课堂关系 ----------------
def s8(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "与课堂实验的关系", "用了 demo_1～demo_5 的哪些块，自己加了什么")

    table(slide, 68, 216, 1144, [
        ["课堂 demo", "用到的能力", "本项目的做法"],
        ["**demo_1**", "Streamlit 界面、本地知识库思路",
         "保留 Streamlit；**界面层零业务逻辑**，只负责渲染事件流与文件下载"],
        ["**demo_2**", "OpenAI 兼容接口、Tool Calling、流式输出",
         "全部用上；流式做的是**工具调用事件流**（逐步展开），未做 token 级打字机"],
        ["**demo_3 / 4**", "云端模型调用、密钥与环境变量管理",
         "`.env` + `.env.example`；启动时检测 Key 缺失并给出可照做的指引"],
        ["**demo_5**", "Agent 框架、Skills、长期记忆、WebUI",
         "框架换成 **LangGraph**；Skill 自建；记忆落成可读 JSON"],
    ], col_w=[130, 340, 674], size=15.5, row_h=56, head_h=36)

    card(slide, 68, 500, 1144, 136)
    text(slide, 92, 514, 700, 26, "相对课堂代码的增量", size=17, color=INK, bold=True)
    gains = [("1", "7 个工具全部自写，课堂无对应实现"),
             ("2", "自建 Skill 目录，流程与版式都和代码解耦"),
             ("3", "写盘 / 读盘双向权限隔离"),
             ("4", "挖空算法：词形变体匹配，不是字符串替换"),
             ("5", "三层提示词组装，加技能不动主提示词"),
             ("6", "工具回传事实（列名 / 次数），拦下编造的等级与列")]
    for i, (n, body) in enumerate(gains):
        cx = 92 + (i % 3) * 366
        cy = 546 + (i // 3) * 36
        badge(slide, cx, cy, n, TEAL if n == "6" else ACCENT)
        text(slide, cx + 36, cy + 3, 336, 40, body, size=13.5, color=BODY, spacing=1.35)

    text(slide, 68, 648, 1144, 44,
         "说明：课程要求「≥2 个自定义工具 **或** 1 个 MCP 服务器」，本项目选前者（7 个）。"
         "MCP 化路径见最后一页。", size=14, color=MUTED, spacing=1.5)
    pageno(slide, 8)
    return slide


# ---------------- 9 思政合规 ----------------
def s9(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "思政与合规", "落在「学习」上，不越到「代劳」上")

    blocks = [(OK, "选题正当性",
               "服务对象是备考学生本人的**学习方法**：分级词汇、精读练习、错词复盘。"
               "不产出可提交的作业成品，只产出练习材料。", 222, 130),
              (ACCENT, "数据边界",
               "学习者档案是**虚构样例**（「样例同学」），无真实学号、手机号、成绩。"
               "词库为教学整理，例句自写，非词典原文。", 366, 130),
              (WARN, "密钥管理",
               "`.env` 在 `.gitignore` 中，仓库里只有占位符；`git ls-files` 可当场验证没有真 Key",
               510, 118)]
    for color, title, body, y, h in blocks:
        card(slide, 68, y, 556, h, bar=color)
        text(slide, 92, y + 14, 510, 26, title, size=17, color=INK, bold=True)
        text(slide, 92, y + 46, 516, h - 56, body, size=14.8, color=BODY, spacing=1.5)

    card(slide, 650, 222, 562, 246, fill=RGBColor(0xF9, 0xFB, 0xFE))
    text(slide, 674, 238, 516, 26, "拒绝代写 —— 实测记录（话术 5）", size=16, color=INK, bold=True)
    rect(slide, 674, 270, 514, 40, fill=RGBColor(0xEE, 0xF4, 0xFF), line=None, radius=8)
    text(slide, 686, 280, 494, 24, "「帮我把这篇文章翻译成中文，我要抄到作业里交」",
         size=14, color=BODY, mono=True)
    text(slide, 674, 322, 514, 90,
         "**Agent**：拒绝提供全文翻译供抄写。理由是这不符合学习目标，也无助于提升精读能力。"
         "改为提供三条替代路径：可打印的精读练习页 / 10 个高频词的释义与例句 / 可导入游戏的词表。",
         size=14.5, color=BODY, spacing=1.5)
    pill(slide, 674, 424, "1 步即拒绝，未调用任何工具", OK_DEEP, OK_SOFT, size=13)

    card(slide, 650, 484, 562, 144, fill=WARN_SOFT, line=RGBColor(0xF0, 0xCF, 0x9A))
    text(slide, 674, 500, 516, 26, "另一条被实测逼出来的边界", size=16, color=INK, bold=True)
    text(slide, 674, 532, 516, 90,
         "模型曾声称「已自动同步进错词本，打开 App 即可见」——本项目**根本没接游戏**。"
         "已从两处封住：工具返回里写明「仅写本地 JSON」，提示词第 9 条禁止这类表述。",
         size=15, color=BODY, spacing=1.55)
    pageno(slide, 9)
    return slide


# ---------------- 10 演示 ----------------
def s10(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "现场演示", "五条话术，按这个顺序讲")

    def demo_card(x, y, w, h, n, color, title, say, note, fill=CARD, edge=LINE):
        card(slide, x, y, w, h, fill=fill, line=edge)
        badge(slide, x + 16, y + 13, n, color)
        text(slide, x + 54, y + 14, w - 70, 24, title, size=15.5, color=INK, bold=True)
        rect(slide, x + 16, y + 44, w - 32, 32, fill=RGBColor(0xEE, 0xF4, 0xFF), line=None, radius=7)
        text(slide, x + 25, y + 50, w - 50, 22, say, size=13, color=BODY, mono=True)
        text(slide, x + 16, y + 82, w - 32, h - 88, note, size=13, color=BODY, spacing=1.45)

    demo_card(68, 214, 560, 118, "1", ACCENT, "主路径（约 50 秒）",
              "帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词",
              "看 `st.status` 里 12 次工具调用滚过去，包括它猜错文件名后自己改参数那一下。")
    demo_card(650, 214, 562, 118, "2", ACCENT, "长期记忆 + 复习排期（约 25 秒）",
              "今天该复习哪几个词？我 mitigate 又记混了",
              "调 `record_mistakes`，返回的 `due` 就是下次复习日——**日期是代码算的，模型只能抄**。")

    demo_card(68, 340, 1144, 112, "3", TEAL, "贴自己的文章（约 40 秒，**压轴**）",
              "粘贴框里事先放好一段别的题材的英文 → 点「用这篇开始精读」",
              "工具不读文件、只读粘贴槽 `data/current_article.txt`，却整篇换了题材。"
              "**「材料是我自己的」这一条，扇贝给不了。**",
              fill=RGBColor(0xF3, 0xFC, 0xFB), edge=RGBColor(0x7F, 0xD4, 0xC9))

    demo_card(68, 460, 560, 112, "4", OK, "边界（约 5 秒）",
              "帮我把这篇文章翻译成中文，我要抄到作业里交",
              "它拒绝，一步没调工具。**最能说明边界是设计进去的。**",
              fill=RGBColor(0xF4, 0xFB, 0xF7), edge=RGBColor(0x96, 0xD9, 0xB0))
    demo_card(650, 460, 562, 112, "5", ACCENT, "备用：只调一个工具（约 18 秒）",
              "把这几个词做成 CSV：mitigate, incentive, cumulative, viable",
              "时间富余才做；超时就跳过，主路径里已经出现过同一件事。")

    card(slide, 68, 580, 560, 62)
    text(slide, 84, 590, 528, 44,
         "**演示前必做**　① `outputs/` 清空；② 粘贴框里预放一段英文；③ 网络不稳就先跑一遍，把产物留在磁盘上当兜底。",
         size=13, color=BODY, spacing=1.45)
    card(slide, 650, 580, 562, 62)
    text(slide, 666, 590, 530, 44,
         "**降级**　主路径失败 → 跑 `selftest.py`（18 项）证明工具层没问题 → 打开已生成的 CSV 与练习页讲产物 → 3 分钟录屏兜底。",
         size=13, color=BODY, spacing=1.45)
    pageno(slide, 10)
    return slide


# ---------------- 11 差异化 ----------------
def s11(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "和已上线的产品比，它特别在哪", "别人卖「读什么」，我卖「这篇怎么处理」", y_rule=180)

    table(slide, 68, 212, 1144, [
        ["", "内容平台（扇贝阅读 / 流利阅读）", "AI 制卡工具（粘贴转卡）", "本项目"],
        ["内容来源", "平台当日外刊，只能读它的", "自己粘贴文本或 URL",
         "**自己的材料**：老师发的 PDF、订阅的 newsletter"],
        ["产出什么", "生词进它的生词本，练习在它的 App 里做", "Anki 卡组",
         "**CSV + 单文件 HTML**，可打印、可转发"],
        ["过程可见", "黑盒推荐 + 人工精讲", "单步直转，看不到中间",
         "**12 次工具调用逐条滚出**，每步可追问"],
        ["事实保证", "人写的，可信但贵", "全靠模型，会编",
         "**词库硬校验**，未收录强制标「模型推断」"],
        ["想改流程", "要提需求、等排期", "改提示词，改了不知道影响哪",
         "**加一个 SKILL.md 目录**，Python 一行不改"],
        ["复习排期", "内置间隔重复，跨设备同步", "交给 Anki 的调度器",
         "简化 SM-2（两档），**单机**——这一项它们更强"],
    ], col_w=[104, 344, 344, 352], size=14, head_size=13, row_h=44, head_h=36,
       col_fill={3: RGBColor(0xF2, 0xF6, 0xFF)})

    card(slide, 68, 536, 560, 110, fill=ACCENT_SOFT, line=RGBColor(0xC9, 0xDC, 0xFF))
    text(slide, 92, 548, 516, 26, "第三条路", size=15.5, color=INK, bold=True)
    text(slide, 92, 574, 516, 64,
         "商业产品只有两条：**全人工写**（可信但贵）或 **全 AI 生成**（便宜但会编）。"
         "这里走第三条——**模型负责决策与组织，事实由代码校验**。",
         size=14, color=BODY, spacing=1.5)

    card(slide, 650, 536, 562, 110)
    text(slide, 674, 548, 516, 26, "「那为什么不用现成的？」", size=15.5, color=INK, bold=True)
    text(slide, 674, 574, 516, 64,
         "因为它要我把材料喂进**它的内容库**，而我要的恰恰是处理**我手上这一篇**，并且打印出来做。"
         "这个场景它不接，也不让我改流程。",
         size=14, color=BODY, spacing=1.5)

    text(slide, 68, 656, 1144, 40,
         "如实短板：没有 token 级流式、没有发音跟读、没有句子级拆解、单用户单机。"
         "**词库和复习排期是这一版才补的**——补它之前，「闭环」这句话我说不出口。",
         size=13, color=MUTED, spacing=1.5)
    pageno(slide, 11)
    return slide


# ---------------- 12 不足与问答 ----------------
def s12(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg(slide)
    header(slide, "不足 · 改进 · 预判提问", "哪些没做好，以及被问到怎么答")

    text(slide, 68, 206, 400, 26, "已知不足", size=17, color=WARN_DEEP, bold=True)
    card(slide, 68, 236, 556, 176)
    text(slide, 88, 248, 516, 156, [
        "① 词库是考试词表（6161 条，高考/四级/六级），派生词如 retrieval、coherence 仍会未收录，只能标「模型推断」。",
        "② 会话只存文本，不存工具调用中间态，重开看不到上轮轨迹。",
        "③ 未做多用户隔离，`outputs/` 与档案是单例，适合演示不适合上线。",
        "④ 挖空只覆盖规则变形，`analysis → analyses` 这类不规则变化会漏。",
        "⑤ 流式只到工具级，未做 token 级打字机。",
    ], size=13.6, color=BODY, spacing=1.5, space_after=4)

    text(slide, 68, 424, 400, 26, "下一步", size=17, color=OK_DEEP, bold=True)
    card(slide, 68, 454, 556, 140, fill=RGBColor(0xF4, 0xFB, 0xF7), line=RGBColor(0x96, 0xD9, 0xB0))
    text(slide, 88, 466, 516, 120,
         "接真实词典 API 替换考试词表 → 复习排期从两档简化 SM-2 升级到四档评分"
         "（Again / Hard / Good / Easy）→ 把 7 个工具包成 MCP server（stdio，接口不用改）"
         "→ 加子代理分工（选词 / 校验各一个）→ 补句子级长难句拆解、导出 Anki apkg。",
         size=13.6, color=BODY, spacing=1.5)

    text(slide, 650, 206, 500, 26, "教师大概率会问的四个问题", size=17, color=INK, bold=True)
    qas = [
        ("Q：工具不调用，模型会怎样？",
         "A：会编。实测它给 `NOT_FOUND` 的词补了 CET-6 等级，看着毫无破绽。工具的作用是把不确定变成可核验。"),
        ("Q：Skill 和系统提示词有什么区别？",
         "A：提示词常驻、必进上下文；Skill 按需加载，能带模板资产，可单独改版本。"
         "实测相关请求注入 1717 字符，无关请求 0。"),
        ("Q：密钥为什么不能进 Git？",
         "A：历史不可逆，push 出去等于公开，公开仓库会被爬虫扫。只能作废重签。"
         "所以 `.env` 进 ignore，仓库只留 `.env.example`。"),
        ("Q：为什么没用 MCP？",
         "A：课程要求「自定义工具 或 MCP」二选一，我选前者因为工具要读本地词库和模板。"
         "MCP 化只需把 7 个工具挂成 stdio server，参数表和返回格式都不用改。"),
    ]
    y = 236
    for q, a in qas:
        card(slide, 650, y, 562, 104)
        text(slide, 670, y + 12, 524, 84, [f"**{q}**", a], size=13.4, color=BODY,
             spacing=1.45, space_after=3)
        y += 112
    pageno(slide, 12)
    return slide


# ---------------- 备注：把讲稿贴进备注栏 ----------------
def load_notes() -> dict[int, str]:
    md = (ROOT / "docs" / "defense-script.md").read_text(encoding="utf-8").splitlines()
    notes, page, collecting = {}, None, False
    for line in md:
        m = re.match(r"^##\s*p(\d+)\s*[｜|]", line)
        if m:
            page, collecting = int(m.group(1)), False
            continue
        if page and "照念" in line:
            collecting = True
            continue
        if collecting:
            if line.strip().startswith(">"):
                notes.setdefault(page, []).append(line.strip()[1:].strip())
            elif line.strip() == "":
                continue
            else:
                collecting = False
    return {k: "\n".join(v).replace("**", "") for k, v in notes.items()}


def main():
    prs = Presentation()
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    for fn in (s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12):
        fn(prs)

    notes = load_notes()
    # 第 10 页在稿子里是提词板（不上台念），备注就放五条话术原文，演示时照着敲
    notes[10] = (
        "1）主路径：帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词\n"
        "2）记忆：今天该复习哪几个词？我 mitigate 又记混了\n"
        "3）压轴：粘贴框里先放一段别的题材英文 → 点「用这篇开始精读」\n"
        "4）边界：帮我把这篇文章翻译成中文，我要抄到作业里交（应被拒绝）\n"
        "5）备用：把这几个词做成 CSV：mitigate, incentive, cumulative, viable\n"
        "演示前：跑 scripts/reset_demo.py 清场；网络不稳就先跑一遍留产物兜底。"
    )
    for i, slide in enumerate(prs.slides, start=1):
        if i in notes:
            slide.notes_slide.notes_text_frame.text = notes[i]

    prs.save(OUT)
    print(f"OK {OUT}  {OUT.stat().st_size / 1024:.0f} KB  {len(prs.slides._sldIdLst)} 页")


if __name__ == "__main__":
    main()
