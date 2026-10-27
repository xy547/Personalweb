"""工具三：生成精读练习页 HTML。

这个工具做了两件事：
1. 用 skills/intensive-reading/template.html 做版式，Agent 只负责内容；
2. 对原文做「挖空」——把目标词（含 emissions / mitigated 这类变形）
   替换成下划线，形成填空练习。

把版式和内容分开，好处是换皮肤不用改 Agent，改 Agent 逻辑也不用碰 HTML。
"""

import json
import re
from datetime import date

from langchain_core.tools import tool

from config import SKILL_DIR, safe_output_path

TEMPLATE_PATH = SKILL_DIR / "intensive-reading" / "template.html"


def _word_pattern(word: str) -> re.Pattern:
    """生成能匹配常见词形变化的正则：复数、三单、过去式、进行时。

    只加后缀是不够的。以 e 结尾的词要去掉 e 再加 -ing/-ed
    （mitigate -> mitigating / mitigated），以辅音+y 结尾的要变 ies/ied
    （quantify -> quantifies / quantified）。漏掉这两条，原文里的变形就不会被挖空。
    """
    w = word.strip().lower()
    forms = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing"}
    if w.endswith("e"):
        forms |= {w[:-1] + "ing", w[:-1] + "ed"}
    if len(w) > 2 and w.endswith("y"):
        forms |= {w[:-1] + "ies", w[:-1] + "ied"}
    alts = "|".join(sorted({re.escape(f) for f in forms}, key=len, reverse=True))
    return re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)


def _mask(text: str, words: list[str]) -> tuple[str, int]:
    hits = 0
    for w in sorted({x for x in words if x}, key=len, reverse=True):
        text, n = _word_pattern(w).subn("______", text)
        hits += n
    return text, hits


def _parse_words(words: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,\n|、;；\s]+", words or "") if w.strip()]


@tool
def build_worksheet_html(
    title: str, article: str, words: str, filename: str = "worksheet.html"
) -> str:
    """把一篇英文原文 + 一组生词，生成一份可打印的精读练习页 HTML。

    参数说明：
    title    练习页标题，用中文写，例如「环保主题外刊精读」
    article  英文原文全文，保留段落换行
    words    需要挖空练习的单词，用逗号分隔，例如 "mitigate,incentive,subsidy"
    filename 输出文件名，工具会自动写进 outputs/ 目录

    该工具会自动把原文中的这些词替换成下划线空格，并在页尾生成生词表与自测清单。
    """
    articles = [p.strip() for p in (article or "").split("\n") if p.strip()]
    if not articles:
        return "ERROR: article 为空，无法生成练习页。"

    word_list = _parse_words(words)

    masked_paragraphs, total_hits = [], 0
    for para in articles:
        masked, hits = _mask(para, word_list)
        masked_paragraphs.append(masked)
        total_hits += hits

    para_html = "\n".join(f"<p>{p}</p>" for p in masked_paragraphs)
    blank_html = "\n".join(
        f'<li><span class="num">{i + 1}</span><span class="blank"></span>'
        f'<span class="hint">（{"&nbsp;" * max(len(w) - 1, 3)}）</span></li>'
        for i, w in enumerate(word_list)
    )
    bank = "　".join(word_list)

    tpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        tpl.replace("%%TITLE%%", title or "英文精读练习")
        .replace("%%DATE%%", date.today().isoformat())
        .replace("%%WORDS%%", str(len(word_list)))
        .replace("%%HITS%%", str(total_hits))
        .replace("%%BANK%%", bank)
        .replace("%%ARTICLE%%", para_html)
        .replace("%%BLANKS%%", blank_html)
    )

    target = safe_output_path(filename, ".html")
    target.write_text(html, encoding="utf-8")

    return json.dumps(
        {
            "status": "ok",
            "path": f"outputs/{target.name}",
            # 与 make_wordlist_csv 一致：相对路径用户打不开，完整路径由工具给出。
            "absolute_path": str(target),
            "open_hint": "告诉用户位置时给出 absolute_path 的完整路径；"
            "并说明界面侧边栏「产出文件」有下载按钮、回复下方也有「下载 / 直接打开」按钮。",
            "words": len(word_list),
            "blanks_filled_in_article": total_hits,
            "note": "已把目标词在原文中挖空，页尾附生词库与自测清单。",
        },
        ensure_ascii=False,
    )
