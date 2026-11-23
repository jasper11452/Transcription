#!/usr/bin/env python3
"""把 post 服务手写的旧 import root 统一成命名空间包下的新 root。

为什么用脚本而不是手改：30 处引用里既有 `import x` / `from y import z`，
也有 pyproject 里的 `packages = [...]` 与 `[project.scripts]` 目标。
逐条 sed 容易漏，脚本按「必须是完整标识符」的边界替换，并把旧名拆开写，
免得脚本自己也被匹配到（第一次 dry-run 就踩了这个坑）。

用法：python3 -I unify_namespace.py [--check]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKIP = {".pytest_cache", ".ruff_cache", ".venv", "node_modules", "__pycache__", ".git"}

# 旧名拆成两段拼接 —— 这样本文件里不出现连续的旧名，脚本不会改到自己。
_OLD_A, _OLD_B = "transcript", "post"
OLD = f"{_OLD_A}_{_OLD_B}"
NEW = "transcript_reimagined.post"

# 只匹配完整标识符：前后都不能紧邻标识符字符或点（避免误伤 transcript_post_x
# 或别的包里的同名片段）。
PATTERN = re.compile(r"(?<![A-Za-z0-9_.])" + OLD + r"(?![A-Za-z0-9_])")

TEXT_EXT = {".py", ".toml", ".md", ".txt", ".cfg", ".json"}


def targets() -> list[pathlib.Path]:
    return [
        p
        for p in HERE.rglob("*")
        if p.is_file()
        and p.suffix in TEXT_EXT
        and not any(part in SKIP for part in p.parts)
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告，不写入")
    args = ap.parse_args()

    changed: list[tuple[pathlib.Path, int]] = []
    for p in targets():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        n = len(PATTERN.findall(text))
        if not n:
            continue
        changed.append((p, n))
        if not args.check:
            p.write_text(PATTERN.sub(NEW, text), encoding="utf-8")

    total = sum(n for _, n in changed)
    verb = "会改" if args.check else "已改"
    for p, n in sorted(changed):
        print(f"  {verb} {n:>2} 处  {p.relative_to(HERE)}")
    print(f"\n{verb} {total} 处，涉及 {len(changed)} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
