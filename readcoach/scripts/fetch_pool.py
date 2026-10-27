"""抓取各语种的离线快照，存进 data/articles/<lang>/。

为什么要有这一步：
`tools/daily.py` 的取文顺序是「当天缓存 → 联网抓 → 本地快照」。
快照池是最后一道保险，答辩教室没网时首页才不至于空着。
快照是**真实抓下来的正文**（不是模型编的），文件名带抓取日期，
库里也记着原文 URL，被问到「这篇哪来的」可以直接打开原链接对。

用法：
    .venv/Scripts/python.exe scripts/fetch_pool.py            # 每个语种抓 3 篇
    .venv/Scripts/python.exe scripts/fetch_pool.py ja de      # 只补指定语种
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from agent.languages import codes  # noqa: E402
from tools.daily import (  # noqa: E402
    HEADERS,
    POOL_DIR,
    TIMEOUT,
    _candidates,
    _extract_body,
    _home_url,
    _site_name,
    _suitable,
)


def grab(code: str, want: int = 3) -> list[dict]:
    home = _home_url(code)
    r = requests.get(home, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    out: list[dict] = []
    used: set[str] = set()
    for url in _candidates(r.text, home):
        if len(out) >= want:
            break
        if url in used:
            continue
        used.add(url)
        try:
            art = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            art.raise_for_status()
        except Exception:
            continue
        title, body = _extract_body(art.text)
        if len(body) < 500:
            continue
        if not _suitable(title):
            continue
        out.append(
            {
                "lang": code,
                "title": title,
                "text": body,
                "url": url,
                "source": _site_name(code),
                "origin": "pool",
                "fetched_at": date.today().isoformat(),
            }
        )
    return out


def _slug(title: str, idx: int) -> str:
    keep = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]+", "-", title).strip("-")
    return f"{date.today().isoformat()}-{idx:02d}-{(keep or 'article')[:24]}"


def main(argv: list[str]) -> int:
    targets = [c for c in argv if c in codes()] or codes()
    total = 0
    for code in targets:
        try:
            items = grab(code, want=3)
        except Exception as exc:
            print(f"[{code}] 抓取失败：{type(exc).__name__}: {exc}")
            continue
        if not items:
            print(f"[{code}] 没有可用正文（站点结构可能变了）")
            continue
        d = POOL_DIR / code
        d.mkdir(parents=True, exist_ok=True)
        for i, item in enumerate(items, 1):
            path = d / f"{_slug(item['title'], i)}.json"
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            total += 1
        print(f"[{code}] {len(items)} 篇 → {d}")
        for i, item in enumerate(items, 1):
            print(f"    {i}. {item['title'][:46]}  ({len(item['text'])} 字符)")
    print(f"共写入 {total} 篇快照")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
