"""等价性证据：本包与 legacy 的 ``chunking.py`` 在相同输入下给出逐字节一致的切片计划。

``MODERNIZATION_BRIEF.md`` 的 Phase 1 exit criteria 要求「一组输入下新旧实现输出逐字节
一致」，并点名了 ``chunking.py:37-93`` 的分片预算与不变量。这里把那条要求变成**可执行**的：
不信「看起来一样」，直接跑差分。

读 legacy 是**只读**的（``legacy/transcript/`` 全程冻结不改）—— 本文件不写任何东西。
找不到 legacy 时整个文件跳过：本包自己的验收测试（``test_rule_011`` / ``test_rule_012``）
仍然独立成立。

legacy 模块用 ``importlib`` 按**文件路径**加载，且用私有模块名 —— 绝不能
``import transcript.chunking``：本仓 ``.venv`` 里装着的遗留包会把它接走，
那会让「等价性」变成同义反复（自己跟自己比）。
"""

from __future__ import annotations

import importlib.util
import os
import random
import sys
from pathlib import Path
from types import ModuleType

import pytest

from transcript_reimagined.ingest.chunking import MIN_GAP_FOR_CUT_S, MIN_INNER_S, plan_chunks

REPO_MARKERS = ("modernized", "analysis", "legacy")


def _find_legacy_src() -> Path | None:
    override = os.environ.get("TRANSCRIPT_LEGACY_SRC")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_dir() else None
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "legacy" / "transcript" / "src" / "transcript"
        if candidate.is_dir():
            return candidate
        if parent.name in REPO_MARKERS and (parent / ".git").exists():
            break
    return None


LEGACY_SRC = _find_legacy_src()
LEGACY_CHUNKING_PATH = (LEGACY_SRC / "chunking.py") if LEGACY_SRC is not None else None

pytestmark = [
    pytest.mark.rule("RULE-011"),
    pytest.mark.skipif(
        LEGACY_CHUNKING_PATH is None or not LEGACY_CHUNKING_PATH.is_file(),
        reason="找不到 legacy/transcript/src/transcript/chunking.py"
        "（可用 TRANSCRIPT_LEGACY_SRC 指定）；本包的验收测试不依赖旧树",
    ),
]


def _stub_legacy_package(parent: Path) -> None:
    """把 legacy 目录注册成私有顶层包，让 ``from .models import Chunk`` 能解析。

    用私有名 ``_legacy_transcript_chunking``：绝不能让遗留包占用 ``transcript``
    （见文件头说明）。
    """
    package_name = "_legacy_transcript_chunking"
    spec = importlib.util.spec_from_file_location(
        package_name,
        parent / "__init__.py",
        submodule_search_locations=[str(parent)],
    )
    assert spec and spec.loader
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


def _load_legacy_chunking() -> ModuleType:
    assert LEGACY_CHUNKING_PATH is not None
    parent = LEGACY_CHUNKING_PATH.parent
    if "_legacy_transcript_chunking" not in sys.modules:
        _stub_legacy_package(parent)
    spec = importlib.util.spec_from_file_location(
        "_legacy_transcript_chunking.chunking", LEGACY_CHUNKING_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_legacy_transcript_chunking.chunking"] = module
    spec.loader.exec_module(module)
    return module


#: 覆盖面：判据原文的负载 + 规则卡列出的每一条边界情形。
#: 未排序区间、退化区间、越界区间、无区间、恰好装得下、恰好等于 target、
#: 引擎上限压小 max_s、间隙恰好 0.15、间隙略小于 0.15、间隙中点超出预算、
#: 重复区间（不去重会影响 acc 与切点）。
CASES: list[tuple[list[tuple[float, float]], float, float, float, float]] = [
    # (spans, duration, min_s, max_s, overlap_s)
    ([(0.0, 60.0), (61.2, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 100.0), (101.2, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 400.0)], 400.0, 30.0, 120.0, 0.5),
    ([], 400.0, 30.0, 120.0, 0.0),
    ([], 300.0, 30.0, 120.0, 0.5),
    ([], 20.0, 30.0, 120.0, 0.5),
    ([(0.0, 5.0)], 5.0, 30.0, 120.0, 0.0),
    ([(0.0, 30.0)], 30.0, 30.0, 120.0, 0.5),
    ([(0.0, 30.5)], 30.5, 30.0, 120.0, 0.5),
    ([(0.0, 320.0)], 320.0, 30.0, 300.0, 0.5),
    ([(0.0, 200.0), (201.0, 400.0)], 400.0, 30.0, 120.0, 0.5),
    ([(0.0, 0.2), (0.5, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 0.2), (0.5, 400.0)], 400.0, 30.0, 120.0, 0.5),
    ([(0.0, 50.0), (50.15, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 50.0), (50.149, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 100.0), (250.0, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 20.0), (20.5, 40.0), (200.3, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 20.0), (20.3, 40.0), (40.3, 60.0), (60.3, 80.0)], 80.0, 30.0, 120.0, 0.0),
    ([(70.0, 80.0), (0.0, 10.0), (40.0, 50.0)], 300.0, 30.0, 120.0, 0.0),
    ([(0.0, 0.0), (10.0, 5.0), (100.0, 200.0)], 300.0, 30.0, 120.0, 0.0),
    ([(-50.0, 10.0), (20.0, 500.0)], 300.0, 30.0, 120.0, 0.0),
    ([(0.0, 100.0), (0.0, 100.0), (100.3, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 25.0), (0.0, 25.0), (26.2, 50.0), (51.4, 400.0)], 460.0, 30.0, 120.0, 0.0),
    ([(0.0, 30.0), (31.2, 60.0), (62.4, 400.0)], 400.0, 30.0, 120.0, 0.0),
    ([(0.0, 5.0), (6.2, 400.0)], 400.0, 5.0, 5.0, 0.0),
    ([(float(i * 10), float(i * 10) + 9) for i in range(40)], 400.0, 30.0, 120.0, 0.5),
    ([(float(i * 10), float(i * 10) + 9) for i in range(120)], 1200.0, 30.0, 120.0, 0.5),
    ([(0.0, 400.0), (402.0, 800.0), (802.0, 1200.0)], 1200.0, 30.0, 120.0, 0.5),
    ([(0.0, 10.0)], -3.0, 30.0, 120.0, 0.5),
    ([], 0.0, 30.0, 120.0, 0.5),
    ([(0.0, 10.0)], 100.0, 90.0, 90.0, 0.5),
]


def _shape(chunks) -> list[tuple[int, float, float]]:
    return [(c.index, round(c.start, 9), round(c.end, 9)) for c in chunks]


@pytest.mark.parametrize(
    ("spans", "duration", "min_s", "max_s", "overlap_s"),
    CASES,
    ids=[
        "midpoint-gap-0",
        "midpoint-gap-0-mid-timeline",
        "continuous-overlap-0",
        "continuous-overlap-0.5",
        "no-spans-400",
        "no-spans-300",
        "no-spans-short",
        "fits-in-one-chunk",
        "duration-equals-target",
        "duration-just-over-target",
        "engine-cap-300",
        "regression-200-1-200",
        "clamp-low-overlap-0",
        "clamp-low-overlap-0.5",
        "gap-exactly-threshold",
        "gap-just-below-threshold",
        "gap-midpoint-over-budget",
        "best-candidate-before-break",
        "pauses-with-one-chunk-fitting",
        "unsorted-spans",
        "degenerate-spans-dropped",
        "out-of-range-spans-clamped",
        "duplicate-spans-count-twice",
        "duplicate-spans-change-first-cut",
        "early-stop-at-target",
        "min-s-larger-than-inner",
        "tiled-40-spans",
        "20min-many-spans",
        "20min-three-blocks",
        "negative-duration",
        "zero-duration",
        "min-equals-max-90",
    ],
)
def test_equivalence_with_legacy_plan_is_byte_identical(
    spans, duration, min_s, max_s, overlap_s
) -> None:
    """同一组输入 → 新旧实现的 ``(index, start, end)`` 序列完全一致。"""
    legacy = _load_legacy_chunking()
    ours = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    theirs = legacy.plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    assert _shape(ours) == _shape(theirs), f"spans={spans} duration={duration}"


@pytest.mark.parametrize(
    ("min_s", "max_s"),
    [(0.0, 120.0), (-1.0, 120.0), (200.0, 120.0), (30.0, 29.0), (0.0, 0.0)],
)
def test_equivalence_with_legacy_raises_the_same_value_error(min_s: float, max_s: float) -> None:
    """非法预算两版都抛 ``ValueError``，且消息文本一致（调用方可能匹配它）。"""
    legacy = _load_legacy_chunking()
    with pytest.raises(ValueError) as ours:
        plan_chunks([(0.0, 10.0)], 100.0, min_s=min_s, max_s=max_s)
    with pytest.raises(ValueError) as theirs:
        legacy.plan_chunks([(0.0, 10.0)], 100.0, min_s=min_s, max_s=max_s)
    assert str(ours.value) == str(theirs.value)


def test_equivalence_with_legacy_duration_check_ordering_matches() -> None:
    """``duration <= 0`` 先于参数校验返回 —— 两版的检查顺序必须一致。"""
    legacy = _load_legacy_chunking()
    ours = plan_chunks([], 0.0, min_s=0.0, max_s=0.0)
    theirs = legacy.plan_chunks([], 0.0, min_s=0.0, max_s=0.0)
    assert ours == [] and theirs == []


def test_equivalence_with_legacy_module_constants_match() -> None:
    """两个门控常量也必须一致：``MIN_GAP_FOR_CUT_S`` 与 ``MIN_INNER_S``。"""
    legacy = _load_legacy_chunking()
    assert legacy.MIN_GAP_FOR_CUT_S == MIN_GAP_FOR_CUT_S == 0.15
    assert legacy.MIN_INNER_S == MIN_INNER_S == 1.0


def test_equivalence_with_legacy_randomized_sweep() -> None:
    """随机扫描：形状差异一旦出现就能被抓到（种子固定，可复现）。

    legacy 的「所有片段被过滤掉 → 整段一片」这条末路兜底在真实的
    ``min_s/max_s`` 量级下不可达，只有把上限压到 1 秒量级才会触发；
    随机扫描覆盖这个角落，避免它成为「只在文档里存在」的分支。
    """
    legacy = _load_legacy_chunking()
    rng = random.Random(20261017)
    for _ in range(400):
        duration = rng.choice([rng.uniform(0.0, 5.0), rng.uniform(0.0, 2000.0)])
        min_s = rng.choice([0.001, 0.01, 0.1, 1.0, 5.0, 30.0, 120.0])
        max_s = rng.choice([min_s, min_s * 2, min_s * 10, 1.0, 5.0, 120.0, 300.0])
        if max_s < min_s:
            continue
        overlap_s = rng.choice([0.0, 0.001, 0.5, 3.0, 50.0, 200.0])
        spans = []
        for _ in range(rng.randint(0, 4)):
            start = rng.uniform(-10.0, duration + 10.0)
            spans.append((start, start + rng.uniform(-10.0, 200.0)))
        ours = _shape(plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s))
        theirs = _shape(
            legacy.plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
        )
        assert ours == theirs, (
            f"spans={spans} duration={duration} min_s={min_s} max_s={max_s} overlap_s={overlap_s}"
        )


def test_equivalence_with_legacy_invariants_hold_on_both_sides() -> None:
    """不变量在**两版**上都成立：片长 <= max_s、按序覆盖、首 0 末 duration。"""
    legacy = _load_legacy_chunking()
    for spans, duration, min_s, max_s, overlap_s in CASES:
        if duration <= 0:
            continue
        ours = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
        theirs = legacy.plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
        for chunks in (ours, theirs):
            assert chunks
            assert chunks[0].start == 0.0
            assert chunks[-1].end == duration
            assert all(c.duration <= max_s + 1e-6 for c in chunks)
            for prev, cur in zip(chunks, chunks[1:], strict=False):
                assert cur.start <= prev.end
