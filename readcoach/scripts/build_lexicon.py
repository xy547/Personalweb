"""把开源的 高考 / CET-4 / CET-6 词表合并进 data/lexicon.json。

为什么需要这一步：
原先的词库是我手写的 49 条，只够演示内置那篇文章。换一篇文章，
几乎每个词都返回 NOT_FOUND——对「精读工具」来说这是致命短板。
同类软件第一步就是「有大词库」，所以这里把词库扩到三档全量。

数据来自开源词表项目 qwerty-learner（MIT）的 public/dicts：
    GaoKao_3500.json  3893 条（基础）
    CET4_T.json       2607 条
    CET6_T.json       2345 条

本脚本只做三件事：清洗音标、拆出词性与释义、合并去重。
级别按「由易到难」先到先得：一个词只要出现在高考 3500 里，就标「高考」——
对备考六级的用户来说，这类词根本不该被挑进生词表。

关键规则：**手写的 49 条优先**。那批词有条目完整的手写例句，
演示用的文章正是围着它们写的，不能被机器生成的字段覆盖掉。

注意：重建时必须从「只含手写条目」的 lexicon.json 开始，
否则上一次生成的条目会被当成手写条目，级别就永远改不回来了。

用法：
    .venv\\Scripts\\python scripts\\build_lexicon.py
    .venv\\Scripts\\python scripts\\build_lexicon.py gk.json c4.json c6.json
"""

import base64
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEXICON = ROOT / "data" / "lexicon.json"
CACHE = ROOT / "scripts" / "cache"
REPO_ID = 331603334

# 三档基础词表，按「由易到难」排列；先收录的级别优先。
# 为什么要有高考这一档：四六级词表收的是「新增难词」，attention / memory
# 这种极常用词反而不在里面。缺了它们，精读任何一篇文章都会满屏「未收录」。
FILES = (
    ("GaoKao_3500.json", "高考"),
    ("CET4_T.json", "CET-4"),
    ("CET6_T.json", "CET-6"),
)

POS_RE = re.compile(r"[\(（]\s*([a-z]+\.)\s*[\)）]")
LEAD_POS_RE = re.compile(r"^((?:[a-z]{1,5}\.)(?:&[a-z]{1,5}\.)*)\s*")
WORD_RE = re.compile(r"^[a-z][a-z-]*$")


def fetch(dict_name: str) -> list:
    """优先读本地缓存；没有就走 GitHub contents API（返回 base64）。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / dict_name
    if not path.exists():
        url = (
            f"https://api.github.com/repositories/{REPO_ID}"
            f"/contents/public/dicts/{dict_name}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "readcoach-build"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            meta = json.load(resp)
        path.write_bytes(base64.b64decode(meta["content"]))
        print(f"  下载 {dict_name}（{path.stat().st_size} 字节）")
    else:
        print(f"  缓存 {dict_name}")
    return json.loads(path.read_text(encoding="utf-8"))


def clean_phonetic(raw: str) -> str:
    """'kænsl -> /ˈkænsl/。原始数据里重音符号是撇号，换成 IPA 的 ˈ。"""
    p = (raw or "").strip()
    if not p:
        return ""
    p = p.replace("'", "ˈ").strip("/ ")
    return f"/{p}/"


def split_trans(items: list[str]) -> tuple[str, str]:
    """把 ['取消， 撤销， 删去 (vt.)'] 拆成 ('取消；撤销；删去', 'vt.')。

    词性有两种写法：四级/六级表写在后面括号里，高考表写在开头（"v.抛弃"）。
    两种都要认，否则高考那一档全是空词性。
    """
    pos = ""
    parts = []
    for raw in items:
        text = (raw or "").strip()
        m = POS_RE.search(text)
        if m:
            pos = pos or m.group(1)
            text = POS_RE.sub("", text)
        else:
            lead = LEAD_POS_RE.match(text)
            if lead:
                pos = pos or lead.group(1)
                text = text[lead.end():]
        if text:
            parts.append(text)
    cn = "；".join(parts)
    cn = cn.replace("，", "；").replace(",", "；")
    cn = re.sub(r"\s*；\s*", "；", cn)
    cn = re.sub(r"\s+", " ", cn).strip("； ")
    return cn, pos


def make_entry(item: dict, level: str) -> dict | None:
    word = (item.get("name") or "").strip().lower()
    if not WORD_RE.match(word):
        return None
    cn, pos = split_trans(item.get("trans") or [])
    if not cn:
        return None
    return {
        "phonetic": clean_phonetic(item.get("ukphone") or item.get("usphone") or ""),
        "pos": pos,
        "cn": cn,
        "example": "",
        "level": level,
    }


def build(local: list[str] | None = None):
    curated = json.loads(LEXICON.read_text(encoding="utf-8"))
    print(f"现有词库 {len(curated)} 条（手写，优先级最高）")

    entries: dict[str, dict] = {}
    for i, (dict_name, level) in enumerate(FILES):
        items = (
            json.loads(Path(local[i]).read_text(encoding="utf-8"))
            if local and i < len(local)
            else fetch(dict_name)
        )
        added = filled = 0
        for item in items:
            entry = make_entry(item, level)
            if not entry:
                continue
            key = item["name"].strip().lower()
            if key in entries:
                # CET-4 与 CET-6 有 1032 个词重叠：级别保留更容易的那个，
                # 但四级表没给词性，正好用六级表里的一栏补上。
                if not entries[key]["pos"] and entry["pos"]:
                    entries[key]["pos"] = entry["pos"]
                    filled += 1
                continue
            entries[key] = entry
            added += 1
        print(f"  {dict_name} → 新增 {added} 条，补词性 {filled} 条（级别 {level}）")

    merged = dict(curated)
    for key, entry in entries.items():
        merged.setdefault(key, entry)

    LEXICON.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    by_level: dict[str, int] = {}
    for e in merged.values():
        by_level[e["level"]] = by_level.get(e["level"], 0) + 1
    no_phone = sum(1 for e in merged.values() if not e["phonetic"])
    print(f"\n完成：{len(merged)} 条 → {LEXICON.relative_to(ROOT)}")
    print(f"  按级别：{by_level}")
    print(f"  无音标：{no_phone} 条　有话例句：{sum(1 for e in merged.values() if e['example'])} 条")


if __name__ == "__main__":
    build(sys.argv[1:] or None)
