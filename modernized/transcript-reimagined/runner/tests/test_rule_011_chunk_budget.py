"""``RULE-011`` —— 分片预算与长度不变量。

判据来自 ``AI_NATIVE_SPEC.md`` §5.2：20 分钟录音、``chunk_min_s=30`` ``chunk_max_s=120``
``chunk_overlap_s=0.5``（内预算 = 119.5s）→ 每片 ``duration <= 120.0s``；分片按序覆盖
``[0, duration]`` 且相邻重叠 0.5s；首片从 0.0 起、末片到 ``duration`` 止。

这些都是可执行断言（不是注释）：切片错了，后面全错。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.ingest.chunking import plan_chunks

#: 判据里的 20 分钟录音：四段语音 + 三段 1.0–2.0s 静音
SPANS_20MIN = [(0.0, 100.0), (101.2, 400.0), (402.0, 900.0), (901.0, 1200.0)]
DURATION_20MIN = 1200.0
MIN_S, MAX_S, OVERLAP_S = 30.0, 120.0, 0.5

#: 几种代表性负载：有静音的、完全连续的、没有语音区间的、以及百炼的 300s 硬限
CASES = [
    (SPANS_20MIN, DURATION_20MIN, MIN_S, MAX_S, OVERLAP_S),
    ([(0.0, 400.0)], 400.0, MIN_S, MAX_S, OVERLAP_S),
    ([], 700.0, MIN_S, MAX_S, OVERLAP_S),
    ([(0.0, 320.0)], 320.0, MIN_S, 300.0, OVERLAP_S),
    ([(float(i * 10), float(i * 10) + 9) for i in range(40)], 400.0, MIN_S, MAX_S, OVERLAP_S),
]


@pytest.mark.parametrize(("spans", "duration", "min_s", "max_s", "overlap_s"), CASES)
def test_rule_011_every_chunk_within_max_s(spans, duration, min_s, max_s, overlap_s):
    """RULE-011：物理不变量 —— 含外扩重叠之后，每片仍不超过 max_s。

    在线引擎有单次硬限（百炼 300s），片长了会被上游直接拒。这条是唯一的保障。
    """
    chunks = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    assert chunks, f"不能切出空计划：spans={spans} duration={duration}"
    for chunk in chunks:
        assert chunk.duration <= max_s + 1e-6, f"{chunk.duration:.2f}s 超过上限 {max_s}s"


@pytest.mark.parametrize(("spans", "duration", "min_s", "max_s", "overlap_s"), CASES)
def test_rule_011_gap_free_ordered_coverage(spans, duration, min_s, max_s, overlap_s):
    """RULE-011：按序覆盖 [0, duration] —— 首片从 0.0 起、末片到 duration 止、不留缝。"""
    chunks = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    assert chunks[0].start == 0.0
    assert chunks[-1].end == duration
    assert [c.index for c in chunks] == list(range(len(chunks)))
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur.start < prev.end, "相邻片必须重叠，不能留缝"
        assert cur.start <= prev.end


def test_rule_011_adjacent_chunks_overlap_by_overlap_s():
    """RULE-011：相邻两片的重叠总量是 overlap_s（不变量成立时是精确的 0.5s）。"""
    chunks = plan_chunks(SPANS_20MIN, DURATION_20MIN, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    overlaps = [
        round(prev.end - cur.start, 6) for prev, cur in zip(chunks, chunks[1:], strict=False)
    ]
    assert overlaps, "这个负载必须切出多片"
    assert all(abs(value - OVERLAP_S) < 1e-6 for value in overlaps), overlaps


def test_rule_011_inner_budget_is_max_minus_overlap():
    """RULE-011 的参数：内预算 = max_s - overlap = 119.5s，target = min(min_s, inner) = 30.0。"""
    from transcript_reimagined.ingest import ChunkPlan

    plan = ChunkPlan(min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    assert plan.inner == pytest.approx(119.5)


def test_rule_011_short_audio_is_a_single_chunk():
    """RULE-011 的快捷分支：duration <= target 时不做切分。"""
    chunks = plan_chunks([], 20.0, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    assert len(chunks) == 1
    assert (chunks[0].start, chunks[0].end) == (0.0, 20.0)


def test_rule_011_non_positive_duration_returns_empty_plan():
    assert plan_chunks([], 0.0, min_s=MIN_S, max_s=MAX_S) == []
    assert plan_chunks([(0.0, 10.0)], -1.0, min_s=MIN_S, max_s=MAX_S) == []


def test_rule_011_illegal_budget_raises_instead_of_planning():
    """参数非法时必须抛错，而不是规划出一个坏计划（宁可失败，不产出坏分片）。"""
    with pytest.raises(ValueError):
        plan_chunks([], 300.0, min_s=0.0, max_s=120.0)
    with pytest.raises(ValueError):
        plan_chunks([], 300.0, min_s=200.0, max_s=120.0)


def test_rule_011_bailian_300s_hard_limit_holds():
    """RULE-011 的关键场景：百炼 300s 硬限下切点也不能越界（回归事故的原始形态）。"""
    chunks = plan_chunks([(0.0, 320.0)], 320.0, min_s=30.0, max_s=300.0, overlap_s=0.5)
    assert max(c.duration for c in chunks) <= 300.0
