"""``RULE-012`` —— 切点优先落静音（``transcript_reimagined.ingest.chunking``）。

判据（``AI_NATIVE_SPEC.md`` §5.2 + ``BUSINESS_RULES.md`` 规则卡）：
    给定 1.2s 静音、游标 60.0s、``target = min(30.0, 119.5) = 30.0s``
    当  规划器寻找下一个切点
    则  切点取 >= 0.15s 静音间隙的**中点**且仍 ``<= cursor + inner``；
        无可用间隙（连续语音）时切在 ``cursor + inner``；
        切点被夹在 ``>= cursor + 1.0s`` 且 ``<= duration``

规则卡列的边界情形（本文件逐条断言）：
中点超出预算时中断扫描、用**目前最好**的候选 · 区间先排序并夹进 ``[0, duration]`` ·
``end <= start`` 的区间丢掉 · 游标跳过所有在新切点处结束的区间（不重复考虑）·
两个常量 ``MIN_GAP_FOR_CUT_S = 0.15`` 与 ``MIN_INNER_S = 1.0`` 钉死在契约里。

所有用例都用 ``overlap_s=0``：这样片边界**就是**切点，断言不用反推外扩。
末片的 ``end`` 恒等于 ``duration``（那是覆盖要求，不是切点），所以本文件的
``cuts()`` 助手只取中间那些边界。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.ingest.chunking import MIN_GAP_FOR_CUT_S, plan_chunks
from transcript_reimagined.ingest.plan import MIN_GAP_FOR_CUT_S as PLAN_MIN_GAP_FOR_CUT_S
from transcript_reimagined.ingest.plan import MIN_INNER_S, ChunkPlan

pytestmark = pytest.mark.rule("RULE-012")

#: 切点常量属于契约的一部分 —— 放宽 0.15 会把句间停顿都变成切点，
#: 放宽 MIN_INNER_S 会让 clamp 失去意义。两个导入路径必须是同一个值。
MIN_GAP_S = 0.15
MIN_INNER = 1.0

#: 用二进制可精确表示的间隙值做边界断言：字面量 ``50.15`` 的浮点差是
#: ``0.14999999999999858``，**小于** 0.15 —— 用它测「恰好等于阈值」会测到反例。
#: ``0.15625`` 与 ``0.125`` 都能被二进制精确表示。
GAP_ABOVE_THRESHOLD = 50.15625  # 间隙 0.15625 >= 0.15 → 可用
GAP_BELOW_THRESHOLD = 50.125  # 间隙 0.125 < 0.15 → 不可用


def cuts(spans, duration, **kwargs) -> list[float]:
    """返回**切点**（中间那些片边界）。

    ``overlap_s=0`` 时片边界 = 切点；末片的 ``end`` 恒为 ``duration``，
    那是覆盖要求而不是切点，所以去掉。
    """
    default = {"min_s": 30.0, "max_s": 120.0, "overlap_s": 0.0}
    default.update(kwargs)
    chunks = plan_chunks(spans, duration, **default)
    return [chunk.end for chunk in chunks[:-1]]


def test_rule_012_constants_are_part_of_the_contract() -> None:
    """两个门控常量与规则卡一致，且两个导入路径指向同一个值。"""
    assert MIN_GAP_FOR_CUT_S == MIN_GAP_S
    assert PLAN_MIN_GAP_FOR_CUT_S == MIN_GAP_S
    assert MIN_INNER_S == MIN_INNER


def test_rule_012_cut_lands_on_the_midpoint_of_a_1_2s_silence() -> None:
    """判据原文：1.2s 静音（60.0 → 61.2）→ 切点取中点 60.6。"""
    assert cuts([(0.0, 60.0), (61.2, 400.0)], 400.0)[0] == 60.6


def test_rule_012_midpoint_of_a_later_silence_is_used_when_it_is_reached_first() -> None:
    """同一个机制在时间轴中段：100.0 → 101.2 的静音 → 切点 100.6。"""
    assert cuts([(0.0, 100.0), (101.2, 400.0)], 400.0)[0] == 100.6


def test_rule_012_gap_above_min_gap_is_accepted_and_cut_at_its_midpoint() -> None:
    """间隙 0.15625s >= 0.15s → 可用，切在中点 50.078125。"""
    assert cuts([(0.0, 50.0), (GAP_ABOVE_THRESHOLD, 400.0)], 400.0)[0] == 50.078125


def test_rule_012_gap_below_min_gap_is_not_a_cut_point() -> None:
    """间隙 0.125s < 0.15s → 不是切点，退化成硬切 ``cursor + inner``。"""
    assert cuts([(0.0, 50.0), (GAP_BELOW_THRESHOLD, 400.0)], 400.0)[0] == 120.0


def test_rule_012_no_usable_gap_falls_back_to_cursor_plus_inner() -> None:
    """连续语音（没有间隙）→ 硬切在 ``cursor + inner``（120）。"""
    assert cuts([(0.0, 400.0)], 400.0) == [120.0, 240.0, 360.0]


def test_rule_012_no_spans_at_all_is_treated_as_continuous_speech() -> None:
    """VAD 什么都没检出 → 没有间隙可用 → 按 ``inner`` 硬切，不能整段一片。"""
    assert cuts([], 400.0) == [120.0, 240.0, 360.0]


def test_rule_012_gap_whose_midpoint_exceeds_the_budget_is_skipped() -> None:
    """间隙中点超出 ``cursor + inner`` 时不用它。

    间隙在 100.0 → 250.0，中点是 175.0 > cursor + inner = 120.0，
    所以这一轮没有可用候选，只能硬切在 120.0。
    """
    assert cuts([(0.0, 100.0), (250.0, 400.0)], 400.0)[0] == 120.0


def test_rule_012_best_candidate_found_so_far_is_used_when_the_scan_breaks() -> None:
    """有候选、且后面还有更远的静音时：断在更远者，用**前面**那个候选。

    区间 ``[(0, 20), (20.5, 40), (200.3, 400)]``：第一个间隙中点 20.25 可用；
    越过它继续扫到 200 附近的间隙，其中点 120.15 > cursor + inner = 120.0 → 中断，
    最终切在 20.25，而不是硬切 120.0。
    """
    spans = [(0.0, 20.0), (20.5, 40.0), (200.3, 400.0)]
    assert cuts(spans, 400.0) == [20.25, 120.15, 240.15, 360.15]


def test_rule_012_early_stop_once_enough_speech_is_accumulated() -> None:
    """攒够 ``target``（= min(min_s, inner) = 30.0）且落在静音处就用它，不再往后找。"""
    spans = [(0.0, 30.0), (31.2, 60.0), (62.4, 400.0)]
    # 第一个间隙（30.0→31.2）中点 30.6：此时 acc = 30.0 >= target，提前停下
    assert cuts(spans, 400.0)[0] == 30.6


def test_rule_012_target_is_capped_by_inner_when_min_s_is_larger() -> None:
    """``target = min(min_s, inner)``：``min_s`` 大于 ``inner`` 时按 ``inner`` 提前停。"""
    budget = ChunkPlan(min_s=30.0, max_s=40.0, overlap_s=15.0)
    assert (budget.inner, budget.target) == (25.0, 25.0)

    spans = [(0.0, 25.0), (26.2, 400.0)]
    cuts_with_capped_target = cuts(spans, 400.0, min_s=30.0, max_s=40.0, overlap_s=15.0)
    # 切点 = cursor + inner = 25.0；外扩 half=7.5 之后首片收在 32.5
    assert cuts_with_capped_target[0] == 32.5
    assert cuts_with_capped_target[1] == 57.5


def test_rule_012_cut_is_clamped_to_at_least_cursor_plus_min_inner() -> None:
    """切点夹在 ``>= cursor + MIN_INNER_S``：游标后 1.0s 内不能切。

    第一个间隙在 0.2 → 0.5（中点 0.35 < 0 + 1.0），被 clamp 到 1.0。
    """
    assert cuts([(0.0, 0.2), (0.5, 400.0)], 400.0)[0] == 1.0


def test_rule_012_cut_is_clamped_to_at_most_duration() -> None:
    """切点夹在 ``<= duration``：最后一轮不能切到录音之外。"""
    chunks = plan_chunks([(0.0, 400.0)], 400.0, min_s=30.0, max_s=120.0, overlap_s=0.0)
    assert all(chunk.end <= 400.0 for chunk in chunks)
    assert chunks[-1].end == 400.0


def test_rule_012_pauses_do_not_create_cuts_when_one_chunk_fits() -> None:
    """0.3s 停顿 >= 0.15s，本来够格做切点；但 80s 在 120s 上限下整段一片。

    也就是说「句间停顿变切点」这件事不会发生 —— **预算先决定不切**，
    间隙门控只在真的需要切的时候起作用。
    """
    spans = [(0.0, 20.0), (20.3, 40.0), (40.3, 60.0), (60.3, 80.0)]
    assert cuts(spans, 80.0) == []


def test_rule_012_spans_are_sorted_before_scanning() -> None:
    """区间先按起点排序：乱序输入不能让扫描错位。"""
    assert cuts([(70.0, 80.0), (0.0, 10.0), (40.0, 50.0)], 300.0) == [60.0, 180.0]


def test_rule_012_spans_are_clamped_into_the_recording() -> None:
    """越界区间被夹进 ``[0, duration]``：``(-50, 10)`` → ``(0, 10)``，间隙中点 15.0。"""
    assert cuts([(-50.0, 10.0), (20.0, 500.0)], 300.0)[0] == 15.0


def test_rule_012_degenerate_spans_are_dropped() -> None:
    """``end <= start`` 的区间不参与扫描 —— 它们造不出间隙，也不该抬高 ``acc``。"""
    with_degenerate = cuts([(0.0, 0.0), (10.0, 5.0), (100.0, 200.0)], 300.0)
    without = cuts([(100.0, 200.0)], 300.0)
    assert with_degenerate == without


def test_rule_012_spans_ending_at_or_before_the_new_cut_are_skipped() -> None:
    """游标推进后跳过所有已在切点处结束的区间，不让同一段被考虑两次。

    三段长语音、每段 100s、间隔 0.3s：切点必须一路前移，不会反复落在同一个间隙。
    """
    spans = [(0.0, 100.0), (100.3, 200.0), (200.3, 300.0)]
    positions = cuts(spans, 300.0)
    assert positions == [100.15, 200.15]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions), "切点不能原地踏步"


def test_rule_012_the_criterion_scenario_from_the_rule_card() -> None:
    """把判据原文的参数一次摆出来：cursor 60.0、1.2s 间隙、inner 119.5、target 30.0。

    这条只是把前面几条的输入对齐到规则卡的字面值，避免「判据说到了但没测」。
    """
    inner = 120.0 - 0.5
    target = min(30.0, inner)
    assert (inner, target) == (119.5, 30.0)

    # cursor=60.0 处在第一段语音结束处；下一段从 61.2 起（1.2s 静音）
    plan = plan_chunks([(0.0, 60.0), (61.2, 400.0)], 400.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    # overlap=0.5 → half=0.25，切点 60.6 外扩成片边界 60.85 / 60.35
    assert plan[0].end == pytest.approx(60.85), "切点 60.6 + half 0.25"
    assert plan[1].start == pytest.approx(60.35), "切点 60.6 - half 0.25"
    assert plan[1].end == pytest.approx(180.35)
    assert all(chunk.duration <= 120.0 + 1e-6 for chunk in plan)


def test_rule_012_cut_never_lands_inside_speech_when_a_gap_is_usable() -> None:
    """性质断言：只要存在可用间隙，切点就落在某个间隙**内部**（不在语音段里）。"""
    spans = [(0.0, 100.0), (102.0, 200.0), (202.0, 300.0)]
    gaps = [(100.0, 102.0), (200.0, 202.0)]
    endpoints = cuts(spans, 300.0)
    for cut in endpoints:
        assert any(start < cut < end for start, end in gaps), f"切点 {cut} 不在静音间隙内"
