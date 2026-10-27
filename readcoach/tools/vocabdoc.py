"""把词表 CSV 排成一份可以直接打印、也能在 Word 里继续编辑的 .docx。

为什么需要这个工具：
CSV 是给程序读的。用 Word 打开 CSV，所有字段挤在一行里，逗号连成一片——
学生真正要背的时候看的是纸，不是 Excel。班级里绝大多数人第一步都是
「把 CSV 复制进 Word」，然后手工排版，这也正是用户反馈的问题：
「标号序号、单词、音标、中文注解、用法依次排开，不要挤在一起」。

所以这里做的是**版式转换**，不是内容生成：
- 逐词一块：编号 / 单词 / 音标 / 词性 + 释义 / 考纲等级 / 用法例句，之间留白；
- 音标、释义、等级全部照抄 CSV（而 CSV 又来自词库），这一步不经过模型，
  所以排版再花哨也不会多出事实；
- 未收录的词明确标「词库未收录，释义为模型推断」，而不是留个空格让人误解。

依赖 python-docx（纯 Python，无 Office 依赖）。没装时给出明确提示，
不让 Agent 拿一个空文件糊弄用户。
"""

from __future__ import annotations

import csv
import datetime as _dt
from pathlib import Path

from langchain_core.tools import tool

from config import OUTPUT_DIR

UNVERIFIED = "未收录"
# 非英语语种专用：没有词库可查，不能说「未收录」（那是在断言词库查过了），
# 只能说「未校验」——它描述的是一件真事：没人核对过。
UNCHECKED = "未校验"


def _safe_read_path(filename: str) -> Path:
    """只允许读 outputs/ 下的文件，挡住 ../ 之类。"""
    raw = (filename or "").strip().strip('"').strip("'").replace("\\", "/")
    raw = raw.split("/")[-1]  # 只取文件名，忽略模型顺手带上的目录
    if not raw:
        raise ValueError("缺少 csv_filename")
    path = (OUTPUT_DIR / raw).resolve()
    if path.parent != OUTPUT_DIR.resolve():
        raise ValueError("只能读取 outputs 目录下的文件")
    if not path.exists():
        raise FileNotFoundError(raw)
    return path


def _set_cjk(run, name: str = "微软雅黑") -> None:
    """python-docx 不会自动设东亚字体，中文会退回 Calibri，字号看着不齐。"""
    from docx.oxml.ns import qn

    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(fonts)
    fonts.set(qn("w:eastAsia"), name)


def _hrule(paragraph, color: str = "D8DEE9") -> None:
    """在段落下方画一条细线，当作词块之间的分隔。"""
    from docx.oxml.ns import qn

    ppr = paragraph._p.get_or_add_pPr()
    pbdr = ppr.makeelement(qn("w:pBdr"), {})
    bottom = pbdr.makeelement(
        qn("w:bottom"),
        {
            qn("w:val"): "single",
            qn("w:sz"): "6",
            qn("w:space"): "6",
            qn("w:color"): color,
        },
    )
    pbdr.append(bottom)
    ppr.append(pbdr)


def render_docx(
    rows: list[dict], title: str, subtitle: str, target: Path, language: str = "en"
) -> None:
    """把词条写成 docx。抽成独立函数，便于自检里直接调用。"""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()

    # A4 + 2.2cm 页边距，跟打印版一致
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, attr, Cm(2.2))

    normal = doc.styles["Normal"]
    normal.font.size = Pt(10.5)

    # 页脚常驻合规提示：和界面底部那句一致，避免打印件被当成权威词典。
    # 英语有本地词库，可以说「来自词库」；其他语种没有，就必须说清是模型给的，
    # 否则打印出来的一张纸会被当成查证结果。
    try:
        from agent.languages import get as _get_lang

        _lang = _get_lang(language)
    except Exception:
        _lang = {"name": "英语", "lexicon": True, "sound": "音标"}
    foot_text = (
        "音标与释义来自本地词库，仅供参考，请以权威词典为准"
        if _lang.get("lexicon")
        else f"{_lang['name']}暂无本地词库：释义、注音与等级由模型生成，"
        "请以教材或权威辞典为准"
    )
    foot = section.footer.paragraphs[0]
    foot.alignment = 1  # center
    frun = foot.add_run(f"外刊精读教练 · {foot_text}")
    frun.font.size = Pt(8)
    frun.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)
    _set_cjk(frun)

    head = doc.add_paragraph()
    head.paragraph_format.space_after = Pt(2)
    run = head.add_run(title)
    run.bold = True
    run.font.size = Pt(19)
    _set_cjk(run)

    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(16)
    info = subtitle.strip() or "外刊精读 · 词汇笔记"
    run = meta.add_run(
        f"{info}　｜　共 {len(rows)} 个词　｜　"
        f"生成于 {_dt.datetime.now():%Y-%m-%d %H:%M}"
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
    _set_cjk(run)
    _hrule(meta, "9AA5B1")

    # 整份都是「模型推断」时（非英语语种），来源说明只在开头写一次。
    # 每个词下面重复一遍同样的话，读起来像免责声明刷屏，反而没人看。
    all_model = bool(rows) and all(
        (r.get("source") or "").strip() == "模型推断" for r in rows
    )
    if all_model:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        note = p.add_run(
            f"说明　本语种暂无本地词库，下表各词的释义、注音与等级均由模型生成，"
            "未经校验；背诵前请对照教材或权威辞典核对。"
        )
        note.font.size = Pt(9)
        note.italic = True
        note.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)
        _set_cjk(note)

    for idx, row in enumerate(rows, start=1):
        word = (row.get("word") or "").strip()
        phonetic = (row.get("phonetic") or "").strip()
        pos = (row.get("pos") or "").strip()
        cn = (row.get("cn") or "").strip()
        level = (row.get("level") or "").strip()
        source = (row.get("source") or "").strip()
        example = (row.get("example") or "").strip()

        # ① 编号 + 单词 + 右侧等级标签
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        # 一个词的四行必须同页：否则「单词留在页底、用法翻到下一页」，
        # 打印出来正好把最该连读的两行拆开。
        p.paragraph_format.keep_with_next = True
        num = p.add_run(f"{idx:02d}　")
        num.bold = True
        num.font.size = Pt(12)
        num.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
        _set_cjk(num)
        w = p.add_run(word)
        w.bold = True
        w.font.size = Pt(16)
        w.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
        _set_cjk(w, "Consolas")
        tag = p.add_run(f"　　〔{level or '—'}〕")
        tag.font.size = Pt(9)
        if level == UNVERIFIED:
            # 红：词库确实查不到（英语专用）
            tag.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        elif source == "模型推断":
            # 橙：该语种没有本地词库，等级是模型判断的，色彩上要和「查证过」区分开
            tag.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)
        else:
            tag.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        _set_cjk(tag)

        # ② 音标 / 词性 / 释义 —— 三项用全角空格分开，不挤在一起
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Cm(1.05)
        p.paragraph_format.keep_with_next = True
        ph = p.add_run(phonetic if phonetic else "—")
        ph.font.size = Pt(11)
        ph.font.color.rgb = (
            RGBColor(0x9A, 0xA3, 0xAF) if not phonetic else RGBColor(0x1D, 0x4E, 0xD8)
        )
        _set_cjk(ph, "Segoe UI")
        mid = p.add_run(f"　　{pos or ''}　")
        mid.font.size = Pt(11)
        mid.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        _set_cjk(mid)
        mean = p.add_run(cn)
        mean.font.size = Pt(11)
        mean.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
        _set_cjk(mean)

        # ③ 用法：单独起一行，前面加「用法」二字，与上面的释义分开
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(1.05)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        label = p.add_run("用法　")
        label.bold = True
        label.font.size = Pt(9.5)
        label.font.color.rgb = RGBColor(0x0F, 0x76, 0x6E)
        _set_cjk(label)
        sent = p.add_run(example if example else "（本轮未提供例句）")
        sent.font.size = Pt(10.5)
        sent.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
        _set_cjk(sent)

        # ④ 未收录 / 未经校验的词必须写明来源，不能让读者以为查证过。
        # 整份都是模型推断时，第 ① 步已在开头统一说明，这里不再逐条重复。
        if not all_model and (level == UNVERIFIED or source == "模型推断"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.05)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            note_text = (
                "注　该词不在本地词库，释义与用法为模型推断，音标请自行核对。"
                if _lang.get("lexicon")
                else f"注　{_lang['name']}暂无本地词库；释义、注音与等级均为模型推断，"
                "请对照教材或辞典核对。"
            )
            note = p.add_run(note_text)
            note.font.size = Pt(9)
            note.italic = True
            note.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)
            _set_cjk(note)

        # ⑤ 分隔线，词与词之间留白
        sep = doc.add_paragraph()
        sep.paragraph_format.space_after = Pt(2)
        sep.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _hrule(sep)

    doc.save(str(target))


def _fill_levels(rows: list[dict], language: str = "en") -> list[dict]:
    """CSV 里没有 level / source 时，按单词现查词库补上（只用于排版，不回写 CSV）。

    等级本来就不是「存下来的数据」，而是「这个词在词库的哪一档」的一次查询结果。
    所以 CSV 删掉那两列不会丢信息：排版时再查一次就有了，
    而且查的是同一个 lexicon.json，结论必然一致。

    非英语语种没有词库：这时查不到不等于「未收录」，只能标「未校验」。
    把「这个词不在汉语之外任何词库里」写成「未收录」，是会误导人的假精确。
    """
    if language != "en":
        for row in rows:
            if not (row.get("level") or "").strip():
                row["level"] = UNCHECKED
            row["source"] = "模型推断"
        return rows
    try:
        from tools.lexicon import lookup
    except Exception:  # 词库不可用就退回「未收录」，宁可保守
        return rows
    for row in rows:
        if (row.get("level") or "").strip():
            continue
        try:
            known = lookup((row.get("word") or "").strip())
        except Exception:
            known = None
        if known:
            row["level"] = known.get("level") or ""
            row["source"] = "本地词库"
        else:
            row["level"] = UNVERIFIED
            row["source"] = "模型推断"
    return rows


def render_csv_file(
    src: Path, title: str = "", subtitle: str = "", language: str = "en"
) -> Path:
    """读一个 CSV → 排成同名 .docx，返回目标路径。

    抽成公开函数，让三个地方共用同一套版式：
    ① `build_vocab_doc` 工具（模型主动调用）；
    ② `make_wordlist_csv` 写盘后顺手排一份（用户不用再要一次）；
    ③ 界面侧边栏那个「排成 Word 笔记」按钮（不经过模型，确定性兜底）。
    只做排版，音标/释义/等级全部照抄 CSV，因此不会新增任何事实。

    title 留空时按语种取默认标题（「英语词汇精读笔记」/「日语词汇精读笔记」…）。
    """
    from agent.languages import get as _get_lang

    lang = _get_lang(language)
    with Path(src).open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("word") or "").strip()]
    if not rows:
        raise ValueError(f"{Path(src).name} 里没有有效词条")
    rows = _fill_levels(rows, language=lang["code"])
    target = Path(src).with_suffix(".docx")
    render_docx(
        rows,
        title or f"{lang['name']}词汇精读笔记",
        subtitle or f"{lang['level_system']} · 每日精读",
        target,
        language=lang["code"],
    )
    return target


@tool
def build_vocab_doc(
    csv_filename: str,
    title: str = "",
    subtitle: str = "",
    language: str = "",
) -> str:
    """把已经生成的词表 CSV 排成一份 Word 文档（.docx），逐词分块、可直接打印。

    什么时候用它：
    用户说「导成 Word / 想在 Word 里看 / 打印出来背 / 别都挤在一起」时，
    或者用户明确要「按序号把单词、音标、释义、用法分开列」。

    csv_filename 只写文件名，例如 "wordlist_cet6_lunar_race.csv"；
    文件必须已经在 outputs/ 里（先用 make_wordlist_csv 生成）。
    title 是文档大标题（留空按语种自动取），subtitle 是副标题（可以写文章来源或考试目标）。
    language 留空 = 用学习档案里的当前语种。

    本工具只做排版，不新增任何内容：音标、释义照抄 CSV，
    等级是按单词**现查词库**得到的（CSV 里没有这一列），
    未收录的词会自动加一行小字说明来源。产出仍是 .docx，可继续在 Word 里改。
    """
    from agent.languages import get as _get_lang

    code = (language or "").strip().lower()
    if not code:
        from tools.memory import load_profile

        code = load_profile().get("language", "en")
    lang = _get_lang(code)
    code = lang["code"]

    try:
        src = _safe_read_path(csv_filename)
    except FileNotFoundError:
        have = sorted(p.name for p in OUTPUT_DIR.glob("*.csv"))
        return (
            f"NOT_FOUND: outputs/{csv_filename} 不存在。现有 CSV："
            + (", ".join(have) if have else "（还没有）")
            + "。请先用 make_wordlist_csv 生成词表，再来排版。"
        )
    except ValueError as exc:
        return f"ERROR: {exc}"

    with src.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("word") or "").strip()]
    if not rows:
        return f"ERROR: {src.name} 里没有有效词条。"
    rows = _fill_levels(rows, language=code)

    try:
        target = render_csv_file(src, title, subtitle, language=code)
    except ModuleNotFoundError:
        return (
            "ERROR: 缺少 python-docx，无法生成 Word。"
            "请先运行 pip install python-docx，或改让用户下载 CSV。"
        )

    unverified = [r["word"] for r in rows if (r.get("level") or "") == UNVERIFIED]
    return (
        f"已生成 Word 文档：{target}\n"
        f"完整路径：{target}\n"
        f"共 {len(rows)} 个词，逐词分块（序号 / 单词 / 音标 / 词性+释义 / 用法）。\n"
        + (
            f"其中 {len(unverified)} 个词词库未收录（{ '、'.join(unverified) }），"
            "文档里已用小字标注「释义与用法为模型推断」。\n"
            if unverified
            else ""
        )
        + (
            ""
            if lang["lexicon"]
            else f"本语种（{lang['name']}）暂无本地词库，释义与注音由模型提供，"
            "文档页脚与每个词下都已注明，回复里也要说清楚。\n"
        )
        + "告诉用户位置时请给出上面的完整路径；界面侧边栏「产出文件」和回复下方也有下载按钮。"
    )
