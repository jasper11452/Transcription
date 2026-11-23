"""零依赖契约 —— 机器可验证地守住 `domain` 的边界。

架构把 `domain` 定为**全仓唯一的零依赖包**（`REIMAGINED_ARCHITECTURE.md` §2）：
零 I/O、零第三方依赖、不依赖同仓任何其他包，位置在依赖图最底层

    domain ← config ← {ingest, engines, post, diar, state} ← orchestrate ← web

「零依赖」不是口号：它在四处的任何一处被放宽，下游的分层契约就会静默失效。
所以这里用四道独立的检查钉住，不靠调用方纪律，也不靠 code review：

1. 静态（AST）：src 里每个 import 都必须是 stdlib，或同包内相对导入（只允许 level 1）。
2. 静态（AST）：不得出现任何做 I/O 的 stdlib 模块，也不得用 `__import__` / `importlib` 绕过。
3. 逐文件白名单：每个模块的 import 集合被**精确**断言，加一行 import 就会红。
4. 动态（隔离子进程）：`python -I` 下导入 `transcript_reimagined.domain`，断言加载进来的
   非 stdlib 模块为空 —— 排除「静态看着干净、运行时拉进第三方」的可能。
5. 打包层：`pyproject.toml` 的 `project.dependencies` 必须是空列表。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PACKAGE_ROOT / "src"
PACKAGE_DIR = SRC_ROOT / "transcript_reimagined" / "domain"
SOURCE_FILES = sorted(PACKAGE_DIR.rglob("*.py"))

# 会做 I/O 或引入运行时资源的 stdlib 模块：领域层一个都不许碰。
FORBIDDEN_MODULES = frozenset(
    {
        "asyncio",
        "concurrent",
        "ctypes",
        "ftplib",
        "http",
        "importlib",
        "io",
        "logging",
        "mmap",
        "multiprocessing",
        "os",
        "pickle",
        "select",
        "selectors",
        "shutil",
        "signal",
        "smtplib",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "tempfile",
        "threading",
        "urllib",
        "uuid",
        "webbrowser",
    }
)

# 每个模块允许的 import 集合 —— 精确匹配，顺序无关。
ALLOWED_IMPORTS_BY_MODULE = {
    "models.py": {"__future__", "dataclasses", "math", "pathlib"},
    # errors.py 除 `__future__` 外无 import（架构 §2 明确写了这一条）
    "errors.py": {"__future__"},
    "__init__.py": {
        "__future__",
        "transcript_reimagined.domain.errors",
        "transcript_reimagined.domain.models",
    },
}


def _module_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name
    if node.level:  # 相对导入
        return "." * node.level + (node.module or "")
    return node.module or ""


def _imports_of(path: Path) -> list[tuple[str, int]]:
    """返回 [(模块名, 行号)]，覆盖条件分支里的 import。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((_module_name(node), node.lineno))
    return found


def test_zero_dependency_contract_src_has_sources_to_scan() -> None:
    """先证明扫描器确实扫到了东西 —— 一个扫不到文件的守卫等于没有守卫。"""
    assert SOURCE_FILES, f"没在 {PACKAGE_DIR} 找到任何 .py"
    assert {p.name for p in SOURCE_FILES} == set(ALLOWED_IMPORTS_BY_MODULE)


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_zero_dependency_contract_every_import_is_stdlib_or_in_package(path: Path) -> None:
    for module, lineno in _imports_of(path):
        if module.startswith("."):
            depth = len(module) - len(module.lstrip("."))
            assert depth == 1, (
                f"{path.name}:{lineno} 的 `from {module} import …` 跳出了本包；"
                "domain 不得依赖同仓其他包"
            )
            continue
        top = module.split(".")[0]
        assert top in sys.stdlib_module_names, (
            f"{path.name}:{lineno} 导入了非 stdlib 模块 `{module}`；domain 必须零第三方依赖"
        )
        assert top != "transcript", (
            f"{path.name}:{lineno} 用绝对路径导入同包/同仓 `{module}`；包内一律用相对导入"
        )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_zero_dependency_contract_no_io_modules(path: Path) -> None:
    for module, lineno in _imports_of(path):
        top = module.split(".")[0]
        assert top not in FORBIDDEN_MODULES, (
            f"{path.name}:{lineno} 引入了会做 I/O 的 `{module}`；domain 零 I/O"
        )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_zero_dependency_contract_no_dynamic_import_escape_hatch(path: Path) -> None:
    """`__import__` / `importlib` 会让上面的静态扫描失效，所以单独禁掉。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "__import__", f"{path.name}:{node.lineno} 用了 __import__"


def _normalized_imports(path: Path) -> set[str]:
    """把相对导入归一成同包全名（`from .errors import …` → `transcript_reimagined.domain.errors`）。"""
    out = set()
    for module, _ in _imports_of(path):
        if module.startswith("."):
            out.add("transcript_reimagined.domain." + module.lstrip("."))
        else:
            out.add(module)
    return out


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_zero_dependency_contract_import_set_is_exactly_whitelisted(path: Path) -> None:
    """逐文件精确白名单：任何新增 import 都必须先改这张表并说明理由。"""
    actual = _normalized_imports(path)
    expected = ALLOWED_IMPORTS_BY_MODULE[path.name]
    assert actual == expected, (
        f"{path.name} 的 import 集合变了。domain 的依赖面是契约的一部分："
        f"新增 {sorted(actual - expected)}，移除 {sorted(expected - actual)}"
    )


def test_zero_dependency_contract_imports_nothing_foreign_in_isolated_interpreter() -> None:
    """`python -I -S` 下导入，看有没有第三方被拉进来。

    `-I` 忽略 PYTHONPATH/PYTHONHOME 与用户 site；`-S` 再关掉 `.venv` 的
    `sitecustomize`（本机 venv 会经它注入 `_virtualenv`/`_distutils_hack`）。
    cwd 也特意设成 `/`，避免「恰好站在包目录里」让导入意外成功。
    """
    probe = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SRC_ROOT)!r})\n"
        "import transcript_reimagined.domain as d\n"
        "assert d.fmt_timestamp(0.0) == '00:00:00,000'\n"
        "assert d.classify_http(429).recoverable is True\n"
        "stdlib = sys.stdlib_module_names | {'__main__'}\n"
        "own = ('transcript_reimagined', 'transcript')\n"
        "foreign = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.split('.')[0] not in stdlib and not m.startswith(own)\n"
        ")\n"
        "loaded = sorted(m for m in sys.modules if m.startswith('transcript_reimagined'))\n"
        "print(json.dumps({'foreign': foreign, 'loaded': loaded}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe],
        capture_output=True,
        text=True,
        cwd="/",  # 与包目录无关的 cwd，避免误拾路径
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["foreign"] == [], f"隔离导入拉进了非 stdlib 模块：{payload['foreign']}"
    assert set(payload["loaded"]) == {
        "transcript_reimagined",
        "transcript_reimagined.domain",
        "transcript_reimagined.domain.models",
        "transcript_reimagined.domain.errors",
    }


def test_zero_dependency_contract_pyproject_declares_no_dependencies() -> None:
    """打包层同样守住：这里出现任何依赖都会让架构的「零依赖包」断言变假。"""
    data = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []
    assert data["project"]["requires-python"] == ">=3.12,<3.13"
