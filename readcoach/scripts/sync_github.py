#!/usr/bin/env python
"""把本项目作为子目录同步到 GitHub 仓库（走 Git Data API）。

为什么不用 `git push`：
    本机到 github.com:443 的 HTTPS 走代理时 CONNECT 被拦，clone/push 都失败；
    但 api.github.com 可达，所以改用 Git Data API 直接写 main 分支。
    副作用：GitHub 上只有一次快照提交，本地的完整 git 历史仍留在本机。

用法：
    python scripts/sync_github.py                      # 默认推 xy547/Personalweb 的 readcoach/
    python scripts/sync_github.py --dry-run            # 只统计，不写远端
    python scripts/sync_github.py --repo 用户名/仓库 --prefix 子目录名 --branch main

token 来源：优先读环境变量 GITHUB_TOKEN，否则从 git 凭据管理器取 github.com 的凭据
（即 `git config --global credential.helper` 存的那个，Windows 上是凭据管理器）。
需要的权限：repo（classic PAT）。
"""
from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"


def get_token() -> str:
    import os

    tok = os.getenv("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        timeout=20,
    )
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("拿不到 GitHub 凭据：先设置 GITHUB_TOKEN，或让 git 记住一次 github.com 的账号。")


class Gh:
    def __init__(self, owner: str, repo: str, token: str):
        self.base = f"{API}/repos/{owner}/{repo}"
        self.h = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    def call(self, method: str, url: str, **kw):
        for attempt in range(4):
            r = requests.request(method, url, headers=self.h, timeout=90, **kw)
            if r.status_code < 300:
                return r.json() if r.text else {}
            # 二级速率限制 / 网关抖动：退避重试
            if r.status_code in (403, 429, 502, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            sys.exit(f"失败 {method} {url} -> {r.status_code}\n{r.text[:500]}")
        return {}


def list_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    return [f for f in out.stdout.decode("utf-8").split("\0") if f]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="xy547/Personalweb", help="用户名/仓库名")
    ap.add_argument("--prefix", default="readcoach", help="目标子目录名，留空则放仓库根目录")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    owner, _, repo = args.repo.partition("/")
    if not repo:
        sys.exit("--repo 要写成 用户名/仓库名")

    files = list_files()
    total = sum((ROOT / f).stat().st_size for f in files)
    print(f"{len(files)} 个文件 / {total / 1024 / 1024:.2f} MB -> {owner}/{repo}"
          f"{'/' + args.prefix if args.prefix else ''} @ {args.branch}")
    if args.dry_run:
        return

    gh = Gh(owner, repo, get_token())
    head_sha = gh.call("GET", f"{gh.base}/git/ref/heads/{args.branch}")["object"]["sha"]
    base_tree = gh.call("GET", f"{gh.base}/git/commits/{head_sha}")["tree"]["sha"]
    print(f"远端 HEAD {head_sha[:10]}")

    def make_blob(rel: str):
        data = (ROOT / rel).read_bytes()
        sha = gh.call(
            "POST", f"{gh.base}/git/blobs",
            json={"content": base64.b64encode(data).decode(), "encoding": "base64"},
        )["sha"]
        return rel, sha

    entries = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (rel, sha) in enumerate(ex.map(make_blob, files), 1):
            path = f"{args.prefix}/{rel}" if args.prefix else rel
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
            if i % 15 == 0 or i == len(files):
                print(f"  上传 {i}/{len(files)}")

    tree = gh.call("POST", f"{gh.base}/git/trees",
                   json={"base_tree": base_tree, "tree": entries})["sha"]
    msg = (f"chore(readcoach): 同步本地快照\n\n"
           f"{len(files)} 个文件 / {total / 1024 / 1024:.2f} MB\n")
    commit = gh.call("POST", f"{gh.base}/git/commits",
                     json={"message": msg, "tree": tree, "parents": [head_sha]})["sha"]
    gh.call("PATCH", f"{gh.base}/git/refs/heads/{args.branch}",
            json={"sha": commit, "force": False})
    print(f"完成 -> https://github.com/{owner}/{repo}/commit/{commit}")


if __name__ == "__main__":
    main()
