"""架构约束的可执行检查。

架构 §3 把「无环性」从口号变成可检查事实：``pyproject.toml`` 里声明 import-linter 的
分层 contract，这里在 pytest 里跑它，**并且**用一份不依赖第三方工具的 AST 检查兜底
（这样即使没装 dev 依赖，方向性也不会无人看守）。

分层方向：``runner → {ingest, post} → domain``。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE_ROOT = SRC / "transcript_reimagined"

#: workspace 根与四个成员的 ``src``。import-linter 要解析整个
#: ``transcript_reimagined`` 命名空间，只给 runner/src 会让 domain/ingest/post
#: 变成未解析的外部包。这里与 CLAUDE.md 里那条 lint-imports 命令保持同一组路径。
WORKSPACE = ROOT.parent
MEMBER_SRC = [WORKSPACE / name / "src" for name in ("domain", "ingest", "post", "runner")]

RUNNER = "runner"
POST = "post"
INGEST = "ingest"
DOMAIN = "domain"

#: 包 → 允许被它依赖的其它包（越靠左越上层）
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    RUNNER: {POST, INGEST, DOMAIN},
    POST: {DOMAIN},
    INGEST: {DOMAIN},
    DOMAIN: set(),
}

#: ``domain`` 只允许这些标准库（它是「零 I/O、零第三方依赖」的公共词汇）
#: 相对 import 会被解析成包名 ``domain``（同包内部依赖），一并放行。
DOMAIN_ALLOWED_IMPORTS = {"__future__", "math", "dataclasses", "pathlib", "typing", DOMAIN}

#: 本切片范围内**不得出现**的能力（属 Phase 2/5/6）
BANNED_IMPORTS = {
    "sqlite3": "state/store 属 Phase 2 —— state.db 的唯一写入者不是本切片",
    "socket": "网络属 Phase 4/6",
    "urllib": "网络属 Phase 4/6",
    "httpx": "云端引擎属 Phase 4",
    "requests": "云端引擎属 Phase 4",
    "fastapi": "web 层属 Phase 6（本服务不含路由）",
    "uvicorn": "web 层属 Phase 6（本服务不起服务）",
}


def _py_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _top_level_imports(path: Path) -> list[tuple[int, str]]:
    """返回 ``(行号, 本包内的顶层包名)``。

    相对 import 按包层级解析成本包内的顶层包，因此：

    - ``domain/__init__.py`` 里的 ``from .errors import`` → ``domain``（同包，不越层）
    - ``post/glossary.py`` 里的 ``from ..domain.models import`` → ``domain``
    - ``runner/run.py`` 里的 ``from ..post.render import`` → ``post``
    """
    parts = path.relative_to(PACKAGE_ROOT).parts[:-1]
    found: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(parts[: max(0, len(parts) - (node.level - 1))])
                resolved = base + (node.module.split(".") if node.module else [])
                if resolved:
                    found.append((node.lineno, resolved[0]))
            elif node.module:
                found.append((node.lineno, node.module.split(".")[0]))
    return found


def test_the_four_packages_import_cleanly():
    for package in ("runner", "post", "ingest", "domain"):
        __import__(f"transcript_reimagined.{package}")


def test_dependency_direction_is_single_way():
    """逐文件检查：谁都不许反向依赖上层包。"""
    for path in _py_files():
        parts = path.relative_to(PACKAGE_ROOT).parts
        if len(parts) == 1:  # 包根 __init__.py
            continue
        owner = parts[0]
        allowed = ALLOWED_DEPENDENCIES[owner]
        for lineno, module in _top_level_imports(path):
            if module not in {RUNNER, POST, INGEST, DOMAIN}:
                continue
            if module == owner:
                continue
            assert module in allowed, (
                f"{path.relative_to(ROOT)}:{lineno} 依赖了 {module}，"
                f"但 {owner} 只允许依赖 {sorted(allowed)}"
            )


def test_domain_never_depends_on_a_higher_layer():
    """``domain`` 是公共词汇：它不知道 ``post`` / ``ingest`` / ``runner`` 存在。"""
    for path in sorted((PACKAGE_ROOT / "domain").glob("*.py")):
        modules = [module for _, module in _top_level_imports(path)]
        assert not ({POST, INGEST, RUNNER} & set(modules)), f"{path.name}: {modules}"


def test_domain_has_no_third_party_or_io_imports():
    """``domain`` 只用 ``math``/``dataclasses``/``pathlib`` —— 用源码文本卡住这条性质。"""
    for path in sorted((PACKAGE_ROOT / "domain").glob("*.py")):
        for lineno, module in _top_level_imports(path):
            if module in {POST, INGEST, RUNNER}:
                continue
            assert module in DOMAIN_ALLOWED_IMPORTS, f"{path.name}:{lineno} import {module}"


def test_no_out_of_scope_capabilities_leak_into_the_slice():
    """范围纪律（架构 §5）：本切片不含 config、不含 store、不含 pipeline、不含 web。"""
    for path in _py_files():
        for lineno, module in _top_level_imports(path):
            assert module not in BANNED_IMPORTS, (
                f"{path.relative_to(ROOT)}:{lineno} 用到了 {module} —— {BANNED_IMPORTS[module]}"
            )


def test_import_linter_contracts_hold():
    """跑 ``pyproject.toml`` 里声明的 import-linter 契约。

    import-linter 的公开 CLI 入口是 ``importlinter.cli.lint_imports_command``
    （console script ``lint-imports``）；它没有 ``python -m`` 入口，因此这里用
    ``subprocess`` 跑一个显式构造的小脚本，而不是猜一个模块路径。
    """
    try:
        import importlinter  # noqa: F401
    except ImportError:
        pytest.skip(
            "import-linter 未安装（dev 依赖）—— 分层契约未被执行。"
            "安装：在 runner/ 目录执行 `uv sync` 或 `pip install import-linter`；"
            "方向性仍由上面的 AST 检查兜底。"
        )
    runner_script = (
        "import sys;from importlinter.cli import lint_imports_command;"
        "sys.exit(lint_imports_command.main(args=['--config', 'pyproject.toml'], standalone_mode=False))"
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(p) for p in MEMBER_SRC))
    completed = subprocess.run(
        [sys.executable, "-c", runner_script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "KEPT" in completed.stdout
