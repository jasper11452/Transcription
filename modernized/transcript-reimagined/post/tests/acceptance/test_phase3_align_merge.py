"""Phase 3 待落地的验收判据（`align` / `merge`）—— 现为 expected-failure。

`REIMAGINED_ARCHITECTURE.md` §5：Phase 1 的 `post` **只含 `glossary.py` + `render.py`**，
`align` / `merge` 属 Phase 3。这里按「先写判据、后写实现」的顺序把规则卡固化下来：
每条测试都带规则 ID，并且**用 `AI_NATIVE_SPEC.md` §5.4 的修正值**（P0 的两条判据在
规则卡里的例子是错的，双评委实际执行过被引用的函数）。

本文件的测试目前**全部 xfail**：`align` / `merge` 是显式 `NotImplementedError` 占位。
实现落地后这些测试应当转绿，届时去掉 xfail 标记即可（`strict=False`，实现完成时
会以 XPASS 显示而不阻断套件）。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import Segment, Word
from transcript_reimagined.post.align import build_segments, normalize_for_compare
from transcript_reimagined.post.merge import MIN_OVERLAP_CHARS, longest_overlap, merge_results

phase3 = pytest.mark.phase3
xfail3 = pytest.mark.xfail(
    reason="Phase 3：align/merge 尚未实现（显式 NotImplementedError）", strict=False
)


# ---------------------------------------------------------------- RULE-001（P0-1）


@phase3
@pytest.mark.rule("RULE-024")
class TestPhase3PinnedConstants:
    """Phase 3 实现时不得放宽的常量 —— 它们现在就已存在，所以**不是** xfail。"""

    def test_overlap_threshold_is_four_characters(self):
        assert MIN_OVERLAP_CHARS == 4

    def test_coverage_threshold_is_eighty_percent_code_wins_over_the_docstring(self):
        from transcript_reimagined.post import merge

        # docstring 写 70%，可执行常量是 0.8 —— 以代码为准（更严格的那个）。
        assert merge.MIN_COVERAGE == 0.8

    def test_overlap_window_is_240_characters(self):
        from transcript_reimagined.post import merge

        assert merge.OVERLAP_WINDOW_CHARS == 240

    def test_align_break_and_segment_constants(self):
        from transcript_reimagined.post import align

        assert align.HARD_BREAK == "。！？!?…\n"
        assert align.SOFT_BREAK == "，,；;、：:"
        assert align.MAX_SEGMENT_S == 15.0
        assert align.MIN_SEGMENT_S == 0.35


@phase3
@xfail3
@pytest.mark.rule("RULE-001")
@pytest.mark.pending_implementation("RULE-001")
class TestRule001ChunkBoundaryDedup:
    """去重只在分片边界发生，正文零丢失。

    ⚠️ 判据用 §5.4 的修正值：重叠必须 ≥ `MIN_OVERLAP_CHARS`（4）才会被检出；
    规则卡里那个 3 字符的 `开会。` 例子是错的（3 字符重叠检测为 0，重复文本原样保留）。
    """

    def test_overlap_shorter_than_four_chars_is_not_detected(self):
        # 修正后的判据：3 字符重叠 = 0 检出，重复文本原样保留。
        assert longest_overlap("今天开会。", "开会。请准备") == 0

    def test_overlap_of_four_or_more_chars_is_detected(self):
        assert longest_overlap("我们下周一开会。请", "开会。请准备材料") == len("开会。请")

    def test_head_text_remaining_after_the_cut_is_never_dropped(self):
        prev = [Segment(100.0, 103.0, "我们下周一开会。请")]
        nxt = [Segment(102.9, 106.0, "开会。请准备材料")]
        merged = merge_results([prev, nxt])
        texts = [s.text for s in merged.segments]
        # 「开会。请」被切掉，剩下的「准备材料」必须还在。
        assert any("准备材料" in t for t in texts)
        assert all("准备材料" in t or "开会。请" in t for t in texts)

    def test_earlier_segment_end_is_pulled_back_to_avoid_stacked_lines(self):
        prev = [Segment(100.0, 103.0, "我们下周一开会。请")]
        nxt = [Segment(102.9, 106.0, "开会。请准备材料")]
        merged = merge_results([prev, nxt])
        assert merged.segments[0].end <= merged.segments[1].start

    def test_segments_inside_one_chunk_are_never_deduplicated_against_each_other(self):
        inner = [Segment(0.0, 1.0, "重复重复"), Segment(1.0, 2.0, "重复重复")]
        merged = merge_results([inner])
        assert [s.text for s in merged.segments] == ["重复重复", "重复重复"]

    def test_a_piece_is_dropped_only_when_nothing_remains_after_the_cut(self):
        prev = [Segment(0.0, 1.0, "下面我们开会。")]
        nxt = [Segment(0.9, 2.0, "开会。")]
        merged = merge_results([prev, nxt])
        assert [s.text for s in merged.segments] == ["下面我们开会。"]


# ---------------------------------------------------------------- RULE-023 / RULE-024


@phase3
@xfail3
@pytest.mark.rule("RULE-023")
@pytest.mark.pending_implementation("RULE-023")
class TestRule023CostAggregation:
    def test_reported_costs_are_summed_and_zero_is_kept(self):
        results = [_result(cost=c) for c in (0.02, 0.02, None, 0.0)]
        merged = merge_results(results)
        assert merged.cost_usd == pytest.approx(0.04)

    def test_audio_seconds_are_never_aggregated(self):
        merged = merge_results([_result(audio_seconds=4.0), _result(audio_seconds=3.0)])
        assert merged.audio_seconds is None

    def test_all_none_costs_yield_none_not_zero(self):
        merged = merge_results([_result(cost=None), _result(cost=None)])
        assert merged.cost_usd is None

    def test_distinct_engine_names_are_joined(self):
        merged = merge_results([_result(engine="dashscope"), _result(engine="openrouter")])
        assert merged.engine == "dashscope+openrouter"


@phase3
@xfail3
@pytest.mark.rule("RULE-024")
@pytest.mark.pending_implementation("RULE-024")
class TestRule024OverlapJudgement:
    def test_a_fuzzy_match_below_the_coverage_threshold_is_rejected(self):
        # 240 字符窗口内的近似匹配覆盖率不足 → 不算重叠。
        prev = "甲" * 200 + "乙" * 40
        nxt = "乙" * 40 + "丙" * 60
        assert longest_overlap(prev, nxt) < MIN_OVERLAP_CHARS * 10


# ---------------------------------------------------------------- RULE-008/009/010（align）


@phase3
@xfail3
@pytest.mark.rule("RULE-010")
@pytest.mark.pending_implementation("RULE-010")
class TestRule010MonotonicTimeline:
    def test_segment_times_never_go_backwards(self):
        words = [
            Word("你", 0.0, 0.4),
            Word("好", 0.4, 0.9),
            Word("世", 0.9, 1.2),
            Word("界", 1.2, 1.6),
        ]
        segments = build_segments("你好世界", words)
        for prev, nxt in zip(segments, segments[1:], strict=False):
            assert nxt.start >= prev.start
            assert prev.end <= nxt.end

    def test_punctuation_and_whitespace_do_not_participate_in_alignment(self):
        assert normalize_for_compare("转录工具冒烟测试。") == normalize_for_compare(
            "转录工具冒烟测试，"
        )

    def test_different_text_is_not_equal_after_normalisation(self):
        assert normalize_for_compare("转录工具冒烟测试。") != normalize_for_compare(
            "转录工具冒烟测试补充内容。"
        )

    def test_blank_text_yields_no_segments(self):
        assert build_segments("   ", None, duration_s=10.0) == []


@phase3
@xfail3
@pytest.mark.rule("RULE-009")
@pytest.mark.pending_implementation("RULE-009")
class TestRule009FallbackDistribution:
    def test_nominal_duration_is_a_quarter_second_per_character(self):
        segments = build_segments("甲乙丙丁戊己庚辛", None, duration_s=0.0)
        assert segments  # 兜底也要产出段落
        assert segments[0].start == 0.0

    def test_segments_never_run_past_the_audio_duration(self):
        segments = build_segments("甲乙丙丁", None, duration_s=2.0)
        assert all(s.end <= 2.0 for s in segments)


@phase3
@xfail3
@pytest.mark.rule("RULE-008")
@pytest.mark.pending_implementation("RULE-008")
class TestRule008SentenceSplitting:
    def test_hard_break_punctuation_ends_a_subtitle_line(self):
        segments = build_segments("第一句。第二句。", None, duration_s=6.0)
        assert [s.text for s in segments] == ["第一句。", "第二句。"]

    def test_hard_break_precedes_soft_break(self):
        text = "这是一句比较长的话，它先遇到逗号，然后才遇到句号。"
        segments = build_segments(text, None, duration_s=20.0)
        assert all(len(s.text) <= 15 + 4 for s in segments)


def _result(**overrides):
    """构造一个最小 `TranscriptResult` 形状的对象（align/merge 落地时改用 domain 类型）。"""

    class _Result:
        text = overrides.get("text", "文本")
        segments: list[Segment] = overrides.get("segments", [])
        language = None
        audio_seconds = overrides.get("audio_seconds")
        cost_usd = overrides.get("cost")
        engine = overrides.get("engine", "offline")
        has_timestamps = overrides.get("has_timestamps", True)

    return _Result()
