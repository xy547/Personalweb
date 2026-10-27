"""工具二：把生词写成 CSV 词表。

两个关键工程细节，都值得在汇报时单独讲一句：

1. 输出用 utf-8-sig 编码。不带 BOM 的 UTF-8 在中文 Windows 上用 Excel
   双击打开会显示乱码，这是学生项目里最常见、也最容易被忽略的坑。

2. 写盘前做一次「事实校验」。实测发现：模型在查词失败（NOT_FOUND）之后，
   仍然会凭印象给那个词填一个考纲等级，于是词表里出现
   「未收录的词 + 编造的 CET-6」。光在提示词里写"不许编"是拦不住的，
   所以这里拿 lexicon.json 再核一遍：查得到的用词库等级覆盖，
   查不到的强制标为「未收录」、来源记「模型推断」。
   校验放在代码里，不依赖模型自觉——这是工具存在的意义。

3. 等级与来源**只用于呈现，不进 CSV**。CSV 留下五列学习事实
   （word / phonetic / pos / cn / example），干净到能直接导进 Excel 或 Anki；
   等级变成 Word 笔记里那个〔CET-6〕标签、未收录变成一行小字注。
   数据表里不该混进审计信息——这是用户看过成品之后提的要求。
"""

import csv
import json
import re
from pathlib import Path

from langchain_core.tools import tool

from config import safe_output_path
from tools.lexicon import lookup

_SEP = re.compile(r"\s*[|｜\t]\s*")
UNVERIFIED = "未收录"

# 模型有时会把「来源」也塞进 entries，于是变成六列：
#   mitigate|v.|减轻；缓和|CET-6|data/lexicon.json|Tree planting helps...
# 位置全错，例句被挤到第六位然后静默丢弃，CSV 里 example 列就变成了文件路径。
# 实测出现过（在我给工具返回加上 columns 之后），所以这里显式识别并剔除来源字段。
_SOURCE_HINT = re.compile(r"(\.json$|\.db$|\.csv$|^本地词库$|^模型推断$|^未收录$)", re.I)


def _drop_source_field(parts: list[str], keep: int = 5) -> list[str]:
    """剔除被模型夹带进来的「来源」字段，并按语种保留合法字段数。

    keep=5（英语）：单词|词性|释义|等级|例句
    keep=6（其他语种）：单词|词性|释义|等级|例句|注音
    注音只在非英语语种才收——英语的音标必须由词库给，模型碰不到。
    """
    if len(parts) > keep:
        for i, p in enumerate(parts):
            if _SOURCE_HINT.search(p.strip()):
                parts = parts[:i] + parts[i + 1:]
                break
    return parts[:keep]


def _parse_entries(entries: str, language: str = "en") -> list[dict]:
    """把逐行文本解析成词条。

    第 6 个字段（注音）只在非英语语种生效：日语要给假名＋罗马音，
    法语/德语/西语要给各自的 IPA。英语那一路刻意不接第 6 个字段——
    模型一旦能往音标列写东西，「不编音标」这条纪律就形同虚设。
    """
    allow_sound = language != "en"
    rows: list[dict] = []
    for raw in (entries or "").splitlines():
        line = raw.strip().strip("-*").strip()
        if not line:
            continue
        parts = [p.strip() for p in _SEP.split(line) if p.strip()]
        parts = _drop_source_field(parts, keep=6 if allow_sound else 5)
        if len(parts) < 2:
            continue
        rows.append(
            {
                "word": parts[0],
                # 英语：音标不接受模型输入，占位由 _verify() 从词库填。
                # 其他语种：本地没有词库，只能收模型给的注音，并在文件里标来源。
                "phonetic": (parts[5] if allow_sound and len(parts) > 5 else ""),
                "pos": parts[1] if len(parts) > 1 else "",
                "cn": parts[2] if len(parts) > 2 else "",
                "level": parts[3] if len(parts) > 3 else "",
                "example": parts[4] if len(parts) > 4 else "",
            }
        )
    return rows


def _verify(
    rows: list[dict], language: str = "en"
) -> tuple[list[dict], list[str], list[str]]:
    """拿词库复核每个词条，返回 (行, 被纠正的词, 未收录的词)。

    覆盖的是「可核查的事实字段」：音标、词性、中文释义、考纲等级、来源。
    例句保留模型给的（要贴合原文语境），只有在它没给时才用词库例句兜底。

    为什么连中文释义也要覆盖：模型给的释义读起来都很通顺，但它会把
    incentive 说成「激励」而漏掉「诱因」那层，也容易把 mitigate 和
    mediate 混在一起。词库的值可复查，模型的不可复查。
    模型在这一步的职责被压到只剩两件：挑哪些词、给一句贴合语境的例句。
    """
    corrected: list[str] = []
    unverified: list[str] = []

    if language != "en":
        # 非英语语种没有本地词库可核，这一步就没有「覆盖」的资格。
        # 与其假装校验（把词库查不到当成「未收录」），不如把来源如实标成模型推断，
        # 让 Word 里每个词都挂一行小字注。用户看到的和实际发生的必须一致。
        for row in rows:
            row["source"] = "模型推断"
            # 模型爱在等级后面自己补「（推断）」，Word 的标签里会变成
            # 〔JLPT N3（推断）〕——来源已经由小字注和标签颜色交代过了，
            # 这里去掉重复的后缀，标签只留档位本身。
            lv = re.sub(r"[（(]\s*(推断|未校验|模型推断)\s*[)）]", "", row.get("level") or "").strip()
            row["level"] = lv or UNVERIFIED
        return rows, corrected, [r["word"] for r in rows]

    for row in rows:
        known = lookup(row["word"])
        if known is None:
            # 音标留空，而不是让模型补一个——空着说明"词库没有"，
            # 编一个则会让读者以为这是查证过的。
            row["phonetic"] = ""
            row["level"] = UNVERIFIED
            row["source"] = "模型推断"
            unverified.append(row["word"])
            continue
        if row["level"] and row["level"] != known["level"]:
            corrected.append(row["word"])
        row["phonetic"] = known["phonetic"]
        # 词库里个别条目没拆出词性（例如 operational 的释义写在一条里），
        # 这时不要把模型给的词性也清空——留空比写错更难用，而且 Word 那边
        # 已经标了「本地词库」，用户看到空白只会以为文件坏了。
        if known["pos"]:
            row["pos"] = known["pos"]
        if known["cn"]:
            row["cn"] = known["cn"]
        row["level"] = known["level"]
        row["source"] = "本地词库"
        if not row["example"]:
            row["example"] = known["example"]
    return rows, corrected, unverified


def _render_sidecar(rows, csv_path, language: str = "en"):
    """按内存里的词条排一份同名 .docx，返回 (docx 路径 或 None, 说明)。

    为什么要在写 CSV 的时候顺手排：
    用户真正要「看 / 背」的是排好版的纸，而**用 Word 直接打开 CSV 只会看到
    带逗号的原文**（这就是「打开还是乱笔记」的根因，不是文件坏了）。
    让两个文件一起落地，模型就少一次「要不要再排个版」的判断，
    用户也不用再追一句「能不能排得好看点」。

    注意这里用的是**内存里的 rows**，不是回读 CSV：
    CSV 已经不含 level / source 两列了，回读会丢掉等级标签。

    排版失败绝不能让 CSV 一起失败——版式是附加价值，数据才是本体。
    所以这里吞掉异常，只在返回值里说清楚。
    """
    try:
        from agent.languages import get as get_lang
        from tools.vocabdoc import render_docx

        lang = get_lang(language)
        target = Path(csv_path).with_suffix(".docx")
        render_docx(
            rows,
            f"{lang['name']}词汇精读笔记",
            f"{lang['level_system']} · 每日精读",
            target,
            language=language,
        )
        return target, ""
    except Exception as exc:
        return None, f"Word 版式未生成（{type(exc).__name__}: {exc}）"


@tool
def make_wordlist_csv(
    entries: str, filename: str = "wordlist.csv", language: str = ""
) -> str:
    """把整理好的生词写成 CSV 词表，供 Excel / Anki 等通用工具导入。

    参数 entries 是逐行文本，每行一个词，用竖线分隔五个字段，顺序为：
    单词|词性|中文释义|考纲等级|例句
    例如：
    mitigate|v.|减轻；缓和|CET-6|Tree planting helps mitigate urban heat.
    incentive|n.|激励；诱因|CET-6|Subsidies provide an incentive to switch.

    例句可以省略（省略时用词库例句兜底）。不要写表头行，不要加 Markdown 代码块标记。
    词性、释义、等级乱填没关系，工具会拿词库复核并覆盖成准确值；
    词库里没有的词会被标为「未收录」。

    **不要写音标**：音标由工具从本地词库直接填进文件，模型不参与这个字段。
    这样就不存在「模型编音标」这件事——它碰不到那一列。

    **非英语语种另有一套规矩**（日语/法语/德语/西语）：本地没有这些语种的词库，
    所以第 6 个字段要填注音——日语写「假名(罗马音)」，例如 影響(えいきょう, eikyou)；
    法德西写各自语言的 IPA。字段顺序是：
    单词|词性|中文释义|等级|例句|注音
    英语调用时**不要**加第 6 个字段，工具会忽略它。

    language 参数留空 = 用学习档案里的当前语种；一般不用显式传。

    **等级与来源不写进 CSV**：CSV 只有 word / phonetic / pos / cn / example
    五列，等级在做 Word 时按单词现查词库、显示成〔CET-6〕这样的标签。

    本工具会**同时产出两个文件**：同名 .csv（数据，给 Excel / Anki）
    和同名 .docx（逐词分块排好版，给人看和打印）。
    所以不需要为了「好看」再调一次 build_vocab_doc；
    只有当用户要改标题、或想重新排版时才调它。

    filename 只能是文件名，文件会被强制写入 outputs/ 目录。
    """
    from agent.languages import get as get_lang

    code = (language or "").strip().lower()
    if not code:
        from tools.memory import load_profile

        code = load_profile().get("language", "en")
    lang = get_lang(code)
    code = lang["code"]

    rows = _parse_entries(entries, language=code)
    if not rows:
        return (
            "ERROR: 没有解析出任何词条。请按「单词|词性|中文释义|等级|例句」的格式，"
            "每行一个词重新提供。"
        )

    rows, corrected, unverified = _verify(rows, language=code)

    target = safe_output_path(filename, ".csv")
    # CSV 只存「学习要用的五列事实」。
    # level / source 是校验过程的中间产物，不进数据表：
    # 用户要的是能背、能导入 Excel/Anki 的干净词表，不是审计日志。
    # 这两项仍然算、仍然核，只是呈现在 Word 的等级标签和「未收录」小字注里
    #（排版时按单词现查词库得到，所以删掉列也不会丢信息）。
    with open(target, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "word",
                "phonetic",
                "pos",
                "cn",
                "example",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    # CSV 与排好版的 Word 一起落地：CSV 给 Excel/Anki，docx 给人看。
    docx_path, docx_note = _render_sidecar(rows, target, code)

    payload = {
        "status": "ok",
        "path": f"outputs/{target.name}",
        # 实测用户拿到「outputs/xxx.csv」在资源管理器里找不到——那是相对路径，
        # 没有盘符。完整路径必须由工具回传，模型抄不错，用户也能直接粘贴。
        "absolute_path": str(target),
        # 同一份数据已经排好版的 Word：用户要的是「能看能打印的笔记」，
        # 不是逗号分隔的原文。两个路径都给，让人自己选。
        "docx_absolute_path": str(docx_path) if docx_path else None,
        "docx_note": docx_note
        or "已自动生成同名 .docx（逐词分块：序号/单词/音标/释义/用法），"
        "CSV 用 Word 打开只会看到逗号原文，看版式请开 .docx。",
        "open_hint": "告诉用户文件位置时必须给出 absolute_path 的完整路径"
        "（可写成「文件在 D:\\readcoach\\outputs\\xxx.csv」）；"
        "只说「outputs/xxx.csv」用户打不开、也找不到。"
        "如果 docx_absolute_path 不是 null，就要**同时**给出这个 .docx 路径，"
        "并说明两者的分工：CSV 是给 Excel / Anki 的数据，"
        ".docx 是排好版、能直接打印的笔记。"
        "用户说「用 Word 打开很乱」时，先解释这是 CSV 的固有形态、开关错的文件，"
        "不要再重复生成一遍。"
        "另外要说明：界面上有两处入口——侧边栏「产出文件」的下载按钮，"
        "以及回复正文下方自动出现的「下载 / 直接打开」按钮。",
        "count": len(rows),
        "columns": [
            "word",
            "phonetic",
            "pos",
            "cn",
            "example",
        ],
        "columns_note": "CSV 只存这五列。等级与来源**不进 CSV**——"
        "它们在排版成 .docx 时按单词现查词库、变成等级标签和「未收录」小字注。"
        "所以不要说「CSV 里有等级列 / 来源列」。",
        "encoding": "utf-8-sig（Excel 直接双击不乱码）",
        # 实测模型说「以竖线 | 为分隔符导入 Anki」——entries 用竖线是有意设计，
        # 但落盘的 CSV 是逗号分隔。分隔符也一并回传，避免被自己前面的写法带偏。
        "delimiter": "逗号 , （entries 参数里的竖线只是输入格式，不写进文件）",
        "level_corrected": corrected,
        "not_in_lexicon": unverified,
        "level_display": "等级与来源只出现在 Word 的标签里（如〔CET-6〕/〔未收录〕），"
        "CSV 没有这两列；描述产物时不要说 CSV 含等级列。",
        "head": rows[:5],
        "phonetic_source": "音标由工具从 data/lexicon.json 填入，不是模型写的；"
        "未收录的词音标列为空字符串（表示词库没有，不是没有音标）。",
        # 列名直接回传，模型就没法凭空多编一列或缺一列。
        "reply_rule": "描述 CSV 内容只能引用 columns 里的五列（word / phonetic / pos / cn / example）；"
        "等级与来源不在 CSV 里，只在 Word 的标签上，别说成「CSV 有 level 列」。"
        "音标是工具从词库填的，可以说「含音标列」，"
        "但**未收录的词一个音标都不许给**——哪怕写成「供参考」「例如」「大概」也不行。"
        "实测模型会给 footprint、habitation 这类未收录词补 /ˈfʊtprɪnt/ 这样的音标，"
        "而文件里那一格是空的，用户一对照就发现回复和文件不一致。"
        "描述分隔符只能依据 delimiter 字段（逗号），不要说成竖线或制表符。"
        "CSV 是通用格式，可说「可导入 Excel 或 Anki」，"
        "但不得承诺「一键导入某个 App」「拖进去就生效」。"
        "另外：提交 entries 时不要带 source 字段、不要写音标，这两项由工具负责。"
        "产物有两个文件：.csv 是数据（Excel / Anki），.docx 是排好版的笔记（打印 / 阅读）。"
        "用户问「怎么在 Word 里看」→ 让他打开 .docx，"
        "不要建议「把 CSV 用 Word 打开再排版」，那是上一版的返工来源。",
    }
    if unverified:
        payload["提醒"] = (
            f"以下词不在本地词库，Word 里被标成「{UNVERIFIED}」并附来源说明："
            + "、".join(unverified)
            + "。请在回复里如实说明这一点，不要让用户以为是查证过的。"
        )

    payload["language"] = code
    payload["language_name"] = lang["name"]
    payload["level_system"] = lang["level_system"]
    payload["lexicon_covered"] = lang["lexicon"]

    if not lang["lexicon"]:
        # 非英语：没有词库可核，所有字段都是模型给的。这里必须把话说死，
        # 否则模型会在回复里说「音标来自词库」——文件里根本没有词库参与。
        payload.pop("level_corrected", None)
        payload["not_in_lexicon"] = []
        payload["phonetic_source"] = (
            f"{lang['name']}没有本地词库，注音（{lang['sound']}）由你提供，"
            "文件里已标注「未经词库校验」。"
        )
        payload["level_display"] = (
            f"等级沿用 {lang['level_system']} 分档，只有模型判断，没有词库依据；"
            "Word 里每个词下面都有一行来源小字注。"
        )
        payload["reply_rule"] = (
            f"这是{lang['name']}词表：本地没有{lang['name']}词库，"
            "所以释义、注音、等级**都不是查证结果**。回复里必须用一句话说清这一点"
            "（例如「这几个词的释义与注音由模型给出，建议对照教材复核」），"
            "不要写成「音标来自本地词库」，也不要说「已核对」。"
            f"词表 word 列按{lang['name']}习惯书写（见系统提示词里的语种规矩）。"
            "CSV 仍是五列；注音在 phonetic 列，标注来源的事情由 Word 的小字注完成。"
        )
        payload["提醒"] = (
            f"该语种（{lang['name']}）暂无本地词库，{len(rows)} 个词的释义、注音、"
            f"{lang['level_system']} 等级全部为模型推断，Word 里已逐条标注。"
            "请在回复开头如实说明，不要让用户以为经过词库校验。"
        )
    return json.dumps(payload, ensure_ascii=False)
