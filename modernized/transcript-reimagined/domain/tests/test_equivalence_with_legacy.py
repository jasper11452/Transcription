"""等价性证据：本包与 legacy 的 `models.py` / `errors.py` 在相同输入下逐字节一致。

`MODERNIZATION_BRIEF.md` 的 Phase 1 exit criteria 要求「一组输入下新旧实现输出逐字节
一致」。这里把那条要求变成**可执行**的：不信「看起来一样」，直接跑差分。

读 legacy 是**只读**的（`legacy/transcript/` 全程冻结不改）—— 本文件不写入任何东西。
为了不把重建版绑死在旧树的路径上，找不到 legacy 时**整文件跳过**：
本包的 87 个用例仍然独立成立。

legacy 模块用 `importlib` 按**文件路径**加载，且用私有模块名 —— 绝不能
`import transcript.models`：本仓 `.venv` 里装着的遗留包会把它接走，
那会让「等价性」变成同义反复（自己跟自己比）。
"""

from __future__ import annotations

import dataclasses
import importlib.util
import itertools
import os
import sys
from pathlib import Path

import pytest

from transcript_reimagined.domain import classify_http, fmt_timestamp
from transcript_reimagined.domain import models as new_models

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

pytestmark = pytest.mark.skipif(
    LEGACY_SRC is None,
    reason="找不到 legacy/transcript/src/transcript（可用 TRANSCRIPT_LEGACY_SRC 指定）；"
    "本包的验收测试不依赖旧树",
)


def _load_by_path(module_name: str, path: Path):
    """按文件路径加载一个模块，绕开 `.venv` 里同名的遗留包。"""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def legacy():
    assert LEGACY_SRC is not None
    return {
        "models": _load_by_path("_legacy_transcript_models", LEGACY_SRC / "models.py"),
        "errors": _load_by_path("_legacy_transcript_errors", LEGACY_SRC / "errors.py"),
    }


def test_fmt_timestamp_is_byte_identical_to_legacy(legacy) -> None:
    """`RULE-025` 的差分：毫秒扫 0..4000 步进 1，含进位边界与负数。"""
    values = [-3600.0, -59.9996, -1.0, -0.0, 0.0, 1e-9]
    values += [i / 1000 for i in range(0, 4000)]
    values += [0.0005, 0.0015, 0.0025, 0.0035, 59.9994, 59.9995, 59.9996, 59.9999]
    values += [60.0, 119.99995, 3599.9999, 359999.9996, 12345.6789]

    mismatches = [
        (value, sep, legacy["models"].fmt_timestamp(value, sep=sep), fmt_timestamp(value, sep=sep))
        for value, sep in itertools.product(values, (",", ".", ":"))
        if legacy["models"].fmt_timestamp(value, sep=sep) != fmt_timestamp(value, sep=sep)
    ]
    assert mismatches == [], mismatches[:5]
    assert len(values) * 3 > 10_000  # 差分确实跑了一大片，不是 3 个样例


def test_classify_http_is_byte_identical_to_legacy(legacy) -> None:
    """`RULE-059` 的差分：199..604 全状态 × 各种 body（含非 JSON、空 code）。"""
    bodies = [
        "",
        "not json",
        '{"code":"Throttling"}',
        '{"code": "Throttling"}',
        '{"code":"InvalidParameter","message":"bad format"}',
        '{"code":"InvalidApiKey"}',
        '{"message":"no code here"}',
        '{"code":""}',
        '{"code":null}',
        '{\n  "code":"QuotaExceeded"}',
    ]
    mismatches = []
    for status, body in itertools.product(range(199, 605), bodies):
        old = legacy["errors"].classify_http(status, body)
        new = classify_http(status, body)
        for attr in ("status", "code", "recoverable"):
            if getattr(old, attr, None) != getattr(new, attr, None):
                mismatches.append(
                    (attr, status, body, getattr(old, attr, None), getattr(new, attr, None))
                )
        if (type(old).__name__, str(old)) != (type(new).__name__, str(new)):
            mismatches.append(("type/message", status, body, type(old).__name__, str(old)))
    assert mismatches == [], mismatches[:5]


@pytest.mark.parametrize("name", ["Word", "Segment", "Chunk", "TranscriptResult", "AudioInfo"])
def test_dataclass_shape_matches_legacy(legacy, name: str) -> None:
    """字段名、类型标注、默认值、frozen 与「公开方法集合」必须一一对应。"""
    old = getattr(legacy["models"], name)
    new = getattr(new_models, name)

    def shape(cls):
        return (
            [
                (f.name, f.type, repr(f.default), repr(f.default_factory))
                for f in dataclasses.fields(cls)
            ],
            cls.__dataclass_params__.frozen,
        )

    def surface(cls):
        return sorted(k for k in vars(cls) if not k.startswith("__"))

    assert shape(old) == shape(new)
    assert surface(old) == surface(new)


def test_shifted_and_public_signatures_match_legacy(legacy) -> None:
    """`shifted()` 的逐字节输出（含 legacy 丢 speaker 的行为）与函数签名。"""
    old_seg = legacy["models"].Segment(
        0.0, 1.0, "t", [legacy["models"].Word("a", 0.0, 0.5)], speaker="speaker_2"
    )
    new_seg = new_models.Segment(
        0.0, 1.0, "t", [new_models.Word("a", 0.0, 0.5)], speaker="speaker_2"
    )
    assert dataclasses.asdict(old_seg.shifted(5.0)) == dataclasses.asdict(new_seg.shifted(5.0))
    # 两边都丢 speaker —— 保留 legacy 行为，不是重建版引入的偏差
    assert old_seg.shifted(5.0).speaker is None and new_seg.shifted(5.0).speaker is None

    old_res = legacy["models"].TranscriptResult(
        "t", [legacy["models"].Segment(0.0, 1.0, "x", speaker="s")], "zh", 1.0, 0.1, "e", True
    )
    new_res = new_models.TranscriptResult(
        "t", [new_models.Segment(0.0, 1.0, "x", speaker="s")], "zh", 1.0, 0.1, "e", True
    )
    assert dataclasses.asdict(old_res.shifted(9.0)) == dataclasses.asdict(new_res.shifted(9.0))

    import inspect

    assert inspect.signature(legacy["models"].fmt_timestamp) == inspect.signature(fmt_timestamp)
    assert inspect.signature(legacy["errors"].classify_http) == inspect.signature(classify_http)
