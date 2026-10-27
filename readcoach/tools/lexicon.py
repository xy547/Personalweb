"""本地词库的共享访问层。

dictionary（查词）和 wordlist（生成词表）读的是同一份 lexicon.json。
把读取抽出来，一是避免重复 IO，二是保证两处对「什么算已收录」的判断一致——
否则会出现「查词说没收录、词表却给了 CET-6 等级」这种前后矛盾的输出，
模型自己就把幻觉补圆了。
"""

import json
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parent.parent / "data" / "lexicon.json"


@lru_cache(maxsize=1)
def load_lexicon() -> dict:
    with open(LEXICON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup(word: str) -> dict | None:
    """精确命中优先，英式/美式拼写变体兜底（见下方 lookup_with_variant）。"""
    return lookup_with_variant(word)[0]


# 英式/美式拼写不一致，会让一个明明收录了的词变成「未收录」。
# 实测：外刊里写 summarise / behaviour，词库里收的是 summarize / behavior，
# 于是工具回 NOT_FOUND，模型只能标「模型推断」——白白丢掉一条可核验的数据。
# 所以精确查不到时，换几个常见拼写再试一次。
_VARIANT_SUFFIXES = (
    ("isation", "ization"),
    ("ization", "isation"),
    ("ising", "izing"),
    ("izing", "ising"),
    ("ised", "ized"),
    ("ized", "ised"),
    ("ise", "ize"),
    ("ize", "ise"),
    ("yse", "yze"),
    ("yze", "yse"),
    ("ogue", "og"),
    ("tre", "ter"),
    ("ter", "tre"),
)


def _variants(key: str) -> list[str]:
    cands: list[str] = []
    for a, b in _VARIANT_SUFFIXES:
        if key.endswith(a) and len(key) > len(a) + 1:
            cands.append(key[: -len(a)] + b)
    if "our" in key:
        cands.append(key.replace("our", "or"))
    if "or" in key:
        cands.append(key.replace("or", "our"))
    return [c for c in dict.fromkeys(cands) if c != key]


def _lemmas(key: str) -> list[str]:
    """粗糙但够用的还原：复数、三单、过去式、进行时。

    实测：文章里写 consolidates / impairs / rereading，词库里只有原形，
    精确查不到就变成「未收录」——学生拿到的是一堆「模型推断」，
    而他明明只差一个 -s。这一步把变形映射回原形。
    只取长度 ≥4 的候选，避免 news→new、his→hi 这类误伤。
    """
    out: list[str] = []
    if key.endswith("ies"):
        out.append(key[:-3] + "y")
    if key.endswith("es"):
        out.append(key[:-2])
    if key.endswith("s") and not key.endswith("ss"):
        out.append(key[:-1])
    if key.endswith("ied"):
        out.append(key[:-3] + "y")
    if key.endswith("ed"):
        out += [key[:-2], key[:-1]]
        if len(key) > 4 and key[-3] == key[-4]:
            out.append(key[:-3])
    if key.endswith("ing"):
        out += [key[:-3], key[:-3] + "e"]
        if len(key) > 4 and key[-4] == key[-5]:
            out.append(key[:-4])
    return [c for c in dict.fromkeys(out) if c != key and len(c) >= 4]


def lookup_with_variant(word: str) -> tuple[dict | None, str]:
    """返回 (词条, 实际命中的写法)。命中变形或异体拼写时，第二个值与原词不同。

    顺序：精确 → 词形还原 → 英美拼写变体 → 先还原再换拼写。
    """
    key = (word or "").strip().lower().strip(".,!?;:\"'()[]")
    if not key:
        return None, ""
    lex = load_lexicon()
    if key in lex:
        return lex[key], key
    for cand in _lemmas(key):
        if cand in lex:
            return lex[cand], cand
    for cand in _variants(key):
        if cand in lex:
            return lex[cand], cand
    for lemma in _lemmas(key):
        for cand in _variants(lemma):
            if cand in lex:
                return lex[cand], cand
    return None, ""
