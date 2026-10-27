"""语种注册表：把「英语」从代码里抽成一份可扩展的配置。

为什么要单独一个文件：
项目原本处处写着 CET-6——提示词、词表、练习页、界面提示。想加一个语种，
就得把这些字符串全找出来改一遍，而且很容易漏。抽成注册表之后，
加一个语种 = 在这里加一条字典，其余代码按 `lang["levels"]`、`lang["sound"]` 取值。

每个语种要交代清楚四件事，缺一项都会让产出不专业：

1. **等级体系**：CET / JLPT / DELF / Goethe / DELE 是四套完全不同的分档，
   共用「CET-6」这个词就是错的。
2. **注音形态**：英语是 IPA，日语是假名＋罗马音，法德西仍是 IPA——
   但词表里那一列叫什么、由谁填，三种情况不一样。
3. **词库覆盖**：只有英语有本地可核验词库（6161 条）。其余语种退回「模型推断」，
   并且必须在文件里写明——这是这个项目最该老实说清的一条边界。
4. **词形规矩**：法语名词要带冠词、德语名词要大写并带 der/die/das、
   日语动词要给辞书形。这些是外语学习者真正会踩的坑，不是装饰。

新闻源也放在这里：多语种站点的正文容器是同一个（div#detail），
所以抓取逻辑共用一份，各语种只差一个首页地址。
"""

from __future__ import annotations

LANGS: dict[str, dict] = {
    "en": {
        "code": "en",
        "name": "英语",
        "native": "English",
        "flag": "🇬🇧",
        "word_of": "生词",
        "level_system": "考纲 / 考试",
        "levels": ["CET-4", "CET-6", "考研", "IELTS 6.5", "TOEFL 90"],
        "default_level": "CET-6",
        "sound": "IPA 音标",
        "sound_by": "工具（本地词库）",
        "lexicon": True,
        "site": "https://english.news.cn/",
        "site_name": "新华网英文版",
        # 提示词里给模型的语种纪律，一条一行，直接拼进系统提示词。
        "notes": [
            "目标考生按 {level} 准备。标为「高考」的词不算生词，不要挑进{word_of}表；"
            "优先 CET-4 / CET-6 / IELTS 档。",
            "音标一律由 lookup_word 从本地词库提供，你没有这个字段的写入权。",
        ],
    },
    "ja": {
        "code": "ja",
        "name": "日语",
        "native": "日本語",
        "flag": "🇯🇵",
        "word_of": "生词",
        "level_system": "JLPT",
        "levels": ["JLPT N5", "JLPT N4", "JLPT N3", "JLPT N2", "JLPT N1"],
        "default_level": "JLPT N3",
        "sound": "假名 + 罗马音",
        "sound_by": "模型（本地无该语种词库）",
        "lexicon": False,
        "site": "https://jp.news.cn/",
        "site_name": "新华网日文版",
        "notes": [
            "本语种**没有本地词库**：释义、注音（假名＋罗马音）、JLPT 等级都由你给出，"
            "但必须在回复里说明「未经词库校验，请以教材或权威辞典核对」。",
            "词表的 word 列写原文表记（汉字或假名均可），**第 6 个字段填「假名(罗马音)」**，"
            "例如 影響(えいきょう, eikyou)。不要填 IPA。",
            "动词给辞书形（書く 而不是 書きます），形容词给原形；"
            "挑词时优先 {level} 附近的实词（名词/动词/形容词），不要挑助词、助动词。",
            "讲解要指出的语法点：助词搭配（に/を/が）、自他动词、敬语等级，这三项是中国学习者最常错的。",
        ],
    },
    "fr": {
        "code": "fr",
        "name": "法语",
        "native": "Français",
        "flag": "🇫🇷",
        "word_of": "生词",
        "level_system": "DELF/DALF",
        "levels": ["DELF A2", "DELF B1", "DELF B2", "DALF C1"],
        "default_level": "DELF B1",
        "sound": "IPA 音标（法语音标）",
        "sound_by": "模型（本地无该语种词库）",
        "lexicon": False,
        "site": "https://french.news.cn/",
        "site_name": "新华网法文版",
        "notes": [
            "本语种**没有本地词库**：释义、音标、DELF 等级都由你给出，"
            "但必须在回复里说明「未经词库校验，请以教材或权威辞典核对」。",
            "词表 word 列写名词时**带上不定冠词**（un/une），并注明阴阳性，例如 une mesure（f.）；"
            "动词给不定式。第 6 个字段填法式 IPA（不要用英语音标糊过去）。",
            "挑词时优先 {level} 附近的实词；连词、介词不单独成条。",
            "讲解要指出的语法点：性数配合、动词变位组别、代词位置（y/en）、连诵。",
        ],
    },
    "de": {
        "code": "de",
        "name": "德语",
        "native": "Deutsch",
        "flag": "🇩🇪",
        "word_of": "生词",
        "level_system": "Goethe-Zertifikat",
        "levels": ["Goethe A2", "Goethe B1", "Goethe B2", "TestDaF"],
        "default_level": "Goethe B1",
        "sound": "IPA 音标（德语音标）",
        "sound_by": "模型（本地无该语种词库）",
        "lexicon": False,
        "site": "https://german.news.cn/",
        "site_name": "新华网德文版",
        "notes": [
            "本语种**没有本地词库**：释义、音标、等级都由你给出，"
            "但必须在回复里说明「未经词库校验，请以教材或权威辞典核对」。",
            "名词必须**首字母大写并带定冠词**：der/die/das，例如 die Maßnahme；"
            "动词给不定式，可分动词写成 an|bieten 这样的形式。第 6 个字段填德式 IPA。",
            "挑词时优先 {level} 附近的实词；冠词、人称代词不单独成条。",
            "讲解要指出的语法点：名词性别与复数、四格变化、可分动词、框型结构（动词第二位/句末）。",
        ],
    },
    "es": {
        "code": "es",
        "name": "西班牙语",
        "native": "Español",
        "flag": "🇪🇸",
        "word_of": "生词",
        "level_system": "DELE",
        "levels": ["DELE A2", "DELE B1", "DELE B2", "DELE C1"],
        "default_level": "DELE B1",
        "sound": "IPA 音标（西语音标）",
        "sound_by": "模型（本地无该语种词库）",
        "lexicon": False,
        "site": "https://spanish.news.cn/",
        "site_name": "新华网西文版",
        "notes": [
            "本语种**没有本地词库**：释义、音标、DELE 等级都由你给出，"
            "但必须在回复里说明「未经词库校验，请以教材或权威辞典核对」。",
            "名词写原形并标阴阳性（m./f.），必要时带冠词 el/la；动词给不定式。"
            "第 6 个字段填西式 IPA，并注意重音位置。",
            "挑词时优先 {level} 附近的实词；介词、连词不单独成条。",
            "讲解要指出的语法点：ser/estar、虚拟式、名词性数一致、反身动词。",
        ],
    },
}

DEFAULT_CODE = "en"


def codes() -> list[str]:
    return list(LANGS.keys())


def get(code: str | None) -> dict:
    """取语种配置；未知代码一律回落到英语，不让界面因为一个坏值崩掉。"""
    return LANGS.get((code or "").strip().lower(), LANGS[DEFAULT_CODE])


def names() -> dict[str, str]:
    """{code: 显示名}，给下拉框用。"""
    return {c: f"{v['flag']} {v['name']} · {v['native']}" for c, v in LANGS.items()}


def level_belongs(code: str, level: str) -> bool:
    """判断某个等级字符串是否属于该语种的体系（切换语种时用来决定要不要重置）。"""
    return (level or "").strip() in get(code)["levels"]


def label(code: str) -> str:
    """一句话描述，界面上显示成「日语 · JLPT N3 · 假名 + 罗马音」。"""
    lang = get(code)
    return f"{lang['name']} · {lang['level_system']} · {lang['sound']}"
