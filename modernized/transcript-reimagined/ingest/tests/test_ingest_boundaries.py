"""``ingest`` 的边界契约 —— 机器可验证，不靠调用方纪律。

架构（``REIMAGINED_ARCHITECTURE.md`` §2 与 §3）把 ``ingest`` 定成一层：

    domain <- ingest <- orchestrate

所以本包被钉住三件事：

1. **只依赖 ``domain``**（同仓）与 stdlib —— 架构砍掉了 ``engines -> ingest`` 这条边，
   没有下游反向依赖。
2. **不作 I/O、不碰网络、不碰 SQLite**：``chunking`` 是纯函数，两次调用同样输入
   必须给同样输出。唯一碰 ffmpeg 的 ``audio.py`` 属 Phase 3，且只经 ``subprocess``。
3. **可打包**：``pyproject.toml`` 只打包本服务，且 ``dependencies`` 为空
   （切片规划不需要任何第三方库）。

这些断言不是走形式：架构的 §7b 范围纪律要求脚手架阶段**不得**出现新依赖。
多一条 import 就是多一处需要回到规格的偏离，所以这里逐文件精确白名单。
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
PACKAGE_DIR = SRC_ROOT / "transcript_reimagined" / "ingest"
SOURCE_FILES = sorted(PACKAGE_DIR.glob("*.py"))

#: 兄弟服务 `domain` 的 `src/`：`transcript_reimagined` 是 PEP 420 命名空间包，
#: 两个片段要同时在 `sys.path` 上才能合并成同一个顶层包（见 ``conftest.py``）。
SIBLING_DOMAIN_SRC = PACKAGE_ROOT.parent / "domain" / "src"

#: Phase 1 落地的两个纯模块：零 I/O 由下面的 AST 扫描强制。
#: ``audio.py`` / ``vad.py`` 属 Phase 3，会需要 ``subprocess`` / ``pathlib`` 之外的
#: 东西，届时按规则卡逐个放行，而不是现在放宽整张表。
PURE_MODULES = frozenset({"__init__.py", "chunking.py", "plan.py"})

#: 会做 I/O 或引入运行时资源的 stdlib 模块 —— 纯规划层一个都不许碰。
#: ``audio.py`` / ``vad.py``（Phase 3）会需要 ``subprocess`` / ``Path`` 之外的
#: 东西，届时按规则卡逐个放行，而不是现在放宽整张表。
FORBIDDEN_MODULES = frozenset(
    {
        "asyncio",
        "ctypes",
        "http",
        "importlib",
        "io",
        "logging",
        "mmap",
        "multiprocessing",
        "os",
        "pickle",
        "select",
        "shutil",
        "signal",
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

#: 每个模块允许的 import 集合 —— 精确匹配，顺序无关。
#: 为什么 ``plan.py`` 允许 ``dataclasses``：``ChunkPlan`` 是不变量携带者，
#: 让 ``__post_init__`` 在构造时校验比在每个调用点校验更难漏。
ALLOWED_IMPORTS_BY_MODULE = {
    "__init__.py": {
        "__future__",
        "transcript_reimagined.ingest.audio",
        "transcript_reimagined.ingest.chunking",
        "transcript_reimagined.ingest.plan",
        "transcript_reimagined.ingest.vad",
    },
    "chunking.py": {
        "__future__",
        "transcript_reimagined.domain.models",
        "transcript_reimagined.ingest.plan",
    },
    "plan.py": {"__future__", "dataclasses"},
    # Phase 3：audio 是唯一碰 ffmpeg 的模块；vad 懒加载 mlx-audio。
    "audio.py": {
        "__future__",
        "collections.abc",
        "contextlib",
        "json",
        "pathlib",
        "shutil",
        "subprocess",
        "transcript_reimagined.domain",
    },
    "vad.py": {
        "__future__",
        "collections.abc",
        "mlx_audio.vad",
        "pathlib",
        "transcript_reimagined.domain",
        "typing",
    },
}


def _module_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name
    if node.level:  # 相对导入
        return "." * node.level + (node.module or "")
    return node.module or ""


def _imports_of(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((_module_name(node), node.lineno))
    return found


def _normalized_imports(path: Path) -> set[str]:
    """相对导入归一成同包全名：``from ..domain.models import Chunk`` →
    ``transcript_reimagined.domain.models``；``from .plan import …`` →
    ``transcript_reimagined.ingest.plan``。"""
    out = set()
    for module, _ in _imports_of(path):
        if not module.startswith("."):
            out.add(module)
            continue
        depth = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".")
        prefix = "transcript_reimagined." if depth == 2 else "transcript_reimagined.ingest."
        out.add(prefix + rest)
    return out


def test_sources_to_scan_exist() -> None:
    """一个扫不到文件的守卫等于没有守卫。"""
    assert SOURCE_FILES, f"没在 {PACKAGE_DIR} 找到任何 .py"
    assert {p.name for p in SOURCE_FILES} == set(ALLOWED_IMPORTS_BY_MODULE)


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_every_import_is_stdlib_domain_or_in_package(path: Path) -> None:
    """``ingest`` 只许依赖 stdlib、``domain``、以及本包自己。"""
    for module, lineno in _imports_of(path):
        if module.startswith("."):
            assert ".." not in module or module.startswith("..domain"), (
                f"{path.name}:{lineno} 的 `from {module} import …` 跳出了允许范围；"
                "ingest 只能依赖 domain 与本包"
            )
            continue
        top = module.split(".")[0]
        if top == "mlx_audio":
            # 唯一放行的第三方依赖：VAD 的模型运行时，且只在 vad.py 里懒加载。
            assert path.name == "vad.py", (
                f"{path.name}:{lineno} 导入了 `{module}`；只有 vad.py 可以依赖 mlx-audio"
            )
            continue
        if top == "transcript_reimagined":
            assert module == "transcript_reimagined.domain" or module.startswith(
                "transcript_reimagined.domain."
            ), f"{path.name}:{lineno} 导入了 `{module}`；ingest 只许依赖 domain"
            continue
        assert top in sys.stdlib_module_names, (
            f"{path.name}:{lineno} 导入了非 stdlib 模块 `{module}`；本包只允许 domain 与 mlx-audio"
        )
        assert top != "transcript", (
            f"{path.name}:{lineno} 用绝对路径导入遗留包 `{module}`；"
            "包内一律相对导入，绝不能把重建版接到遗留实现上"
        )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_io_modules_in_the_pure_planning_layer(path: Path) -> None:
    """纯函数约束只覆盖 chunking/plan；audio/vad 有 I/O 权限，由规则卡逐条放行。"""
    if path.name not in PURE_MODULES:
        pytest.skip(f"{path.name} 是有 I/O 权限的模块；纯函数约束只覆盖 chunking/plan")
    for module, lineno in _imports_of(path):
        top = module.split(".")[0]
        assert top not in FORBIDDEN_MODULES, (
            f"{path.name}:{lineno} 引入了会做 I/O 的 `{module}`；"
            "切片规划是纯函数，I/O 归 Phase 3 的 audio.py"
        )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_dynamic_import_escape_hatch(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "__import__", f"{path.name}:{node.lineno} 用了 __import__"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_import_set_is_exactly_whitelisted(path: Path) -> None:
    """逐文件精确白名单：任何新增 import 都必须先改这张表并说明理由。"""
    actual = _normalized_imports(path)
    expected = ALLOWED_IMPORTS_BY_MODULE[path.name]
    assert actual == expected, (
        f"{path.name} 的 import 集合变了。ingest 的依赖面是架构契约的一部分："
        f"新增 {sorted(actual - expected)}，移除 {sorted(expected - actual)}"
    )


def test_package_declares_no_third_party_runtime_dependency() -> None:
    """运行时依赖白名单：``mlx-audio`` 是 VAD 的唯一第三方依赖。

    切片规划本身零依赖。``transcript-domain`` 是 PEP 420 命名空间下的**兄弟
    包**（同一个 workspace 的成员），不是外部依赖 —— 架构 §7b 的范围纪律禁止的
    是引入第三方库，不是禁止成员互相引用。Phase 3 按规则放行 ``mlx-audio``
    （VAD 模型运行时，懒加载），其余任何第三方都应视为偏离。
    """
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    third_party = sorted(
        d for d in project["project"]["dependencies"] if not d.startswith("transcript-")
    )
    assert [d.split(">")[0].split("=")[0] for d in third_party] == ["mlx-audio"]
    assert project["project"]["requires-python"] == ">=3.12,<3.13"


def test_packaging_targets_only_this_service() -> None:
    """只打包本服务，不是整个重建版（``transcript_reimagined`` 是 PEP 420 命名空间）。

    包根必须写成命名空间根：本成员的 ``src/transcript_reimagined`` 里只有 ``ingest/``，
    所以打包范围仍是本服务；但 editable 安装会把包根的父目录放进 sys.path，写成
    ``src/transcript_reimagined/ingest`` 会让顶层命名空间无法与其他成员合并
    （UAT 实测：安装后 ``import transcript_reimagined.cli`` 失败）。
    """
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert packages == ["src/transcript_reimagined"]


def test_imports_cleanly_in_an_isolated_interpreter() -> None:
    """``python -I -S`` 下导入，断言没有第三方被拉进来、也没有连带加载遗留包。

    cwd 特意设成 ``/``：避免「恰好站在包目录里」让导入意外成功。
    特别注意 ``transcript``（遗留包）**不在**加载列表里 —— 重建版与旧树并存，
    若哪天本包开始 import 它，等价性对比就会变成同义反复。
    """
    probe = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SIBLING_DOMAIN_SRC)!r})\n"
        f"sys.path.insert(0, {str(SRC_ROOT)!r})\n"
        "from transcript_reimagined.ingest import plan_chunks\n"
        "from transcript_reimagined.ingest.plan import ChunkPlan\n"
        "chunks = plan_chunks([(0.0, 300.0)], 300.0, min_s=30.0, max_s=120.0, overlap_s=0.5)\n"
        "assert chunks\n"
        "assert ChunkPlan().max_s == 120.0\n"
        "stdlib = sys.stdlib_module_names | {'__main__'}\n"
        "own = ('transcript_reimagined', 'transcript')\n"
        "foreign = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.split('.')[0] not in stdlib and not m.startswith(own)\n"
        ")\n"
        "legacy = sorted(m for m in sys.modules if m == 'transcript' or m.startswith('transcript.'))\n"
        "print(json.dumps({'foreign': foreign, 'legacy': legacy}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe],
        capture_output=True,
        text=True,
        cwd="/",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["foreign"] == [], f"隔离导入拉进了非 stdlib 模块：{payload['foreign']}"
    assert payload["legacy"] == [], f"隔离导入连带加载了遗留包：{payload['legacy']}"


def test_chunking_and_plan_do_not_read_or_write_anything(tmp_path, monkeypatch) -> None:
    """纯函数性质：同样输入两次调用给同样输出，且不产生任何文件。"""
    from transcript_reimagined.ingest.chunking import plan_chunks

    def forge(*args, **kwargs):  # pragma: no cover - 只要被调用就会失败
        raise AssertionError("纯函数不许调用 open/写入")

    monkeypatch.setattr("builtins.open", forge)
    first = plan_chunks([(0.0, 300.0)], 300.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    second = plan_chunks([(0.0, 300.0)], 300.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert [(c.index, c.start, c.end) for c in first] == [(c.index, c.start, c.end) for c in second]
    assert list(tmp_path.iterdir()) == [], "规划器不写文件"


def test_plan_chunk_plan_derived_budget_values() -> None:
    """``ChunkPlan`` 的派生值就是规则卡的公式（`RULE-011` 的机制）。"""
    from transcript_reimagined.ingest.plan import ChunkPlan

    default = ChunkPlan()
    assert (default.min_s, default.max_s, default.overlap_s) == (30.0, 120.0, 0.5)
    assert default.overlap == 0.5
    assert default.half == 0.25
    assert default.inner == 119.5  # 规则卡：内预算 = 120 - 0.5
    assert default.target == 30.0  # 规则卡：target = min(30.0, 119.5)


def test_plan_chunk_plan_rejects_illegal_budgets_at_construction() -> None:
    """非法预算在**构造时**就抛 ``ValueError``，而不是等到规划时才发现。"""
    from transcript_reimagined.ingest.plan import ChunkPlan

    with pytest.raises(ValueError, match="切片参数非法"):
        ChunkPlan(min_s=0.0)
    with pytest.raises(ValueError, match="切片参数非法"):
        ChunkPlan(min_s=200.0, max_s=120.0)


def test_plan_chunk_plan_treats_negative_overlap_as_zero() -> None:
    """负重叠按 0 处理：否则 ``inner > max_s``，长度不变量会被静默破坏。

    一行性质断言：对任意 ``overlap_s``（含负数），``inner <= max_s`` 必须成立。
    """
    from transcript_reimagined.ingest.plan import ChunkPlan

    for overlap_s in (-5.0, -0.5, 0.0, 0.5, 3.0, 119.0):
        budget = ChunkPlan(overlap_s=overlap_s)
        assert budget.inner <= budget.max_s, f"overlap_s={overlap_s} 时 inner 超出了 max_s"
    negative = ChunkPlan(overlap_s=-5.0)
    assert negative.overlap == 0.0
    assert negative.inner == 120.0


def test_plan_chunks_with_agrees_with_the_keyword_version() -> None:
    """``plan_chunks_with`` 是纯转发 —— 两条调用路径必须给一模一样的计划。"""
    from transcript_reimagined.ingest.chunking import plan_chunks, plan_chunks_with
    from transcript_reimagined.ingest.plan import ChunkPlan

    spans = [(0.0, 100.0), (101.2, 400.0)]
    budget = ChunkPlan(min_s=30.0, max_s=120.0, overlap_s=0.5)
    via_plan = plan_chunks_with(spans, 400.0, budget)
    via_keywords = plan_chunks(spans, 400.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert [(c.index, c.start, c.end) for c in via_plan] == [
        (c.index, c.start, c.end) for c in via_keywords
    ]


def test_phase_three_modules_are_implemented_not_stubs() -> None:
    """Phase 3 的模块已落地：坏输入要给出明确的 InputError，而不是 NotImplementedError。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio, vad

    with pytest.raises(InputError, match="不存在"):
        audio.probe("/definitely/missing.wav")
    assert vad.merge_gaps([(0.0, 1.0)], max_gap_s=0.4) == [(0.0, 1.0)]


def test_public_api_is_exactly_what_the_readme_documents() -> None:
    """包根导出全部已实现能力（Phase 3 之后 audio / vad 也在其中）。"""
    import transcript_reimagined.ingest as ingest

    assert set(ingest.__all__) == {
        "__version__",
        "ChunkPlan",
        "MIN_GAP_FOR_CUT_S",
        "MIN_INNER_S",
        "plan_chunks",
        "plan_chunks_with",
        "probe",
        "require_ffmpeg",
        "verify",
        "to_wav16k",
        "to_mp3_64k",
        "cut",
        "speech_spans",
        "merge_gaps",
    }
