"""``RULE-011`` —— 分片预算与长度不变量（``transcript_reimagined.ingest.chunking``）。

判据（``AI_NATIVE_SPEC.md`` §5.2 + ``BUSINESS_RULES.md`` 规则卡）：
    给定 20 分钟录音、``min_s=30`` ``max_s=120`` ``overlap_s=0.5``（内预算 = 119.5s）
    当  切片规划给出计划
    则  每片 ``duration <= 120.0s``；分片按序覆盖 ``[0, duration]`` 且相邻重叠 0.5s；
        首片从 0.0 起、末片到 ``duration`` 止

这条不变量是**物理约束**，不是审美问题：在线引擎有单次硬限（百炼 300s），
片长了会被上游直接拒 —— 它是 300s 上限不被击穿的唯一保障。

规则卡列的边界情形（本文件逐条断言）：
``duration <= 0`` 返回空计划 · ``min_s <= 0`` 或 ``max_s < min_s`` 抛 ``ValueError`` ·
所有片段都被过滤掉时退化为整段一片 · ``start`` 只向左扩、``end`` 只向右扩，
计划永不越出 ``[0, duration]``。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.ingest.chunking import plan_chunks

pytestmark = pytest.mark.rule("RULE-011")

#: 判据里的 20 分钟录音：四段语音 + 三段 1.0–2.0s 静音（有可用切点）
SPANS_20MIN = [(0.0, 100.0), (101.2, 400.0), (402.0, 900.0), (901.0, 1200.0)]
DURATION_20MIN = 1200.0
MIN_S, MAX_S, OVERLAP_S = 30.0, 120.0, 0.5

#: 代表性负载：有静音的、完全连续的、没有语音区间的、以及百炼的 300s 硬限。
#: 最后两条是修复前的**实测反例**：两段 200s 语音 + 1s 静音、max_s=120 时
#: 曾切出 200.75s 的片；max_s=300 时曾切出 300.25s，直接超过上游硬限。
CASES = [
    (SPANS_20MIN, DURATION_20MIN, MIN_S, MAX_S, OVERLAP_S),
    ([(0.0, 400.0)], 400.0, MIN_S, MAX_S, OVERLAP_S),
    ([], 700.0, MIN_S, MAX_S, OVERLAP_S),
    ([(0.0, 320.0)], 320.0, MIN_S, 300.0, OVERLAP_S),
    ([(0.0, 200.0), (201.0, 400.0)], 400.0, MIN_S, MAX_S, OVERLAP_S),
    ([(float(i * 10), float(i * 10) + 9) for i in range(40)], 400.0, MIN_S, MAX_S, OVERLAP_S),
]


@pytest.mark.parametrize(("spans", "duration", "min_s", "max_s", "overlap_s"), CASES)
def test_rule_011_every_chunk_within_max_s(spans, duration, min_s, max_s, overlap_s) -> None:
    """含外扩重叠之后，每片仍不超过 max_s —— 上游 300s 硬限的唯一保障。"""
    chunks = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    assert chunks, f"不能切出空计划：spans={spans} duration={duration}"
    for chunk in chunks:
        assert chunk.duration <= max_s + 1e-6, f"{chunk.duration:.2f}s 超过上限 {max_s}s"


@pytest.mark.parametrize(("spans", "duration", "min_s", "max_s", "overlap_s"), CASES)
def test_rule_011_gap_free_ordered_coverage(spans, duration, min_s, max_s, overlap_s) -> None:
    """按序覆盖 ``[0, duration]``：首片从 0.0 起、末片到 duration 止、不留缝。"""
    chunks = plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    assert chunks[0].start == 0.0
    assert chunks[-1].end == duration
    assert [c.index for c in chunks] == list(range(len(chunks)))
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur.start < prev.end, "相邻片必须重叠，否则边界会丢字"


def test_rule_011_the_decision_criterions_20_minute_recording() -> None:
    """判据原文的输入：20 分钟、默认预算 → 每片 <= 120.0s、无缝隙、末片收在 1200s。"""
    chunks = plan_chunks(SPANS_20MIN, DURATION_20MIN, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    assert len(chunks) > 1, "20 分钟在 120s 上限下必须被切开"
    # 浮点表示：切片边界是「119.5 + 0.25」这类加法，结果可能是 120.00000000000003。
    # 不变量是「不超过 max_s」，所以用 1e-6 容差断言，而不是要求二进制精确。
    assert max(c.duration for c in chunks) <= 120.0 + 1e-6
    assert chunks[0].start == 0.0
    assert chunks[-1].end == 1200.0
    assert all(c.start >= 0.0 and c.end <= DURATION_20MIN for c in chunks)


def test_rule_011_adjacent_chunks_overlap_by_exactly_overlap_s() -> None:
    """相邻两片的重叠总量是 overlap_s（不变量成立时精确；这里是 0.5s）。"""
    chunks = plan_chunks(SPANS_20MIN, DURATION_20MIN, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    overlaps = [
        round(prev.end - cur.start, 6) for prev, cur in zip(chunks, chunks[1:], strict=False)
    ]
    assert overlaps, "这个负载必须切出多片"
    assert all(abs(value - OVERLAP_S) < 1e-6 for value in overlaps), overlaps


def test_rule_011_overlap_lives_inside_the_budget_not_outside_it() -> None:
    """重叠算在预算内：``inner = max(MIN_INNER_S, max_s - overlap)``。

    这条是「片长 <= max_s」的**机制**，不是等价的说法 —— 重叠若算在预算外，
    每片就会超出 overlap_s，百炼场景直接击穿 300s。
    """
    chunks = plan_chunks([(0.0, 320.0)], 320.0, min_s=30.0, max_s=300.0, overlap_s=0.5)
    # inner = 299.5，所以首片的内容长度最多 299.5s，外扩 half=0.25 后仍 <= 300
    assert chunks[0].end == 299.75
    assert chunks[0].duration <= 300.0
    assert chunks[-1].end == 320.0


def test_rule_011_duration_at_or_below_the_single_chunk_budget_is_not_split() -> None:
    """装得下就不切 —— 多切一片就是多一次引擎调用（在线就是多花钱）。"""
    no_spans = plan_chunks([], 20.0, min_s=30.0, max_s=120.0)
    assert len(no_spans) == 1
    assert no_spans[0].end == 20.0
    single = plan_chunks([(0.0, 30.0)], 30.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert len(single) == 1, "时长恰好等于 target 时仍是一片"
    assert (single[0].start, single[0].end) == (0.0, 30.0)
    just_over = plan_chunks([(0.0, 30.5)], 30.5, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert len(just_over) == 1, "略超 target 但仍装得进 max_s 时不切"


@pytest.mark.parametrize("bad_min_s", [0.0, -1.0, -0.001])
def test_rule_011_non_positive_min_s_raises_value_error(bad_min_s: float) -> None:
    """``min_s <= 0`` 抛 ``ValueError`` 而不是规划出坏计划。"""
    with pytest.raises(ValueError, match="切片参数非法"):
        plan_chunks([(0.0, 10.0)], 100.0, min_s=bad_min_s, max_s=120.0)


@pytest.mark.parametrize(("min_s", "max_s"), [(200.0, 120.0), (30.0, 29.999), (1.0, 0.0)])
def test_rule_011_max_below_min_raises_value_error(min_s: float, max_s: float) -> None:
    """``max_s < min_s`` 抛 ``ValueError`` —— 参数自相矛盾，不能猜一个赢家。"""
    with pytest.raises(ValueError, match="切片参数非法"):
        plan_chunks([(0.0, 10.0)], 100.0, min_s=min_s, max_s=max_s)


def test_rule_011_non_positive_duration_returns_an_empty_plan() -> None:
    """``duration <= 0`` 返回空计划，**不**抛错、也不给整段一片。"""
    assert plan_chunks([(0.0, 5.0)], 0.0, min_s=30.0, max_s=120.0) == []
    assert plan_chunks([(0.0, 5.0)], -3.0, min_s=30.0, max_s=120.0) == []
    assert plan_chunks([], 0.0, min_s=30.0, max_s=120.0) == []


def test_rule_011_duration_check_runs_before_the_parameter_check() -> None:
    """两个检查的**顺序**是契约的一部分。

    ``duration <= 0`` 先行返回，所以参数同时非法（``min_s=0``）时返回 ``[]``
    而不是抛 ``ValueError``。调换顺序会让这里与 legacy 分道扬镳。
    """
    assert plan_chunks([], 0.0, min_s=0.0, max_s=0.0) == []


def test_rule_011_plan_never_leaves_the_recording() -> None:
    """``start`` 只向左扩、``end`` 只向右扩，且都被夹回 ``[0, duration]``。"""
    chunks = plan_chunks([(0.0, 0.2), (0.5, 400.0)], 400.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert chunks[0].start == 0.0, "首片不从 0 起会让开头丢内容"
    assert all(c.start >= 0.0 for c in chunks)
    assert all(c.end <= 400.0 for c in chunks)
    assert all(c.start < c.end for c in chunks), "零长或负长的片不是片"


def test_rule_011_start_is_only_extended_left_and_end_only_right() -> None:
    """每片左右各外扩 half=overlap/2；首片不左扩、末片不右扩。"""
    chunks = plan_chunks(SPANS_20MIN, DURATION_20MIN, min_s=MIN_S, max_s=MAX_S, overlap_s=OVERLAP_S)
    assert chunks[0].start == 0.0
    assert chunks[-1].end == DURATION_20MIN
    for chunk in chunks[1:-1]:
        assert chunk.end - chunk.start <= MAX_S + 1e-6


def test_rule_011_tiling_by_inner_when_there_are_no_usable_spans() -> None:
    """VAD 什么都没检出时按 inner 硬切，不能整段一片（长音频必须被切开）。"""
    chunks = plan_chunks([], 300.0, min_s=30.0, max_s=120.0, overlap_s=0.5)
    assert len(chunks) > 1
    assert chunks[-1].end == 300.0
    assert all(c.duration <= 120.0 + 1e-6 for c in chunks)


def test_rule_011_effective_engine_cap_is_the_callers_job_via_max_s() -> None:
    """引擎声明的单次上限靠收紧 ``max_s`` 生效（``RULE-014`` 的调用方式）。

    规划器不认识引擎：调用方传 ``min(min_s, engine_max)`` / ``min(max_s, engine_max)``。
    这里钉住「压小 max_s 之后不变量仍然成立」，并钉住为什么调用方必须先压小 min_s
    —— ``min_s > max_s`` 会直接抛错（legacy ``pipeline.py:269-270`` 的注释即此意）。
    """
    engine_max = 5.0
    chunks = plan_chunks([(0.0, 400.0)], 400.0, min_s=engine_max, max_s=engine_max, overlap_s=0.5)
    assert chunks
    assert all(c.duration <= engine_max + 1e-6 for c in chunks)

    with pytest.raises(ValueError):
        plan_chunks([(0.0, 400.0)], 400.0, min_s=90.0, max_s=engine_max, overlap_s=0.5)


def test_rule_011_every_piece_filtered_out_falls_back_to_one_whole_chunk() -> None:
    """所有片段都被过滤掉时退化为整段一片。

    触发条件：``duration > target``（所以走了切分分支），但每个边界区间都短于
    0.01s 被丢弃 —— 只有 ``max_s``/``min_s`` 被压到 1 秒量级时可达。
    """
    chunks = plan_chunks([(-1.0, 10.0)], 0.005, min_s=0.001, max_s=1.0, overlap_s=0.0)
    assert len(chunks) == 1, "「切不出片」和「不切」对调用方是两件不同的事，不能给空计划"
    assert (chunks[0].index, chunks[0].start, chunks[0].end) == (0, 0.0, 0.005)


def test_rule_011_indices_are_sequential_starting_at_zero() -> None:
    """``index`` 是重试与落盘单位 id：必须 0 起、连续、与列表位置一致。"""
    chunks = plan_chunks([(0.0, 300.0)], 300.0, min_s=30.0, max_s=60.0, overlap_s=0.4)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(
    "spans",
    [
        [(70.0, 80.0), (0.0, 10.0), (40.0, 50.0)],  # 未排序
        [(0.0, 0.0), (10.0, 5.0), (100.0, 200.0)],  # 退化（end <= start）与零长
        [(-50.0, 10.0), (20.0, 500.0)],  # 越界
    ],
)
def test_rule_011_spans_are_sorted_clamped_and_degenerates_dropped(spans) -> None:
    """区间先排序、再夹进 ``[0, duration]``，``end <= start`` 的丢掉。"""
    chunks = plan_chunks(spans, 300.0, min_s=30.0, max_s=120.0, overlap_s=0.0)
    assert chunks
    assert chunks[0].start == 0.0
    assert chunks[-1].end == 300.0
    assert all(c.duration <= 120.0 + 1e-6 for c in chunks)


def test_rule_011_duplicate_spans_count_twice_toward_the_early_stop() -> None:
    """重叠的语音区间会**各算一次** ``acc``（legacy 行为：区间不去重）。

    钉住这条是为了防止把「顺手去重区间」当成等价改动：重复会让 ``acc`` 提前
    达到 ``target``，切点因此前移 —— 行为变了，不是重构。

    输入是「同一段 25s 语音报了两遍」+ 两段正常语音；去重后首片会切在 50.7s，
    不去重则切在 25.6s（间隙 25.0–26.2 的中点外扩 half 之前的位置）。
    """
    duplicated = [(0.0, 25.0), (0.0, 25.0), (26.2, 50.0), (51.4, 400.0)]
    deduplicated = [(0.0, 25.0), (26.2, 50.0), (51.4, 400.0)]
    chunks = plan_chunks(duplicated, 460.0, min_s=30.0, max_s=120.0, overlap_s=0.0)
    deduped = plan_chunks(deduplicated, 460.0, min_s=30.0, max_s=120.0, overlap_s=0.0)
    assert chunks[0].end == 25.6, "重复区间让 acc 提前达标 → 切点前移"
    assert deduped[0].end == 50.7, "去重会改变切点，所以它不是等价改动"
    assert all(c.duration <= 120.0 + 1e-6 for c in chunks)
    assert chunks[-1].end == 460.0
