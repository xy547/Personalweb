"""全局配置：模型客户端参数、路径常量、以及写盘权限边界。

这里集中的三件事，正好对应 README 里要讲的三个设计点：
1. 模型走 OpenAI 兼容接口，换模型只改环境变量，不改代码；
2. 所有路径由本文件统一给出，工具里不出现硬编码路径；
3. safe_output_path() 是权限隔离的唯一入口，Agent 只能写 outputs/。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
DEMO_DIR = ROOT / "demo"
SKILL_DIR = ROOT / "skills"

# 用户粘贴的正文只能落在这一个固定文件里，Agent 没有路径可指。
CURRENT_ARTICLE_PATH = DATA_DIR / "current_article.txt"

for _d in (OUTPUT_DIR, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---- 模型 ----
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
BASE_URL = os.getenv(
    "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).strip()
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-plus").strip()
MODEL_NAME_FAST = os.getenv("MODEL_NAME_FAST", "qwen-turbo").strip()

# ---- 权限边界 ----
_ILLEGAL = '\\/:*?"<>|'


def safe_output_path(filename: str, default_ext: str = ".txt") -> Path:
    """把文件名收敛到 outputs/ 目录内部，越界直接抛错。

    为什么是「报错」而不是「悄悄改写成文件名」：
    Agent 生成的 filename 属于不可信输入。如果拿 basename 把 ../evil.txt
    静默截成 evil.txt，文件确实安全了，但模型会以为自己写到了别的位置，
    后续汇报路径就会错。明确失败，模型才能自己纠正参数——失败可解释，
    比默默成功更重要。

    允许 "outputs/xxx.csv" 这种带目录前缀的写法（模型常这么写），
    先剥掉前缀再校验。
    """
    raw = (filename or "").strip().replace("\\", "/")
    if raw.lower().startswith("outputs/"):
        raw = raw[len("outputs/"):]

    if "/" in raw or raw in (".", ".."):
        raise ValueError(
            f"拒绝写入 outputs 之外的路径：{filename}"
            "（filename 只接受纯文件名，例如 wordlist.csv）"
        )

    name = "".join(c for c in raw if c not in _ILLEGAL).strip()
    if not name or name in (".", ".."):
        name = f"untitled{default_ext}"
    if not os.path.splitext(name)[1]:
        name += default_ext

    target = (OUTPUT_DIR / name).resolve()
    out_root = OUTPUT_DIR.resolve()
    if target.parent != out_root:
        raise ValueError(f"拒绝写入 outputs 之外的路径：{filename}")
    return target


def has_api_key() -> bool:
    return bool(DASHSCOPE_API_KEY) and not DASHSCOPE_API_KEY.startswith("sk-xxx")


def missing_key_hint() -> str:
    return (
        "还没有配置 API Key。\n\n"
        "1. 在项目根目录执行：copy .env.example .env\n"
        "2. 打开 .env，把 DASHSCOPE_API_KEY 换成你自己的百炼 Key\n"
        "3. 重新运行 streamlit run app.py\n\n"
        "Key 获取地址：https://bailian.console.aliyun.com/"
    )
