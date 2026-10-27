"""工具一：离线词库查词。

设计意图（这也是汇报时要讲的一点）：
这个工具只做一件事——把「词」变成「可核验的结构化词条」。
如果模型不调用它、凭记忆给释义，它可能给出过时的词频、错误的考纲等级、
甚至编造音标；而工具返回的每一条都来自 data/lexicon.json，可复查。
查不到时它明确回 NOT_FOUND，而不是猜一个——让模型知道该承认不确定。

词库从最初手写的 49 条扩到 6161 条（高考 / 四级 / 六级三档，
见 scripts/build_lexicon.py）。查不到时还会依次尝试词形还原
（consolidates → consolidate）和英美拼写变体（summarise → summarize），
所以实测「未收录」率明显下降。
"""

import json
import re

from langchain_core.tools import tool

from tools.lexicon import load_lexicon, lookup_with_variant


@tool
def lookup_word(word: str) -> str:
    """在本地词库中查一个英文单词，返回音标、词性、中文释义、例句和考纲等级。

    参数 word 只传单个英文单词，不要带句子或标点。传文章里的原样形式即可
    （consolidates、rereading 都行），工具会自己还原词形。

    如果返回 NOT_FOUND，说明该词不在本地词库中，你必须明确告诉用户
    「这个词不在本地词库内，释义来自模型推断，请自行核对」，不要假装查到了。
    如果返回里带 matched_spelling，说明词库收录的是另一个写法（词形变化或
    英美拼写差异），音标与释义取自那个写法——不要把它说成拼写错误，
    也不要因为写法不同就说「未收录」。
    """
    key = (word or "").strip().lower().strip(".,!?;:\"'()[]")
    if not key:
        return "ERROR: word 参数为空。"

    if not re.fullmatch(r"[a-z][a-z' \-]*", key):
        # 词库只有英语。日语汉字/假名、法语带冠词的名词（une mesure）都会落到这里。
        # 早先一律回 NOT_FOUND，结果模型以为自己「查过但库里没有」，
        # 于是把整篇的每个词都挨个试一遍，白烧十几次调用还不改口。
        # 这里直接说明工具边界，让它换正确的做法。
        from agent.languages import get as get_lang
        from tools.memory import load_profile

        lang = get_lang(load_profile().get("language", "en"))
        if lang["code"] != "en":
            return (
                f"NOT_SUPPORTED: 当前学习语种是{lang['name']}，本地词库只覆盖英语。\n"
                f"不要再用本工具查{lang['name']}词。直接给出释义与注音，"
                "并在回复和产出文件里说明「未经词库校验」。"
            )

    lexicon = load_lexicon()
    entry, matched = lookup_with_variant(key)
    if entry is None:
        return (
            f"NOT_FOUND: '{key}' 不在本地词库（共 {len(lexicon)} 条）中。"
            "请不要编造音标与考纲等级，向用户说明该词释义仅为模型推断。"
        )

    payload = {
        "word": key,
        "phonetic": entry["phonetic"],
        "pos": entry["pos"],
        "cn": entry["cn"],
        "example": entry["example"],
        "level": entry["level"],
        "source": "data/lexicon.json",
    }
    if matched and matched != key:
        payload["matched_spelling"] = matched
        payload["note"] = (
            f"词库收录的写法是 '{matched}'，音标与释义取自该条目。"
            "这是词形变化或英美拼写差异，不要当成拼写错误，也不要另编一套释义。"
        )
    return json.dumps(payload, ensure_ascii=False)
