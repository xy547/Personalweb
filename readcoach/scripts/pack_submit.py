"""打最终提交包。

为什么用脚本而不是右键压缩：要排除的东西很具体（.env 有密钥、.venv 有 500MB、
outputs 里有 Word 的 ~$ 锁文件），而且包里的目录结构要按「老师先看什么」排，
不是按仓库原样排。
"""

from pathlib import Path
import zipfile

ROOT = Path(r"D:\readcoach")
OUT = Path(r"D:\外刊精读教练-最终提交.zip")
TOP = "外刊精读教练-最终提交"

SKIP_DIRS = {".venv", ".git", "__pycache__", ".preview", "logs", "node_modules"}
SKIP_FILES = {".env", ".DS_Store", "Thumbs.db"}
SKIP_SUFFIX = {".pyc", ".pyo", ".log"}
# 运行期状态与可重新下载的原料：不该进提交包
SKIP_REL = {
    ("data", "session.json"),        # 会话历史属运行期状态，且是旧版七列说法
    ("data", "cache"),               # 每日推送的当天抓取缓存，跑一次就会重新生成
    ("scripts", "cache"),            # 2.6MB 原始词表，build_lexicon 会自动重下
}


def keep(path: Path) -> bool:
    if path.name.startswith("~$"):          # Word/Excel 打开时留下的锁文件
        return False
    if path.name in SKIP_FILES:
        return False
    if path.suffix.lower() in SKIP_SUFFIX:
        return False
    # 只把仓库根目录下带下划线前缀的当临时文件；__init__.py 是源码，不能误杀
    if path.parent == ROOT and path.name.startswith("_"):
        return False
    return True


def main() -> None:
    readme = Path(r"D:\readcoach\_提交说明.txt")
    if not readme.exists():
        raise SystemExit("缺少 _提交说明.txt")

    items: list[tuple[Path, str]] = []

    # 01 答辩材料：打开就能看的东西放最前面
    material = [
        (ROOT / "答辩幻灯片.pptx", "答辩幻灯片.pptx"),
        (ROOT / "答辩幻灯片.pdf", "答辩幻灯片.pdf"),
        (ROOT / "答辩幻灯片.html", "答辩幻灯片.html"),
        (ROOT / "代码解读.pptx", "代码解读.pptx"),
        (ROOT / "代码解读.pdf", "代码解读.pdf"),
        (ROOT / "代码解读.html", "代码解读.html"),
        (ROOT / "代码解读.docx", "代码解读.docx"),
        (ROOT / "docs" / "发言稿-答辩.docx", "发言稿-答辩.docx"),
        (ROOT / "docs" / "发言稿-录屏.docx", "发言稿-录屏.docx"),
        (ROOT / "docs" / "preview-word-note.png", "Word笔记版式预览.png"),
    ]
    for src, name in material:
        if not src.exists():
            raise SystemExit(f"缺少答辩材料：{src}")
        items.append((src, f"{TOP}/01-答辩材料/{name}"))

    items.append((readme, f"{TOP}/00-提交说明.txt"))

    # 02 项目源码：整个仓库，按排除规则过滤
    # 01 里已经放过的那几份（幻灯片 pptx/pdf/html、代码解读、两份讲稿）不再重复进源码树，
    # 否则包里会出现两个同名文件，老师不知道该看哪个。
    used = {src.resolve() for src, _ in items}
    count = 0
    for path in sorted(ROOT.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if any(rel.parts[: len(skip)] == skip for skip in SKIP_REL):
            continue
        if not keep(path):
            continue
        if path.resolve() in used:
            continue
        items.append((path, f"{TOP}/02-项目源码/readcoach/{rel.as_posix()}"))
        count += 1

    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, arc in items:
            zf.write(src, arc)

    size = OUT.stat().st_size / 1024
    print(f"OK {OUT}  {len(items)} 个文件  {size:.0f} KB  （源码 {count} 个）")


if __name__ == "__main__":
    main()
