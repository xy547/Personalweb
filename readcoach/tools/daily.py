"""每日推送：今天读哪一篇、连续打卡几天。

为什么「推送」不是定时弹窗：
这个项目跑在本地，没有推送通道，硬造一个「消息推送」只会演示时翻车。
真正要解决的问题是「今天该读什么、我昨天断了没有」——多邻国的核心也是这两件事，
而它的实现方式就是「打开 App 首页上的那个任务卡」。

于是这里做三件事：

1. **选文**：按语种抓当天的一篇新闻，抓不到就用本地快照池按日期轮换。
   为什么必须有快照：答辩教室可能没网，或者对方站点改版。宁可给一篇「昨天的」，
   也不能让首页空着——空着就没法演示。
2. **去重**：同一天同一语种只抓一次，结果落在 data/cache/daily/<lang>/<date>.json。
   否则每刷新一次页面就打一次对方服务器，既不礼貌也不稳定。
3. **连续天数**：读完一篇记一个日期，按日期连续性算 streak。
   日期全部落盘（最多留 90 天），所以「连续 5 天」是可复查的，不是界面上的一个数字。

关于「外刊」这个词：这里抓的是新华网多语种版（英文/日文/法文/德文/西文），
公开可访问、没有付费墙，正文容器统一是 div#detail，抓取稳定。
它不是 The Economist，界面和回复里都必须照实写成「新华网英文版」这类具体来源，
不能笼统说成「外刊精选」。
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from config import DATA_DIR

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReadCoach/1.0 (+course project)",
    "Accept-Language": "en;q=0.9,*;q=0.8",
}
CACHE_DIR = DATA_DIR / "cache" / "daily"
POOL_DIR = DATA_DIR / "articles"
TIMEOUT = 6

# 新华网各语种站的文章 URL 形状一致：/YYYYMMDD/<32位hex>/c.html
# 首页里既有绝对地址也有相对地址（德文版是 20261027/xxx/c.html），两种都要认。
_ARTICLE_RE = re.compile(r'((?:https?://[^"\']+)?/?(\d{8})/[0-9a-f]{20,}/c\.html)')

# 选材偏好：只要经济 / 科技 / 文化 / 环保这类中性材料。
# 时政与灾难新闻不适合当精读素材——生词全落在专有名词上，讲起来也容易跑偏。
# 这是选材标准，不是内容审查：语言课要的是可迁移的学术词汇。
_SKIP_TOPIC = re.compile(
    r"CPC|Communist Party|Politburo|Party Congress|Xi Jinping|"
    r"共産党|习近平|"
    r"Parti communiste|président chinois|"
    r"Kommunistische Partei|Staatspräsident|"
    r"Partido Comunista|presidente chino|"
    r"earthquake|death toll|killed in|地震|震源|死者|戦争|"
    r"Erdbeben|getötet|terremoto|muertos|séisme|tremblement de terre",
    re.I,
)


def _suitable(title: str) -> bool:
    return not _SKIP_TOPIC.search(title or "")


def _today() -> date:
    return date.today()


# ---------------- 抓取 ----------------


def _home_url(code: str) -> str:
    from agent.languages import get

    return get(code)["site"]


def _site_name(code: str) -> str:
    from agent.languages import get

    return get(code)["site_name"]


def _abs_url(href: str, home: str) -> str:
    if href.startswith("http"):
        return href
    host = home.split("//", 1)[-1].split("/", 1)[0]
    return f"https://{host}/" + href.lstrip("/")


def _candidates(home_html: str, home: str) -> list[str]:
    """从首页抽出文章链接，最新日期在前，去重。"""
    seen: dict[str, str] = {}
    for href, day in _ARTICLE_RE.findall(home_html):
        seen.setdefault(_abs_url(href, home), day)
    return [u for u, _ in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)]


def _extract_body(html_text: str) -> tuple[str, str]:
    """返回 (标题, 正文)。正文取 div#detail 下的 p，空段与图注剔除。"""
    from lxml import html as LH

    doc = LH.fromstring(html_text)
    title = (doc.findtext(".//title") or "").strip()
    title = re.split(r"[-_|]", title)[0].strip() or title
    paras = []
    for p in doc.xpath("//div[@id='detail']//p"):
        t = re.sub(r"\s+", " ", p.text_content()).strip()
        if len(t) >= 30:
            paras.append(t)
    return title, "\n\n".join(paras)


def fetch_live(code: str, timeout: int = TIMEOUT) -> dict | None:
    """抓当天最新的一篇。失败返回 None——调用方负责回落，不在这里吞异常演成成功。"""
    import requests

    home = _home_url(code)
    try:
        r = requests.get(home, timeout=timeout, headers=HEADERS)
        r.raise_for_status()
    except Exception:
        return None

    best: dict | None = None
    for url in _candidates(r.text, home)[:4]:
        try:
            art = requests.get(url, timeout=timeout, headers=HEADERS)
            art.raise_for_status()
        except Exception:
            continue
        title, body = _extract_body(art.text)
        if len(body) < 400:
            continue  # 图片故事只有两段，不适合精读
        if not _suitable(title):
            continue  # 时政/灾难类不选，理由见 _SKIP_TOPIC
        item = {
            "lang": code,
            "title": title,
            "text": body,
            "url": url,
            "source": _site_name(code),
            "origin": "live",
        }
        if best is None or len(body) > len(best["text"]):
            best = item
        if len(body) >= 900:
            break  # 够长了就停，别为了「更好」把每个候选都抓一遍
    return best


# ---------------- 缓存与本地池 ----------------


def _cache_path(code: str, day: date) -> Path:
    d = CACHE_DIR / code
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{day.isoformat()}.json"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pool(code: str) -> list[dict]:
    """本地快照池，按文件名排序（文件名以日期开头，天然按新旧排）。"""
    d = POOL_DIR / code
    if not d.exists():
        return []
    items = []
    for f in sorted(d.glob("*.json")):
        data = _read_json(f)
        if data and len(data.get("text", "")) >= 300:
            items.append(data)
    return items


def _from_pool(code: str, day: date) -> dict | None:
    items = pool(code)
    if not items:
        return None
    # 用「日期序号」取模，保证同一天永远是同一篇，换一天才换一篇。
    item = dict(items[day.toordinal() % len(items)])
    item["origin"] = "pool"
    item["note"] = f"离线快照（抓取于 {item.get('fetched_at', '未知')}）"
    return item


# ---------------- 对外 ----------------


def pick(code: str = "en", day: date | None = None, allow_network: bool = True) -> dict:
    """取某天某语种的文章。顺序：当天缓存 → 联网抓 → 本地快照。

    返回值里一定有 origin 字段（live / pool），界面和回复都要按它说话：
    抓的是今天的新文章，还是离线快照，不能含糊。
    """
    day = day or _today()
    cached = _read_json(_cache_path(code, day))
    if cached and len(cached.get("text", "")) >= 300:
        return cached

    if allow_network:
        live = fetch_live(code)
        if live:
            live["date"] = day.isoformat()
            live["fetched_at"] = day.isoformat()
            _cache_path(code, day).write_text(
                json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return live

    fallback = _from_pool(code, day)
    if fallback:
        fallback["date"] = day.isoformat()
        return fallback

    return {
        "lang": code,
        "title": "（今天没有可用的文章）",
        "text": "",
        "url": "",
        "source": _site_name(code),
        "origin": "empty",
        "date": day.isoformat(),
        "note": "联网抓取失败，且本地快照池为空。请运行 scripts/fetch_pool.py 补一份快照。",
    }


def suggest_words(text: str, floor: int = 6, cap: int = 10) -> int:
    """按篇幅给一个「挑几个词」的建议值。200 词以内挑 6 个，长篇封顶 10 个。"""
    words = len(re.findall(r"[A-Za-zÀ-ÿ\u3040-\u30ff\u4e00-\u9fff]+", text or ""))
    if words <= 0:
        return floor
    return max(floor, min(cap, round(words / 45)))


def preview(item: dict, chars: int = 150) -> str:
    """首页卡片用的一句话摘要。取正文第一句，不额外生成内容。"""
    body = re.sub(r"\s+", " ", item.get("text", "")).strip()
    if not body:
        return item.get("note", "暂无内容")
    first = re.split(r"(?<=[.!?。！？])\s", body)[0]
    return first[:chars] + ("…" if len(first) > chars else "")


# ---------------- 连续天数 ----------------


def history(profile: dict) -> list[str]:
    return list(profile.get("daily_dates", []) or [])


def compute_streak(dates: list[str], day: date | None = None) -> int:
    """连续天数 = 从今天（或昨天）往前数，一天不断。

    今天还没读时，保留到昨天的连续记录：否则每天零点一过，
    界面上的 5 天会突然变成 0，用户会以为自己的记录丢了。
    """
    day = day or _today()
    pool_set = set(dates)
    cursor = day if day.isoformat() in pool_set else day - timedelta(days=1)
    n = 0
    while cursor.isoformat() in pool_set:
        n += 1
        cursor -= timedelta(days=1)
    return n


def done_today(profile: dict, day: date | None = None) -> bool:
    return (day or _today()).isoformat() in set(history(profile))


def record_done(code: str, day: date | None = None) -> dict:
    """记一次打卡，返回 {streak, total, done_today}。同一天重复调用不会加天。"""
    from tools.memory import load_profile, save_profile

    day = day or _today()
    profile = load_profile()
    dates = history(profile)
    stamp = day.isoformat()
    if stamp not in dates:
        dates.append(stamp)
    dates = sorted(set(dates))[-90:]
    profile["daily_dates"] = dates
    profile["daily_lang"] = code
    profile["language"] = profile.get("language", code)
    save_profile(profile)
    return {
        "date": stamp,
        "streak": compute_streak(dates, day),
        "total": len(dates),
        "done_today": True,
    }


def status(code: str = "en", day: date | None = None) -> dict:
    from tools.memory import load_profile

    profile = load_profile()
    dates = history(profile)
    return {
        "done_today": done_today(profile, day),
        "streak": compute_streak(dates, day),
        "total": len(dates),
    }
