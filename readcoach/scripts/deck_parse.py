"""把 代码解读.html 拆成结构化数据，供 build_code_pptx.py 渲染。

为什么要解析而不是手抄：
13 页里有 10 页是「左边一屏代码 + 右边四条批注」，代码里还有四种高亮色。
手抄一遍既容易错字，也会把 `-&gt;` 这类实体抄错。解析保证 PPT 里的代码
与 HTML 逐字一致，改 HTML 后重跑即可同步。
"""

from __future__ import annotations

import html as htmllib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "代码解读.html"

SPAN = re.compile(r'<span[^>]*?class="([a-z]+)"[^>]*>|<span[^>]*>|</span>|<br\s*/?>')
NOTE = re.compile(r'<div class="note( teal| warn| danger)?"[^>]*>(.*?)\n    </div>', re.S)
INLINE = re.compile(
    r'<code class="inline"[^>]*>(.*?)</code>|<b[^>]*>(.*?)</b>|<br\s*/?>|</?[^>]+>', re.S
)


def _plain(frag: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", frag))


def _balanced_div(s: str, start: int) -> tuple[str, int]:
    """从 s[start:] 里的 <div 开始，返回（内层 HTML，闭合标签之后的位置）。"""
    depth = 0
    for m in re.finditer(r"<div\b|</div>", s[start:]):
        if m.group(0) == "</div>":
            depth -= 1
            if depth == 0:
                inner_end = start + m.start()
                open_end = s.index(">", start) + 1
                return s[open_end:inner_end], start + m.end()
        else:
            depth += 1
    raise ValueError("div 未闭合")


# ---------- 代码块：保留每个字符的颜色类别 ----------
def parse_pre(frag: str) -> list[list[tuple[str, str]]]:
    lines: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    stack = ["p"]

    def push(text: str, cls: str) -> None:
        nonlocal cur
        if not text:
            return
        for i, seg in enumerate(text.split("\n")):
            if i:
                lines.append(cur)
                cur = []
            if seg:
                if cur and cur[-1][1] == cls:
                    cur[-1] = (cur[-1][0] + seg, cls)
                else:
                    cur.append((seg, cls))

    pos = 0
    for m in SPAN.finditer(frag):
        push(htmllib.unescape(frag[pos:m.start()]), stack[-1])
        pos = m.end()
        if m.group(1):
            stack.append(m.group(1))
        elif m.group(0).startswith("</span"):
            if len(stack) > 1:
                stack.pop()
        elif m.group(0).startswith("<span"):
            stack.append("p")
        else:  # <br>
            push("\n", stack[-1])
    push(htmllib.unescape(frag[pos:]), stack[-1])
    if cur:
        lines.append(cur)
    # 去掉行尾空白，保留缩进
    return [[(t, c) for t, c in line] for line in lines]


# ---------- 批注卡与行内富文本 ----------
def parse_inline(frag: str) -> list[tuple[str, str]]:
    """返回 [(文字, kind)]，kind ∈ p / b / code / nl。"""
    runs: list[tuple[str, str]] = []
    pos = 0
    for m in INLINE.finditer(frag):
        plain = htmllib.unescape(re.sub(r"<[^>]+>", "", frag[pos:m.start()]))
        if plain:
            runs.append((plain, "p"))
        pos = m.end()
        if m.group(1) is not None:
            runs.append((_plain(m.group(1)), "code"))
        elif m.group(2) is not None:
            runs.append((_plain(m.group(2)), "b"))
        elif m.group(0).startswith("<br"):
            runs.append(("\n", "nl"))
    tail = htmllib.unescape(re.sub(r"<[^>]+>", "", frag[pos:]))
    if tail:
        runs.append((tail, "p"))
    # 压掉多余空白（HTML 源码里的缩进换行不该带进 PPT）
    out: list[tuple[str, str]] = []
    for t, k in runs:
        if k != "nl":
            t = re.sub(r"\s+", " ", t)
            if not t.strip():
                continue
        out.append((t, k))
    return out


def parse_notes(frag: str) -> list[dict]:
    notes = []
    for m in re.finditer(r'<div class="note([^"]*)"', frag):
        cls = m.group(1).strip()
        body, _ = _balanced_div(frag, m.start())
        b = re.search(r"<b[^>]*>(.*?)</b>", body, re.S)
        p = re.search(r"<p[^>]*>(.*?)</p>", body, re.S)
        notes.append(
            {
                "tone": {"teal": "teal", "warn": "warn", "danger": "danger"}.get(cls, "plain"),
                "title": parse_inline(b.group(1)) if b else [],
                "body": parse_inline(p.group(1)) if p else [],
            }
        )
    return notes


def parse() -> list[dict]:
    src = SRC.read_text(encoding="utf-8")
    chunks = src.split('<div class="slide')[1:]
    pages = []
    for chunk in chunks:
        chunk = chunk[: chunk.index('<div class="slide')] if '<div class="slide' in chunk else chunk
        page = re.search(r'data-page="(\d+) /', chunk)
        header = re.search(r'<div class="kicker"[^>]*>(.*?)</div>', chunk, re.S)
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", chunk, re.S)
        item = {
            "no": int(page.group(1)) if page else 0,
            "kicker": _plain(header.group(1)) if header else "",
            "h2": _plain(h2.group(1)) if h2 else "",
            "cover": chunk.startswith(' cover"'),
        }
        pre = re.search(r"<pre[^>]*>(.*?)</pre>", chunk, re.S)
        if pre:
            item["code"] = parse_pre(pre.group(1))
        if '<div class="notes"' in chunk:
            inner, _ = _balanced_div(chunk, chunk.index('<div class="notes"'))
            item["notes"] = parse_notes(inner)
        tk = re.search(r'<div class="takeaway"[^>]*>(.*?)</div>\s*</div>', chunk, re.S)
        if not tk:
            tk = re.search(r'<div class="takeaway"[^>]*>(.*?)</div>', chunk, re.S)
        if tk:
            item["takeaway"] = parse_inline(tk.group(1))
        pages.append(item)
    return pages


if __name__ == "__main__":
    import json

    pages = parse()
    for p in pages:
        code_lines = len(p.get("code", []))
        notes = p.get("notes", [])
        tk = len("".join(t for t, _ in p.get("takeaway", [])))
        print(
            f"{p['no']:02d} 代码{code_lines:>3}行  批注{len(notes)}  收束{tk:>3}字  "
            f"{p['kicker'][:34]}"
        )
    Path(ROOT / "_code_deck.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n已写出 _code_deck.json")
