"""离线自检：不调用模型、不需要 API Key，验证七个工具与模板渲染是否正常。

用法：
    .venv\\Scripts\\python selftest.py

它检查的是「工具层」——也就是现场演示时真正干活的那部分。
模型能不能连通不在这个脚本的范围内（那需要 Key）。
"""

import json
import shutil
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import CURRENT_ARTICLE_PATH, OUTPUT_DIR, safe_output_path  # noqa: E402
from tools import ALL_TOOLS, TOOLS_BY_NAME  # noqa: E402
from tools.memory import PROFILE_PATH, due_words, load_profile  # noqa: E402
from tools.reader import save_user_article  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str):
    def deco(fn):
        try:
            detail = fn() or ""
            results.append((PASS, name, str(detail)))
        except Exception:
            results.append((FAIL, name, traceback.format_exc(limit=2)))
        return fn

    return deco


@check("工具数量与注册")
def _tools():
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == 7, f"应有 7 个工具，实际 {names}"
    for need in ("load_text", "read_article", "lookup_word", "make_wordlist_csv",
                 "build_worksheet_html", "build_vocab_doc", "record_mistakes"):
        assert need in names, f"缺少工具 {need}"
    return " / ".join(names)


@check("read_article 读取示例文章")
def _read():
    out = TOOLS_BY_NAME["read_article"].invoke({"filename": "article_sample.txt"})
    assert out.startswith("[demo/article_sample.txt]"), out[:60]
    assert "sustainability" in out.lower(), "没读到正文内容"
    return f"{len(out)} 字符"


@check("read_article 越权读取被拒绝")
def _read_guard():
    denied = 0
    for evil in ("../.env", "../../config.py", "sub/../.env"):
        out = TOOLS_BY_NAME["read_article"].invoke({"filename": evil})
        if out.startswith("ERROR"):
            denied += 1
    assert denied == 3, f"3 个越权路径中只拦下 {denied} 个"
    miss = TOOLS_BY_NAME["read_article"].invoke({"filename": "nope.txt"})
    assert miss.startswith("NOT_FOUND") and "article_sample.txt" in miss
    # 只报文件名不够：模型会猜错内容然后停下来反问用户，主路径当场中断。
    assert "首行：" in miss and "立刻用 article_sample.txt 重新调用" in miss, miss[:200]
    return "越权拒绝；缺文件时给首行 + 要求自行重试"


def _slot_backup():
    if CURRENT_ARTICLE_PATH.exists():
        return CURRENT_ARTICLE_PATH.read_text(encoding="utf-8")
    return None


def _slot_restore(backup):
    if backup is None:
        if CURRENT_ARTICLE_PATH.exists():
            CURRENT_ARTICLE_PATH.unlink()
    else:
        CURRENT_ARTICLE_PATH.write_text(backup, encoding="utf-8")


@check("load_text 读界面粘贴的文章")
def _load_text():
    backup = _slot_backup()
    try:
        save_user_article(
            "Carbon pricing is spreading fast.\n\n\n\n"
            "Firms with long supply chains adapt first, or they pay more."
        )
        out = TOOLS_BY_NAME["load_text"].invoke({})
        assert "ARTICLE START" in out and "Carbon pricing" in out, out[:80]
        assert "\n\n\n" not in out, "多余空行没有被压缩"
        assert "PARAGRAPHS: 2" in out, out[:140]

        arg = "Direct text pasted in the chat window. " * 2
        out2 = TOOLS_BY_NAME["load_text"].invoke({"article": arg})
        assert "Direct text pasted" in out2, "article 参数没生效"
        assert "Carbon pricing" not in out2, "传了参数却还在读槽位"
        return f"{len(out)} 字符，参数优先于槽位"
    finally:
        _slot_restore(backup)


@check("load_text 空槽不编内容、无路径参数")
def _load_text_guard():
    backup = _slot_backup()
    try:
        save_user_article("")
        empty = TOOLS_BY_NAME["load_text"].invoke({})
        assert empty.startswith("EMPTY"), empty[:40]
        short = TOOLS_BY_NAME["load_text"].invoke({"article": "Too short to read."})
        assert short.startswith("ERROR"), short[:40]
        params = list(TOOLS_BY_NAME["load_text"].args.keys())
        assert params == ["article", "source_name"], f"不该有路径参数：{params}"
        return "空槽 EMPTY、过短 ERROR、参数表里没有 filename/path"
    finally:
        _slot_restore(backup)


@check("lookup_word 命中")
def _hit():
    raw = TOOLS_BY_NAME["lookup_word"].invoke({"word": "Mitigate"})
    data = json.loads(raw)
    assert data["word"] == "mitigate"
    assert data["phonetic"].startswith("/")
    assert data["level"] == "CET-6"
    return f"{data['word']} {data['phonetic']} {data['level']}"


@check("lookup_word 未命中时如实返回")
def _miss():
    raw = TOOLS_BY_NAME["lookup_word"].invoke({"word": "zzzznotaword"})
    assert raw.startswith("NOT_FOUND"), raw[:60]
    return "返回 NOT_FOUND，未编造释义"


@check("lookup_word 兼容英美拼写变体")
def _variant():
    data = json.loads(TOOLS_BY_NAME["lookup_word"].invoke({"word": "summarise"}))
    assert data["phonetic"] and data["cn"], data
    assert data.get("matched_spelling") in (None, "summarize"), data
    beh = json.loads(TOOLS_BY_NAME["lookup_word"].invoke({"word": "behaviour"}))
    assert beh["phonetic"] and beh["cn"], beh
    return f"summarise → {data.get('matched_spelling') or '精确命中'}；behaviour 命中"


@check("lookup_word 还原词形 + 常用词命中")
def _lemma():
    for surface, base in (
        ("consolidates", "consolidate"),
        ("impairs", "impair"),
        ("decayed", "decay"),
    ):
        data = json.loads(TOOLS_BY_NAME["lookup_word"].invoke({"word": surface}))
        assert data.get("matched_spelling") == base, f"{surface} → {data}"
    att = json.loads(TOOLS_BY_NAME["lookup_word"].invoke({"word": "attention"}))
    assert att["level"] == "高考", att
    return "consolidates→consolidate；attention 命中高考档（原词库缺这类常用词）"


@check("make_wordlist_csv 生成且编码正确")
def _csv():
    entries = "mitigate|v.|减轻；缓和|CET-6|Tree planting helps mitigate urban heat.\nincentive|n.|激励；诱因|CET-6|Subsidies provide an incentive."
    raw = TOOLS_BY_NAME["make_wordlist_csv"].invoke({"entries": entries, "filename": "selftest_wordlist.csv", "language": "en"})
    data = json.loads(raw)
    path = OUTPUT_DIR / "selftest_wordlist.csv"
    assert path.exists(), "文件没生成"
    head = path.read_bytes()[:3]
    assert head == b"\xef\xbb\xbf", "缺少 BOM，Excel 打开会乱码"
    rows = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(rows) == 3, f"应有表头+2行，实际 {len(rows)}"
    header = rows[0].split(",")
    assert header == ["word", "phonetic", "pos", "cn", "example"], f"列不对：{header}"
    assert "level" not in header and "source" not in header, (
        f"CSV 不该再有等级/来源列：{header}"
    )
    assert data["columns"][1] == "phonetic", data["columns"]
    known_ipa = json.loads(
        TOOLS_BY_NAME["lookup_word"].invoke({"word": "mitigate"})
    )["phonetic"]
    assert known_ipa in rows[1], f"音标不是词库里那条：{rows[1]}"
    assert "减轻" in rows[1], f"释义没被词库覆盖：{rows[1]}"
    # 路径必须是可打开的绝对路径：相对路径用户拿去资源管理器里找不到。
    assert data["absolute_path"] == str(path), data["absolute_path"]
    assert Path(data["absolute_path"]).is_absolute(), "absolute_path 不是绝对路径"
    # 同一个工具要顺手排一份 Word：用户真正要看的是版式，不是逗号原文。
    docx = Path(data["docx_absolute_path"] or "")
    assert docx.is_file(), f"没有同时生成 .docx：{data.get('docx_note')}"
    import zipfile

    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "mitigate" in xml and "用法" in xml, "docx 里没有词条或用法行"
    # 等级标签必须落在 Word 里（CSV 已经没有这一列了）
    assert "〔CET" in xml, "docx 里没有等级标签"
    return f"{data['count']} 条，五列带 BOM，音标来自词库，CSV + docx 双产出"


@check("make_wordlist_csv 拦截编造的考纲等级")
def _csv_guard():
    entries = "structural|adj.|结构性的|CET-6|x\nmitigate|v.|减轻|CET-4|y"
    raw = TOOLS_BY_NAME["make_wordlist_csv"].invoke(
        {"entries": entries, "filename": "selftest_guard.csv", "language": "en"}
    )
    data = json.loads(raw)
    assert "structural" in data["not_in_lexicon"], "未收录的词没被标出"
    assert "mitigate" in data["level_corrected"], "错误等级没被纠正为词库值"
    text = (OUTPUT_DIR / "selftest_guard.csv").read_text(encoding="utf-8-sig")
    # 等级与来源从 CSV 里退出了，改由 Word 的标签与注承载。
    assert "未收录" not in text and "本地词库" not in text, "CSV 里不该有等级/来源"
    guard_rows = text.strip().splitlines()
    assert guard_rows[1].startswith("structural,,"), (
        f"未收录词的音标列应为空：{guard_rows[1]}"
    )
    import zipfile

    with zipfile.ZipFile(OUTPUT_DIR / "selftest_guard.docx") as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "未收录" in xml, "Word 里没标「未收录」"
    assert "模型推断" in xml, "Word 里没说明来源为模型推断"
    return "编造等级被纠正；CSV 五列不含等级，Word 里标「未收录」"
    return "编造等级已纠正，未收录已标注来源、音标留空"


@check("make_wordlist_csv 容忍多写的 source 字段")
def _csv_source_field():
    # 实测：模型会把 source 也塞进 entries，变成六列，把例句挤到第六位。
    entries = (
        "mitigate|v.|减轻；缓和|CET-6|data/lexicon.json|Tree planting helps mitigate urban heat.\n"
        "incentive|n.|激励；诱因|CET-6|本地词库|Subsidies provide an incentive."
    )
    raw = TOOLS_BY_NAME["make_wordlist_csv"].invoke(
        {"entries": entries, "filename": "selftest_source.csv", "language": "en"}
    )
    data = json.loads(raw)
    assert data["count"] == 2, data
    for row in data["head"][:2]:
        assert "lexicon.json" not in row["example"], f"例句被来源字段挤掉了：{row}"
        assert "Tree" in row["example"] or "Subsidies" in row["example"], row
    return "六列输入能正确对齐，来源字段被剔除"


@check("build_worksheet_html 生成且完成挖空")
def _html():
    article = (
        "Emissions from campus buildings keep rising.\n"
        "Simple measures can mitigate the impact, but incentives matter more."
    )
    raw = TOOLS_BY_NAME["build_worksheet_html"].invoke(
        {
            "title": "自检精读页",
            "article": article,
            "words": "emission,mitigate,incentive",
            "filename": "selftest_worksheet.html",
        }
    )
    data = json.loads(raw)
    path = OUTPUT_DIR / "selftest_worksheet.html"
    assert path.exists(), "文件没生成"
    html = path.read_text(encoding="utf-8")
    assert "自检精读页" in html, "标题没替换"
    assert "%%" not in html, "还有未替换的占位符"
    assert html.count("______") >= 3, "挖空数量不足"
    assert "Emissions" not in html, "emissions 的复数变体没被挖空"
    return f"{data['words']} 个词，挖空 {data['blanks_filled_in_article']} 处"


@check("build_vocab_doc 把 CSV 排成可读的 Word")
def _docx():
    csv_name = "selftest_wordlist.csv"
    raw = TOOLS_BY_NAME["build_vocab_doc"].invoke(
        {"csv_filename": csv_name, "title": "自检词表", "subtitle": "selftest", "language": "en"}
    )
    path = OUTPUT_DIR / "selftest_wordlist.docx"
    assert path.exists(), f"docx 没生成：{raw[:120]}"
    assert str(path) in raw, "返回里没给绝对路径"
    # 结构断言：不靠肉眼，直接从 XML 里数段落和文字
    import zipfile

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    for token in ("mitigate", "incentive", "用法", "01", "02"):
        assert token in xml, f"文档里缺 {token}"
    assert xml.count("用法") >= 2, "用法行没逐词出现（说明还是挤在一起）"
    # 音标必须来自词库，而不是模型
    known_ipa = json.loads(
        TOOLS_BY_NAME["lookup_word"].invoke({"word": "mitigate"})
    )["phonetic"]
    assert known_ipa in xml, f"音标没写进文档：{known_ipa}"
    return f"2 个词，逐词分块，含音标与用法行"


@check("record_mistakes 写回档案")
def _memory():
    backup = PROFILE_PATH.read_text(encoding="utf-8")
    try:
        raw = TOOLS_BY_NAME["record_mistakes"].invoke({"words": "mitigate,incentive", "note": "自检"})
        data = json.loads(raw)
        assert "mitigate" in data["bumped"], "已存在的词应计入 bumped"
        assert data["total_in_notebook"] >= 3
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        assert any(m["word"] == "mitigate" for m in profile["mistakes"])
        return f"错词本共 {data['total_in_notebook']} 条"
    finally:
        PROFILE_PATH.write_text(backup, encoding="utf-8")


@check("record_mistakes 排下次复习日期")
def _schedule():
    backup = PROFILE_PATH.read_text(encoding="utf-8")
    try:
        first = json.loads(
            TOOLS_BY_NAME["record_mistakes"].invoke(
                {"words": "mitigate", "note": "自检"}
            )
        )
        s1 = first["schedule"]["mitigate"]
        assert s1["reps"] == 0 and s1["interval_days"] == 1, s1
        assert s1["due"] == (date.today() + timedelta(days=1)).isoformat(), s1

        second = json.loads(
            TOOLS_BY_NAME["record_mistakes"].invoke({"known": "mitigate"})
        )
        s2 = second["schedule"]["mitigate"]
        assert s2["reps"] == 1 and s2["interval_days"] == 1, s2

        third = json.loads(
            TOOLS_BY_NAME["record_mistakes"].invoke({"known": "mitigate"})
        )
        s3 = third["schedule"]["mitigate"]
        assert s3["reps"] == 2 and s3["interval_days"] == 3, s3
        assert s3["due"] == (date.today() + timedelta(days=3)).isoformat(), s3

        fourth = json.loads(
            TOOLS_BY_NAME["record_mistakes"].invoke({"words": "mitigate"})
        )
        s4 = fourth["schedule"]["mitigate"]
        assert s4["interval_days"] == 1 and s4["reps"] == 0, s4
        assert s4["ease"] < s3["ease"], f"答错后难度系数应下降：{s3['ease']}→{s4['ease']}"
        return f"错→1天，对→1天→3天，再错→1天（ease {s3['ease']}→{s4['ease']}）"
    finally:
        PROFILE_PATH.write_text(backup, encoding="utf-8")


@check("due_words 只取到期词")
def _due():
    backup = PROFILE_PATH.read_text(encoding="utf-8")
    try:
        TOOLS_BY_NAME["record_mistakes"].invoke({"words": "mitigate"})
        words = [e["word"] for e in due_words(limit=99)]
        assert "mitigate" not in words, "明天才到期的词不该出现在今日待复习里"

        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        for m in profile["mistakes"]:
            if m["word"] == "mitigate":
                m["due"] = (date.today() - timedelta(days=1)).isoformat()
        PROFILE_PATH.write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
        words2 = [e["word"] for e in due_words(limit=99)]
        assert "mitigate" in words2, "已过期的词应该被选进今日待复习"
        return "明天到期不入选，已过期入选"
    finally:
        PROFILE_PATH.write_text(backup, encoding="utf-8")


@check("权限隔离：越界写入被拒绝")
def _guard():
    blocked = 0
    for evil in ("../escaped.txt", "..\\escaped.txt", "C:\\Windows\\evil.txt"):
        try:
            safe_output_path(evil, ".txt")
        except ValueError:
            blocked += 1
    assert blocked == 3, f"3 个越界路径中只拦下 {blocked} 个"
    ok = safe_output_path("normal.csv", ".csv")
    assert ok.parent == OUTPUT_DIR.resolve()
    return "3 个越界路径全部拦截，正常路径放行"


@check("语种注册表")
def _languages():
    from agent.languages import LANGS, get, level_belongs

    assert len(LANGS) == 5, f"应有 5 个语种，实际 {list(LANGS)}"
    for code, lang in LANGS.items():
        assert lang["levels"], f"{code} 没定义等级体系"
        assert lang["default_level"] in lang["levels"], f"{code} 默认等级不在档位里"
        assert lang["site"].startswith("http"), f"{code} 没有新闻源"
    # 等级体系不能串台：CET-6 只属于英语，JLPT N3 只属于日语
    assert level_belongs("en", "CET-6") and not level_belongs("ja", "CET-6")
    assert level_belongs("ja", "JLPT N3") and not level_belongs("en", "JLPT N3")
    return " / ".join(f"{c}:{v['level_system']}" for c, v in LANGS.items())


@check("每日推送：五语种都有文章且同日同篇")
def _daily_pick():
    from tools import daily

    day = date(2026, 3, 1)
    picked = {}
    for code in ("en", "ja", "fr", "de", "es"):
        item = daily.pick(code, day=day, allow_network=False)
        assert len(item.get("text", "")) >= 300, f"{code} 离线快照为空（跑 scripts/fetch_pool.py）"
        assert item["origin"] == "pool", f"{code} 应回落到快照池，实际 {item['origin']}"
        again = daily.pick(code, day=day, allow_network=False)
        assert again["title"] == item["title"], f"{code} 同一天取到了不同的文章"
        picked[code] = item["title"][:18]
    return "；".join(f"{k}→{v}" for k, v in picked.items())


@check("每日推送：连续天数按日期算")
def _streak():
    from tools import daily

    today = date(2026, 3, 10)
    d = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731
    assert daily.compute_streak([d(0), d(1), d(2)], today) == 3
    # 今天还没读，但昨天读了：保留到昨天的连续记录，不能归零
    assert daily.compute_streak([d(1), d(2)], today) == 2
    # 断了一天就从头开始
    assert daily.compute_streak([d(0), d(1), d(3)], today) == 2
    assert daily.compute_streak([], today) == 0
    # 同一天重复调用不加天
    # 这一项会真的写档案（打卡只认日期，没法干跑），所以跑完要还原，
    # 否则自检本身会给演示账号刷一天连续记录。
    snapshot = dict(load_profile())
    try:
        first = daily.record_done("en")
        second = daily.record_done("en")
        assert first["streak"] == second["streak"], "同一天打卡被算了两次"
        assert second["total"] == len(set(snapshot.get("daily_dates", []) or [])
                                     | {date.today().isoformat()})
    finally:
        from tools.memory import save_profile

        save_profile(snapshot)
    return f"连续 {second['streak']} 天，累计 {second['total']} 篇"


@check("非英语词表：注音来自第 6 字段并标为模型推断")
def _ja_wordlist():
    tool = TOOLS_BY_NAME["make_wordlist_csv"]
    data = json.loads(
        tool.invoke(
            {
                "entries": "課題|名|课题；待解决的问题|JLPT N3|少子化は大きな課題だ。|課題(かだい, kadai)",
                "filename": "selftest_ja.csv",
                "language": "ja",
            }
        )
    )
    assert data["language"] == "ja" and data["lexicon_covered"] is False
    row = data["head"][0]
    assert "かだい" in row["phonetic"], f"注音没取到第 6 字段：{row['phonetic']}"
    assert row["source"] == "模型推断", row["source"]
    text = (OUTPUT_DIR / "selftest_ja.csv").read_text(encoding="utf-8-sig")
    header = text.splitlines()[0].split(",")
    assert header == ["word", "phonetic", "pos", "cn", "example"], header
    assert "未收录" not in text, "非英语词表不该出现「未收录」（那是英语词库的说法）"
    xml = __import__("zipfile").ZipFile(OUTPUT_DIR / "selftest_ja.docx").read(
        "word/document.xml"
    ).decode()
    assert "課題" in xml and "暂无本地词库" in xml, "Word 里没写明该语种无词库"
    return "注音入列、标注模型推断、Word 有来源小字注"


def main() -> int:
    width = max(len(n) for _, n, _ in results) + 2
    for status, name, detail in results:
        mark = "✓" if status == PASS else "✗"
        print(f"[{mark}] {name.ljust(width)} {detail.splitlines()[0] if detail else ''}")
        if status == FAIL:
            for line in detail.splitlines()[1:]:
                print("     " + line)

    failed = sum(1 for s, _, _ in results if s == FAIL)
    print("-" * 56)
    print(f"共 {len(results)} 项，通过 {len(results) - failed} 项，失败 {failed} 项")

    for leftover in (
        "selftest_wordlist.csv",
        "selftest_wordlist.docx",
        "selftest_worksheet.html",
        "selftest_guard.csv",
        "selftest_guard.docx",
        "selftest_guard.docx",
        "selftest_source.csv",
        "selftest_source.docx",
        "selftest_source.docx",
        "selftest_ja.csv",
        "selftest_ja.docx",
        "selftest_en.csv",
        "selftest_en.docx",
    ):
        p = OUTPUT_DIR / leftover
        if p.exists():
            p.unlink()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
