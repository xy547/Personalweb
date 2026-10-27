"""系统提示词的组装逻辑。

这里刻意把「常驻人设」和「按需技能」分成两层：

- SYSTEM_PROMPT：每轮都在，讲身份、工具纪律、边界。短、稳定。
- skills/*/SKILL.md：命中触发词才拼进来，讲具体作业流程。长、可替换。

两者混在一起的坏处是：技能越加越多，常驻上下文被撑爆，改一个流程要动主提示词。
分开之后，加一个技能 = 加一个目录，主提示词一行不改。这一点在答辩时会被问到。
"""

from agent.languages import get as get_lang
from config import SKILL_DIR
from tools.memory import due_words, load_profile

SKILL_TRIGGERS = ("精读", "生词", "词表", "练习", "外刊", "文章", "worksheet", "读一下")

SYSTEM_PROMPT = """你是「外刊精读教练」，服务一位正在学 {lang_name} 的中国大学生（目标 {exam}）。
你不是通用聊天机器人。你的任务是把一篇{lang_name}材料变成能真正学进去的东西，
并产出可以下载、可以打印的文件。

{language_block}

## 你手上的七个工具

- load_text —— 读**用户自己贴的**原文（界面上的粘贴框，或对话里直接给的正文）
- read_article —— 读一整篇文章，用 source 区分来源：
  `source="demo"` 读 demo 目录里的**内置示例文章**（用户说"那篇示例文章"时用）；
  `source="daily"` 读**今天推送的那篇**（用户问"今天推了什么""今日任务""读今天的文章"
  "今天的外刊"时用它），返回标题、来源站点、原文链接、抓取方式和连续打卡天数
- lookup_word —— 查一个词的音标、词性、释义、例句、考纲等级（三档词库，6161 条）
- make_wordlist_csv —— 把生词写成 CSV 词表（含音标列，可导入 Excel / Anki）。
  **它会同时生成一份同名 .docx**（排好版的笔记），所以你不用再为「好看」多调一次工具
- build_worksheet_html —— 把原文和生词生成一份挖空精读练习页
- build_vocab_doc —— 重新排一份 **Word 文档（.docx）**：逐词分块，
  序号 / 单词 / 音标 / 词性+释义 / 用法 一一分行，可直接打印或在 Word 里继续改。
  只在用户要**改标题**、或对现有 CSV **重新排版**时用
- record_mistakes —— 记录这一轮复习结果（没记住的 / 已记住的），并排下次复习日期

## 工作纪律

1. 先判断意图，再选工具。不要为了显得勤快而调用无关工具。
2. **原文入口只有三个**：内置示例 → read_article(source="demo")；
   今天的推送 → read_article(source="daily")；用户自己贴的 → load_text。
   三个都不许凭记忆复述原文。
   如果 read_article 返回 NOT_FOUND，按它给的处理办法**立刻用 article_sample.txt 重试**，
   不要停下来问用户"要不要换一篇"——实测这一停顿会让整条主路径中断。
3. **英语语境下，任何单词的释义、音标、词性、考纲等级都必须来自 lookup_word 的返回**，
   不许凭记忆写。若当前语种不是英语（本地无该语种词库），lookup_word 会返回
   NOT_SUPPORTED——那就按上面「语种规矩」由你给出，但必须标注「未经词库校验」。
4. 查词要一个一个来，不要臆造一个不存在的批量接口。参数传文章里的原样形式就行，
   工具自己会还原词形（consolidates → consolidate），不用你改写。
   挑生词时先查再挑，看 `level`：**标为「高考」的词对 CET-6 考生不算生词，
   不要挑进词表**；优先挑 CET-4 / CET-6 / IELTS 这一档。这条只对英语成立，
   其他语种按各自的等级档位判断。
5. 遇到 NOT_FOUND，必须如实告诉用户「该词不在本地词库，释义为模型推断」。
6. 产出文件后，只用一两句话说明文件名和内容概要，不要复述文件全文。
   **说位置时必须抄工具回传的 `absolute_path` 完整路径**，不要只写 `outputs/xxx.csv`——
   那是相对路径，用户拿去资源管理器里找不到，就会以为文件没生成。
   再补一句：界面侧边栏「产出文件」和回复下方都有「下载 / 直接打开」按钮。
7. 生成词表时，查词返回 NOT_FOUND 的词也可以写进去，但必须在回复里点明
   哪几个词「未收录、释义为模型推断」——工具会把它们的等级标成「未收录」、
   音标留空，你的说法要和文件内容对得上。
   **未收录的词一个音标都不许给**，写成「供参考」「例如」也不行：
   文件里那格是空的，你一给音标，回复和文件就对不上了。
8. 不要声称某个词「已加入词表 / 已同步进练习页」，除非它确实出现在你本轮
   提交给 make_wordlist_csv 的 entries 里。错词本里的词 ≠ 这次产出的词。
9. 本项目只产出本地文件：CSV、HTML 和 `data/learner_profile.json`，
   **没有接入任何 App、游戏或云端词库服务**。错词只写进本地档案。
   不得说「已同步到 App」「打开 App 即可见」「已自动导入」这类没发生的事。
10. 词表 CSV 共五列：word / phonetic / pos / cn / example。
    **等级与来源不在 CSV 里**——它们在做 Word 时按单词现查词库，显示成〔CET-6〕
    这样的标签和「未收录」小字注。不要说「CSV 有等级列 / 来源列」。
    **音标由工具从词库直接填入，你不要写音标**，也不要说某个未收录的词带音标。
    可以说「可导入 Excel 或 Anki」，但不要说「可一键导入某某 App」「拖进去就生效」。
11. 复习日期只能抄 record_mistakes 返回的 due 字段。**不要自己推算**
    「七天后」「下周」这类时间，也不要自己编一个复习计划。
12. **每一轮只要用户要产出文件，就必须在这一轮真的调用写文件工具**
    （make_wordlist_csv / build_worksheet_html）。不许因为「上一轮生成过同名文件」
    就直接回复「已生成」——实测过两次：模型没调工具就写「两份文件已生成」，
    用户跑去打开时文件根本不存在，或者打开的是上一轮的旧文件。
    回复里出现的文件名，必须是**本轮**工具返回的 `path`；写盘失败就直说失败。
13. 词表类需求一律 make_wordlist_csv：它一次产出 .csv 和 .docx 两个文件。
    回复里**两个路径都要给**，并说清分工：CSV 是数据（Excel / Anki），
    docx 是排好版、能打印的笔记。
    用户说「用 Word 打开还是很乱」时——那是把 CSV 拖进 Word 了，
    **解释清楚并让他打开 .docx**，不要重复生成、也不要建议他自己排版。
    只有当用户要改标题、或指定「把某个已有 CSV 重新排一版」时，才调 build_vocab_doc。
14. 用户问「今天推了什么 / 今天读哪篇 / 我连续几天了」→ 调 read_article(source="daily")。
    标题、来源站点、原文链接、抓取方式、连续天数**只能抄工具返回的字段**，
    不许把「新华网英文版」说成「外刊精选」这类更漂亮的说法，也不许自己算天数。
    如果返回 EMPTY（今天没取到正文），照实说「今天的这篇没取到」并建议用粘贴框，
    **不要拿内置示例冒充今天的推送**——老师一点开链接就露馅。

## 边界

- 不代写作文、读后感、作业；不逐句翻译整篇供人抄写。
- 不编造音标、词频、考纲等级；不确定就说不确定。
- 不提供医疗、法律、投资方面的判断建议。
- 用户给的个人信息只用于调整难度，不做其他用途。

## 当前学习者档案

{profile}
"""


def _profile_block() -> str:
    p = load_profile()
    if not p:
        return "暂无档案记录。首次使用时可以问一下对方的考试目标。"

    mistakes = p.get("mistakes", [])
    if mistakes:
        top = "、".join(f"{m['word']}({m.get('count', 1)}次)" for m in mistakes[:5])
    else:
        top = "暂无"

    due = due_words(limit=8)
    if due:
        due_line = (
            f"今日待复习（{len(due)} 个，按到期先后）："
            + "、".join(f"{e['word']}(已错{e.get('count', 1)}次)" for e in due)
        )
    else:
        due_line = "今日无到期的复习词"

    return (
        f"目标考试：{p.get('target_exam', '未填写')}　当前水平：{p.get('level', '未填写')}\n"
        f"学习目标：{p.get('goal', '未填写')}\n"
        f"错词本（高频在前）：{top}\n"
        f"{due_line}\n"
        f"{_daily_line(p)}\n"
        f"已累计练习：{p.get('sessions', 0)} 次"
    )


def _daily_line(profile: dict) -> str:
    """每日精读的打卡状态。天数由 tools/daily 按日期算，模型只负责照抄。"""
    try:
        from tools import daily

        st = daily.status(profile.get("language", "en"))
    except Exception:
        return "每日精读：状态暂不可用"
    today = "今天已读" if st["done_today"] else "今天还没读"
    return f"每日精读：连续 {st['streak']} 天，累计 {st['total']} 篇（{today}）"


def _language_block(lang: dict, level: str) -> str:
    """把「当前学什么语种」讲清楚——这一块是换语种后模型行为的唯一依据。

    为什么必须进常驻提示词：模型默认会按英语的思路办事（音标、CET 等级、
    挑词只看字母词），换成日语之后如果不说清，它会给出英语音标和 CET-6 等级，
    还自作主张把汉字词拆开讲。语种规矩写在这里，比在每个工具里 if 来 if 去可靠。
    """
    lines = [
        f"## 当前语种：{lang['name']}（{lang['native']}）",
        f"- 等级分档：{lang['level_system']}；这位学生的目标是 **{level}**",
        f"- 注音形态：{lang['sound']}，由{lang['sound_by']}提供",
        "- 本地词库："
        + (
            "有（可核验）。音标、词性、释义、等级一律以 lookup_word 的返回为准。"
            if lang["lexicon"]
            else "无。该语种的释义、注音、等级都只能由你给出，"
            "凡是产出文件或结论，都要明说「未经词库校验」。"
        ),
        "",
        "语种规矩：",
    ]
    for i, note in enumerate(lang["notes"], start=1):
        lines.append(f"{i}. " + note.format(level=level, word_of=lang["word_of"]))
    return "\n".join(lines)


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def select_skill(query: str, history: str = "") -> str | None:
    """按触发词决定是否加载技能全文。没命中就完全不加载。

    history 是最近两轮「用户」说过的话。为什么要把历史算进来：
    第一轮说「帮我精读这篇」，第二轮只说「再来一份」——只看当前这一句
    就命不中触发词，技能掉了，模型开始自由发挥。
    这是实测发现的 bug，不是理论上的顾虑。
    """
    haystack = f"{query}\n{history}".lower()
    if not haystack.strip():
        return None
    if not any(k in haystack for k in SKILL_TRIGGERS):
        return None

    skill_file = SKILL_DIR / "intensive-reading" / "SKILL.md"
    if not skill_file.exists():
        return None
    return _strip_frontmatter(skill_file.read_text(encoding="utf-8")).strip()


def build_system_prompt(query: str = "", history: str = "") -> str:
    profile = load_profile()
    lang = get_lang(profile.get("language", "en"))
    # 等级也按语种取：档案里还留着 CET-6、但学生切到日语时，不能拿 CET-6 去要求他。
    exam = (profile.get("target_exam") or "").strip()
    if not exam or not lang["levels"].__contains__(exam):
        exam = lang["default_level"]
    prompt = SYSTEM_PROMPT.format(
        exam=exam,
        profile=_profile_block(),
        lang_name=lang["name"],
        language_block=_language_block(lang, exam),
    )

    skill = select_skill(query, history)
    if skill:
        prompt += (
            "\n\n---\n\n## 已加载技能：外刊精读（intensive-reading）\n"
            "以下流程仅在本轮任务中生效，请严格遵守。\n\n" + skill
        )
    return prompt
