"""``RULE-012`` —— 切点优先落静音。

判据来自 ``AI_NATIVE_SPEC.md`` §5.2：语音区间间有静音间隙时，切点取间隙中点且仍
``<= cursor + inner``；无可用间隙则切在 ``cursor + inner``；切点夹在 ``>= cursor + 1.0s``
且 ``<= duration``。

「切点」在计划里表现为相邻两片原始边界的重合点（每片左右各外扩 overlap/2，
因此 ``(prev.end + cur.start) / 2`` 正是被选中的切点）。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.ingest.chunking import MIN_GAP_FOR_CUT_S, MIN_INNER_S, plan_chunks

DURATION = 300.0
MIN_S, MAX_S, OVERLAP_S = 30.0, 120.0, 0.5
INNER = MAX_S - OVERLAP_S  # 119.5


def cuts_of(chunks) -> list[float]:
    """从切片计划反推出被选中的切点。"""
    return [
        round((prev.end + cur.start) / 2, 6) for prev, cur in zip(chunks, chunks[1:], strict=False)
    ]


def test_rule_012_cut_lands_on_the_midpoint_of_the_silence_gap():
    """1.2s 静音间隙 → 切点落在间隙中点（60.0–61.2 之间 → 60.6）。"""
    chunks = plan_chunks(
        [(0.0, 60.0), (61.2, DURATION)], DURATION, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S
    )
    cuts = cuts_of(chunks)
    assert cuts, "必须有切点"
    assert cuts[0] == pytest.approx(60.6, abs=1e-6), cuts
    assert cuts[0] < 61.2 and cuts[0] > 60.0, "切点必须落在静音间隙内部"


def test_rule_012_gap_narrower_than_the_threshold_is_not_used():
    """间隙小于 MIN_GAP_FOR_CUT_S（0.15s）不值得作为边界 —— 这时按 inner 硬切。"""
    assert MIN_GAP_FOR_CUT_S == 0.15
    # 60.0–60.1 只有 0.1s 静音：不足以当边界，切点必须退化成 cursor + inner
    chunks = plan_chunks(
        [(0.0, 60.0), (60.1, DURATION)], DURATION, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S
    )
    assert cuts_of(chunks)[0] == pytest.approx(INNER, abs=1e-6)


def test_rule_012_continuous_speech_hard_cuts_at_the_inner_budget():
    """连续语音没有可用间隙时，切点固定在 cursor + inner，不能无限累积。"""
    chunks = plan_chunks([(0.0, 400.0)], 400.0, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    assert cuts_of(chunks) == pytest.approx([119.5, 239.0, 358.5], abs=1e-6)


def test_rule_012_a_gap_that_does_not_fit_is_rejected():
    """切点必须仍然 <= cursor + inner：放不下的间隙只能改用当前最好的候选。"""
    # 0–119.0 一段、之后 119.0–120.4 有 1.4s 静音、再长语音。中点 119.7 > cursor + inner?
    # cursor=0 时 inner=119.5，中点 119.7 放不下 → 必须回退到 cursor + inner
    chunks = plan_chunks(
        [(0.0, 119.0), (120.4, 400.0)], 400.0, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S
    )
    first_cut = cuts_of(chunks)[0]
    assert first_cut <= INNER + 1e-6, f"切点 {first_cut} 超过了 cursor + inner = {INNER}"


def test_rule_012_cut_is_clamped_into_the_audio():
    """切点夹在 >= cursor + MIN_INNER_S 且 <= duration：既不会原地踏步，也不会越界。"""
    for spans, duration in (
        ([], 300.0),
        ([(0.0, 300.0)], 300.0),
        ([(0.0, 1.0)], 300.0),
        ([(100.0, 101.0)], 240.0),
    ):
        chunks = plan_chunks(spans, duration, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
        cursor = 0.0
        for cut in [*cuts_of(chunks), duration]:
            assert cut >= cursor + MIN_INNER_S - 1e-6, f"切点 {cut} 距上一个游标 {cursor} 太近"
            assert cut <= duration + 1e-6
            cursor = cut


def test_rule_012_spans_are_clamped_and_sorted_before_use():
    """乱序/越界的语音区间先被夹进 [0, duration] 再排序，切点仍然合法。"""
    chunks = plan_chunks(
        [(200.0, 400.0), (-5.0, 60.0), (61.2, 90.0)],
        DURATION,
        min_s=MIN_S,
        max_s=MAX_S,
        overlap_s=OVERLAP_S,
    )
    cuts = cuts_of(chunks)
    assert cuts and all(0.0 <= cut <= DURATION for cut in cuts)
    assert chunks[-1].end == DURATION
