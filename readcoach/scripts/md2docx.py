"""把 docs/ 里的讲稿 markdown 排成可打印的 Word。

只覆盖这份稿子实际用到的语法：标题(#/##/###)、表格、引用块、无序列表、
分隔线、加粗、行内代码。够用就好，不引第三方 markdown 库——多一个依赖，
答辩机器上就多一个装不上的风险。

排版目标很具体：**拿在手上念**。所以正文 10.5pt、行距 1.45、A4 页边距 2.2cm，
一页能装下 25 行左右；标题带左侧色条，方便台上翻页时一眼找到「p6」。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CJK = "微软雅黑"
MONO = "Consolas"
INK = RGBColor(0x1F, 0x29, 0x37)
ACCENT = RGBColor(0x1A, 0x4F, 0xA8)
MUTED = RGBColor(0x6B, 0x76, 0x86)


# ---------- 低层 XML 小工具 ----------
def _set_font(run, name=CJK, size=None, bold=None, color=None, mono=False):
    run.font.name = MONO if mono else name
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    # 中英混排必须显式写 eastAsia，否则中文会掉回宋体、大小不一
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    fonts.set(qn("w:eastAsia"), CJK)
    fonts.set(qn("w:ascii"), MONO if mono else CJK)
    fonts.set(qn("w:hAnsi"), MONO if mono else CJK)


def _shade(element, hex_fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    element.append(shd)


def _para_border(paragraph, side="left", color="1A4FA8", size=18, space=6):
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), color)
    borders.append(el)


def _keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


# 表情符号在 Word 里靠字体替换凑出来，打印会变成怪怪的小方块，
# 而且它们后面的文字（照念 / 可删 / 动作）已经把意思说完了，直接去掉。
DROP_CHARS = str.maketrans("", "", "🎤➕⌫⏱👉✅❌💡📌")


def clean(text: str) -> str:
    s = (text or "").translate(DROP_CHARS)
    s = s.replace("\u3000 ", " ").replace(" \u3000", " ").replace("\u3000\u3000", "\u3000")
    return s.strip()


# ---------- 行内标记：**粗体** 与 `代码` ----------
TOKEN = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def _add_inline(paragraph, text, size=10.5, color=INK, bold=False):
    for part in TOKEN.split(clean(text)):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            _set_font(run, size=size, bold=True, color=color)
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            _set_font(run, size=size - 0.5, color=RGBColor(0xB4, 0x2A, 0x2A), mono=True)
        else:
            run = paragraph.add_run(part)
            _set_font(run, size=size, bold=bold, color=color)


# ---------- 块级 ----------
def _heading(doc, text, level):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if level == 1:
        pf.space_before = Pt(20)
        pf.space_after = Pt(10)
        size, color = 19, ACCENT
        _para_border(p, "bottom", "D6E0F0", 8, 4)
    elif level == 2:
        pf.space_before = Pt(18)
        pf.space_after = Pt(8)
        size, color = 14.5, ACCENT
        _para_border(p, "left", "1A4FA8", 24, 8)
        pf.left_indent = Cm(0.25)
    else:
        pf.space_before = Pt(12)
        pf.space_after = Pt(6)
        size, color = 12, INK
    _keep_with_next(p)
    _add_inline(p, text, size=size, color=color, bold=True)
    return p


def _quote(doc, lines):
    """引用块 = 台上要念的话。整块加灰底 + 左色条，扫一眼就知道哪块是嘴要动的。"""
    for i, line in enumerate(lines):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.55)
        pf.right_indent = Cm(0.3)
        pf.space_before = Pt(6) if i == 0 else Pt(0)
        pf.space_after = Pt(6) if i == len(lines) - 1 else Pt(2)
        pf.line_spacing = 1.5
        # 一段要念的话被翻页切断，台上很容易接不上；整块推到下一页更安全
        if i < len(lines) - 1:
            pf.keep_with_next = True
        _shade(p._p.get_or_add_pPr(), "F2F6FC")
        _para_border(p, "left", "1A4FA8", 24, 10)
        _add_inline(p, line, size=11.5, color=RGBColor(0x11, 0x1C, 0x2B))


def _bullets(doc, items):
    for item in items:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.75)
        pf.first_line_indent = Cm(-0.35)
        pf.space_before = Pt(1)
        pf.space_after = Pt(1)
        pf.line_spacing = 1.45
        # 待办清单：勾选框用中文字体能显示的 □，不要用 ☐ / [ ]
        todo = re.match(r"^\[[ xX]\]\s*(.*)$", item)
        mark = "□ " if todo else "· "
        if todo:
            item = todo.group(1)
        run = p.add_run(mark)
        _set_font(run, size=10.5, color=ACCENT, bold=True)
        _add_inline(p, item)


def _code_block(doc, lines):
    """命令行 / 代码：等宽字体 + 浅灰底，逐行保留，不能当成正文断句。"""
    for i, line in enumerate(lines):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.5)
        pf.space_before = Pt(4) if i == 0 else Pt(0)
        pf.space_after = Pt(4) if i == len(lines) - 1 else Pt(0)
        pf.line_spacing = 1.15
        _shade(p._p.get_or_add_pPr(), "F4F6F9")
        run = p.add_run(line if line else " ")
        _set_font(run, size=9.5, color=RGBColor(0x2A, 0x34, 0x44), mono=True)


def _body(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.45
    _add_inline(p, text)
    return p


def _rule(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    _para_border(p, "bottom", "E3E8EF", 6, 1)


def _rows_keep_together(table):
    """整张表尽量别被分页拆开：表头跨页重复，行内不许断。

    实测问题：7 行的表正好卡在页底，表头留在上一页、内容从下一页开始，
    打印出来就是「一张没有表头的表」。短表整体推到下一页比拆开好读。
    """
    rows = table.rows
    for idx, row in enumerate(rows):
        tr_pr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        tr_pr.append(cant)
        if idx == 0:
            tr_pr.append(OxmlElement("w:tblHeader"))
        if idx < len(rows) - 1:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True


def _col_widths(header, body, total_cm):
    """按各列内容的平均长度分配列宽。

    为什么不用 Word 的 autofit：演示那张表四列字数差别很大，
    「嘴上说什么」那一列最长，autofit 会把它压成窄条、每行折成七八行。
    这里按平均字数加权，再给最长的列保底宽度，念稿时一眼能扫到。
    """
    n = len(header)
    if n == 0:
        return []
    weights = []
    for i in range(n):
        lens = [len(re.sub(r"[*`]", "", r[i])) for r in body if i < len(r)]
        avg = sum(lens) / len(lens) if lens else len(header[i])
        weights.append(max(avg, 4))
    # 开方压缩极端差距，避免某列独吞整行
    weights = [w ** 0.5 for w in weights]
    total_w = sum(weights)
    widths = [total_cm * w / total_w for w in weights]
    # 任何一列不低于 1.6cm，其余按比例补给最长的列
    min_w = 1.6
    for _ in range(3):
        deficit = sum(min_w - w for w in widths if w < min_w)
        if deficit <= 0:
            break
        for i, w in enumerate(widths):
            if w < min_w:
                widths[i] = min_w
        longest = widths.index(max(widths))
        widths[longest] -= deficit
    return widths


def _table(doc, rows):
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # 页面可用宽度：21cm - 左右各 2.2cm 边距
    widths = _col_widths(header, body, 16.6)
    if widths:
        for i, w in enumerate(widths):
            for cell in table.columns[i].cells:
                cell.width = Cm(w)

    for i, cell_text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        _shade(cell._tc.get_or_add_tcPr(), "EAF1FB")
        _add_inline(p, cell_text, size=10, color=ACCENT, bold=True)

    for row in body:
        cells = table.add_row().cells
        for i, cell_text in enumerate(row[: len(header)]):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            _add_inline(p, cell_text, size=10)

    # add_row 新建的单元格不继承列宽，必须再按行设一次
    if widths:
        for row in table.rows:
            for i, w in enumerate(widths):
                if i < len(row.cells):
                    row.cells[i].width = Cm(w)

    _rows_keep_together(table)

    # 表格后面留一点气口，不然下一段会贴着表框
    gap = doc.add_paragraph()
    gap.paragraph_format.space_before = Pt(0)
    gap.paragraph_format.space_after = Pt(0)
    gap.paragraph_format.line_spacing = 0.6


def convert(md_path: Path, out_path: Path, footer_text: str = "") -> Path:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    doc = Document()

    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2.2)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = CJK
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CJK)

    if footer_text:
        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run(footer_text)
        _set_font(run, size=9, color=MUTED)

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 分隔线
        if re.fullmatch(r"---+", stripped):
            _rule(doc)
            i += 1
            continue

        # 围栏代码块 ```lang ... ```
        if stripped.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i].rstrip())
                i += 1
            i += 1  # 跳过收尾的 ```
            _code_block(doc, block or [""])
            continue

        # 表格：连续的 | 开头行
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip().strip("|")
                cells = [c.strip() for c in row.split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    block.append(cells)
                i += 1
            if block:
                _table(doc, block)
            continue

        # 引用块：连续的 > 行
        if stripped.startswith(">"):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i].strip()[1:].strip())
                i += 1
            # 引用块里空行分段，这里保留为同一块（稿子里用于整段照念）
            _quote(doc, [b for b in block if b] or [""])
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            _heading(doc, m.group(2), min(len(m.group(1)), 3))
            i += 1
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            _bullets(doc, items)
            continue

        # 有序列表：保留原编号，避免重新编号与稿子里的「p6」对不上
        if re.match(r"^\d+[.)]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append(lines[i].strip())
                i += 1
            for item in items:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.75)
                p.paragraph_format.first_line_indent = Cm(-0.4)
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.45
                _add_inline(p, item)
            continue

        _body(doc, stripped)
        i += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


if __name__ == "__main__":
    pairs = [
        ("docs/defense-script.md", "docs/发言稿-答辩.docx", "外刊精读教练 · 答辩发言稿"),
        ("docs/record-script.md", "docs/发言稿-录屏.docx", "外刊精读教练 · 录屏脚本"),
    ]
    for src, dst, footer in pairs:
        p = convert(Path(src), Path(dst), footer)
        print(f"OK {p}  {p.stat().st_size} bytes")
