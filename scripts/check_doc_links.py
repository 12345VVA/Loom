#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docs 相对链接校验：扫描 docs/ 与仓库根目录 Markdown，检查本地链接目标是否存在。

用法（仓库根目录）：
    python scripts/check_doc_links.py            # 只校验 docs/
    python scripts/check_doc_links.py --all      # 额外校验根目录与 deliverables/

退出码：0 = 零断链；1 = 存在断链或锚点缺失。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__",
             ".workbuddy", "data", "logs", "_archive"}  # _archive = 冻结的历史快照，链接不再维护
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def slug(text: str) -> str:
    """GitHub 风格锚点：小写、去标点、空格转连字符。"""
    text = re.sub(r"`", "", text.strip())
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", text)
    return text.strip().lower().replace(" ", "-")


def anchors(path: Path) -> set[str]:
    out, in_fence = set(), False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEAD_RE.match(line)
        if m:
            out.add(slug(m.group(2)))
    return out


def iter_md(paths: list[Path]):
    for base in paths:
        for p in base.rglob("*.md"):
            if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
                continue
            yield p


def check(files: list[Path]) -> tuple[int, list[str]]:
    errors: list[str] = []
    total = 0
    cache: dict[Path, set[str]] = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            # 行内代码里的 [x](y) 不是链接，先剔除
            scan = re.sub(r"`[^`]*`", "", line)
            for m in LINK_RE.finditer(scan):
                target = m.group(1).strip()
                if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
                    continue
                total += 1
                path_part, _, frag = target.partition("#")
                if not path_part:
                    dest_code, dest = None, f
                else:
                    dest = (f.parent / path_part).resolve()
                    dest_code = dest
                rel = f.relative_to(ROOT).as_posix()
                if dest_code is not None and not dest_code.exists():
                    errors.append(f"{rel}:{lineno} 目标不存在 -> {target}")
                    continue
                if frag:
                    # 源码行锚点（#L17-L40）与 Markdown 标题锚点不是一套规则
                    if re.fullmatch(r"L\d+(-L\d+)?", frag):
                        continue
                    if path_part and dest.suffix.lower() != ".md":
                        continue
                    # 先判文件再读内容：目标可能是存在的目录，anchors() 对目录 read_text 会崩
                    if not dest.is_file():
                        errors.append(f"{rel}:{lineno} 锚点指向非文件 -> {target}")
                        continue
                    if dest not in cache:
                        cache[dest] = anchors(dest)
                    if slug(frag) not in cache[dest]:
                        errors.append(f"{rel}:{lineno} 锚点缺失 -> {target}")
    return total, errors


def main() -> int:
    # Windows 中文控制台 stdout 默认 GBK，"✅" 等字符会 UnicodeEncodeError 且退出码 1
    # 被误读为存在断链——统一按 UTF-8 输出，不可编码字符降级替换
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="额外校验根目录与 deliverables/")
    args = ap.parse_args()

    bases = [ROOT / "docs"]
    if args.all:
        bases += [ROOT / "deliverables"]
    files = sorted(set(iter_md(bases)))
    if args.all:
        files += sorted(ROOT.glob("*.md"))

    total, errors = check(files)
    print(f"扫描 {len(files)} 个 Markdown，检查 {total} 条本地链接")
    if errors:
        print(f"\n发现 {len(errors)} 条问题：")
        for e in errors:
            print("  ✗", e)
        return 1
    print("✅ 零断链")
    return 0


if __name__ == "__main__":
    sys.exit(main())
