"""七个工具的统一出口。Agent 只依赖这里，不直接依赖具体实现文件。"""

from tools.dictionary import lookup_word
from tools.memory import record_mistakes
from tools.reader import load_text, read_article
from tools.vocabdoc import build_vocab_doc
from tools.wordlist import make_wordlist_csv
from tools.worksheet import build_worksheet_html

ALL_TOOLS = [
    load_text,
    read_article,
    lookup_word,
    make_wordlist_csv,
    build_worksheet_html,
    build_vocab_doc,
    record_mistakes,
]

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}

__all__ = [
    "ALL_TOOLS",
    "TOOLS_BY_NAME",
    "load_text",
    "read_article",
    "lookup_word",
    "make_wordlist_csv",
    "build_worksheet_html",
    "build_vocab_doc",
    "record_mistakes",
]
