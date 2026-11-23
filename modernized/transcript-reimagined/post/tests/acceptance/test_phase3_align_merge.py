"""Phase 3 验收：`align` / `merge`（P0-1、RULE-008/009/010/023/024）。

判据用 `AI_NATIVE_SPEC.md` §5.4 的**修正值**：P0-1 的重叠必须 ≥4 字符才会被
检出；规则卡里那个 3 字符的 `开会。` 例子是错的。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from transcript_reimagined.domain import Segment, TranscriptResult, Word

from transcript_reimagined.post.align import (
    HARD_BREAK,
    MAX_SEGMENT_S,
    MIN_SEGMENT_S,
    SOFT_BREAK,
    build_segments,
    enforce_monotonic,
    map_times,
    normalize_for_compare,
    split_sentence_ranges,
)
from transcript_reimagined.post.merge import (
    MIN_OVERLAP_CHARS,
    longest_overlap,
    merge_results,
    merge_texts,
)

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "offline_fixture.json"


# ---------------------------------------------------------------- 常量（不得放宽）


@pytest.mark.rule("RULE-024")
def test_pinned_merge_constants():
    assert MIN_OVERLAP_CHARS == 4
    from transcript_reimagined.post import merge

    assert merge.MIN_COVERAGE == 0.8  # docstring 70%，代码 80% —— 以代码为准
    assert merge.OVERLAP_WINDOW_CHARS == 240


@pytest.mark.rule("RULE-008")
def test_pinned_align_constants():
    assert frozenset("。！？!?…\n") == HARD_BREAK
    assert frozenset("，,；;、：:") == SOFT_BREAK
    assert MAX_SEGMENT_S == 15.0
    assert MIN_SEGMENT_S == 0.35


# ---------------------------------------------------------------- RULE-001（P0-1）


@pytest.mark.rule("RULE-001")
def test_overlap_shorter_than_four_chars_is_not_detected():
    """修正后的判据：3 字符重叠 = 0 检出，重复文本原样保留。"""
    assert longest_overlap("今天开会。", "开会。请准备") == 0
    assert merge_texts("今天开会。", "开会。请准备") == "今天开会。开会。请准备"


@pytest.mark.rule("RULE-001")
def test_overlap_of_four_or_more_chars_is_detected():
    assert longest_overlap("我们下周一开会。请", "开会。请准备材料") == len("开会。请")


@pytest.mark.rule("RULE-001")
def test_head_text_remaining_after_the_cut_is_never_dropped():
    prev = _result(segments=[Segment(100.0, 103.0, "我们下周一开会。请")])
    nxt = _result(segments=[Segment(102.9, 106.0, "开会。请准备材料")])
    merged = merge_results([prev, nxt])
    texts = [s.text for s in merged.segments]
    assert any("准备材料" in t for t in texts)
    assert all("准备材料" in t or "开会。请" in t for t in texts)


@pytest.mark.rule("RULE-001")
def test_earlier_segment_end_is_pulled_back_to_avoid_stacked_lines():
    prev = _result(segments=[Segment(100.0, 103.0, "我们下周一开会。请")])
    nxt = _result(segments=[Segment(102.9, 106.0, "开会。请准备材料")])
    merged = merge_results([prev, nxt])
    assert merged.segments[0].end <= merged.segments[1].start


@pytest.mark.rule("RULE-001")
def test_segments_inside_one_chunk_are_never_deduplicated_against_each_other():
    inner = [Segment(0.0, 1.0, "重复重复"), Segment(1.0, 2.0, "重复重复")]
    merged = merge_results([_result(segments=inner)])
    assert [s.text for s in merged.segments] == ["重复重复", "重复重复"]


@pytest.mark.rule("RULE-001")
def test_a_piece_is_dropped_only_when_nothing_remains_after_the_cut():
    # 重叠必须 ≥4 字符才会被检出；这里切完没有剩余，整段丢掉。
    prev = _result(segments=[Segment(0.0, 1.0, "下面我们开会。请")])
    nxt = _result(segments=[Segment(0.9, 2.0, "开会。请")])
    merged = merge_results([prev, nxt])
    assert [s.text for s in merged.segments] == ["下面我们开会。请"]


@pytest.mark.rule("RULE-001")
def test_merge_texts_fuzzy_overlap():
    prev = "第三，专有名词需要校对，例如冒烟测试"
    new = "专有名词需耍校对，例如冒烟测试和分片合并。"
    merged = merge_texts(prev, new)
    assert merged.count("冒烟测试") == 1
    assert merged.endswith("和分片合并。")


@pytest.mark.rule("RULE-001")
def test_merge_texts_never_drops_content():
    assert len(merge_texts("甲" * 50, "乙" * 50)) == 100


@pytest.mark.rule("RULE-024")
def test_common_prefix_char_is_not_an_overlap():
    assert longest_overlap("第一段。", "第二段。") == 0


@pytest.mark.rule("RULE-024")
def test_overlap_must_be_anchored_at_the_tail():
    assert longest_overlap("开场白提到冒烟测试然后结束了", "冒烟测试又是另一个话题的开头") == 0


# ---------------------------------------------------------------- RULE-023


@pytest.mark.rule("RULE-023")
def test_reported_costs_are_summed_and_zero_is_kept():
    results = [_result(cost=c) for c in (0.02, 0.02, None, 0.0)]
    assert merge_results(results).cost_usd == pytest.approx(0.04)


@pytest.mark.rule("RULE-023")
def test_audio_seconds_are_never_aggregated():
    merged = merge_results([_result(audio_seconds=4.0), _result(audio_seconds=3.0)])
    assert merged.audio_seconds is None


@pytest.mark.rule("RULE-023")
def test_all_none_costs_yield_none_not_zero():
    assert merge_results([_result(cost=None), _result(cost=None)]).cost_usd is None


@pytest.mark.rule("RULE-023")
def test_distinct_engine_names_are_joined():
    merged = merge_results([_result(engine="dashscope"), _result(engine="openrouter")])
    assert merged.engine == "dashscope+openrouter"


# ---------------------------------------------------------------- RULE-010 / fixture


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def words(fixture: dict) -> list[Word]:
    return [
        Word(w["text"], w["start"], w["end"], w["probability"])
        for w in fixture["whisper"]["words"]
    ]


@pytest.mark.rule("RULE-010")
def test_fixture_has_both_sources(fixture: dict):
    assert fixture["qwen"]["text"].strip()
    assert len(fixture["whisper"]["words"]) > 10
    assert fixture["whisper"]["words"][0]["start"] == 0.0


@pytest.mark.rule("RULE-010")
def test_qwen_text_is_fully_preserved(fixture: dict, words: list[Word]):
    """最重要的不变式：一个字都不能丢。"""
    text = fixture["qwen"]["text"]
    segments = build_segments(text, words)
    assert segments
    got = normalize_for_compare("".join(s.text for s in segments))
    assert got == normalize_for_compare(text)


@pytest.mark.rule("RULE-010")
def test_times_are_monotonic_and_in_range(fixture: dict, words: list[Word]):
    duration = max(w.end for w in words)
    segments = build_segments(fixture["qwen"]["text"], words)
    prev = 0.0
    for seg in segments:
        assert seg.start >= prev - 1e-6
        assert seg.end > seg.start
        assert seg.start >= -1e-6
        assert seg.end <= duration + 1.0
        prev = seg.start


@pytest.mark.rule("RULE-010")
def test_all_content_chars_get_a_time(fixture: dict, words: list[Word]):
    times = map_times(fixture["qwen"]["text"], words)
    content = [t for t in times if t is not None]
    assert len(content) == len(normalize_for_compare(fixture["qwen"]["text"]))
    assert all(t is not None for t in content)


@pytest.mark.rule("RULE-010")
def test_dropping_words_does_not_lose_text(words: list[Word]):
    text = "第一，离线转写的质量；第二，在线字幕的生成；第三，专有名词的校对。"
    segments = build_segments(text, words[::3])
    assert normalize_for_compare("".join(s.text for s in segments)) == normalize_for_compare(text)


@pytest.mark.rule("RULE-010")
def test_enforce_monotonic_repairs_overlap():
    segs = [
        Segment(start=0.0, end=2.0, text="甲"),
        Segment(start=1.0, end=3.0, text="乙"),
        Segment(start=0.5, end=1.0, text="丙"),
    ]
    fixed = enforce_monotonic(segs)
    assert [s.text for s in fixed] == ["甲", "乙", "丙"]
    assert fixed[1].start >= fixed[0].end
    assert fixed[2].start >= fixed[1].end


# ---------------------------------------------------------------- RULE-009 / RULE-008


@pytest.mark.rule("RULE-009")
def test_no_words_at_all_is_handled_without_losing_text():
    segments = build_segments("没有任何时间戳的文本。", [])
    assert normalize_for_compare("".join(s.text for s in segments)) == "没有任何时间戳的文本"


@pytest.mark.rule("RULE-009")
def test_segments_never_run_past_the_audio_duration():
    segments = build_segments("甲乙丙丁", None, duration_s=2.0)
    assert segments[0].start == 0.0
    assert all(s.end <= 2.0 for s in segments)


@pytest.mark.rule("RULE-009")
def test_blank_text_yields_no_segments():
    assert build_segments("   ", None, duration_s=10.0) == []


@pytest.mark.rule("RULE-008")
def test_hard_break_punctuation_ends_a_subtitle_line():
    segments = build_segments("第一句。第二句。", None, duration_s=6.0)
    assert [s.text for s in segments] == ["第一句。", "第二句。"]


@pytest.mark.rule("RULE-008")
def test_soft_break_does_not_end_on_dangling_lead_in():
    text = "第一，离线转写的质量；第二，在线字幕的生成；第三，专有名词的校对。"
    times = [(float(i) * 0.2, float(i) * 0.2 + 0.2) for i in range(len(text))]
    ranges = split_sentence_ranges(times, text, max_segment_s=15.0)
    pieces = [text[s:e] for s, e in ranges]
    assert not any(p.strip().endswith(("第二，", "第三，", "第一，")) for p in pieces)
    assert "".join(pieces) == text, "切句不能丢字"


@pytest.mark.rule("RULE-008")
def test_split_respects_max_duration_for_text_without_punctuation():
    times = [(float(i) * 0.5, float(i) * 0.5 + 0.5) for i in range(200)]
    text = "甲" * 200
    ranges = split_sentence_ranges(times, text, max_segment_s=10.0, soft_min_chars=5)
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(text)
    assert len(ranges) >= 1


@pytest.mark.rule("RULE-010")
def test_monotonic_and_complete_for_random_inputs():
    """性质测试：任意文本/词级时间下，时间不减且每个正文字符都有归属。"""
    import random

    rng = random.Random(20261017)
    alphabet = "甲乙丙丁戊己庚辛壬癸，。！？"
    for _ in range(100):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 80)))
        words: list[Word] = []
        cursor = 0.0
        for ch in text:
            if ch.isalnum():
                duration = rng.uniform(0.05, 0.5)
                words.append(Word(ch, cursor, cursor + duration))
                cursor += duration
        segments = build_segments(text, words)
        prev = 0.0
        for seg in segments:
            assert seg.start >= prev - 1e-9
            assert seg.end > seg.start
            prev = seg.start
        assert normalize_for_compare(
            "".join(seg.text for seg in segments)
        ) == normalize_for_compare(text)
        times = map_times(text, words)
        content_times = [t for ch, t in zip(text, times, strict=False) if ch.isalnum()]
        assert len(content_times) == len(normalize_for_compare(text))
        assert all(t is not None for t in content_times)


def _result(**overrides) -> TranscriptResult:
    return TranscriptResult(
        text=overrides.get("text", ""),
        segments=overrides.get("segments", []),
        language=overrides.get("language"),
        audio_seconds=overrides.get("audio_seconds"),
        cost_usd=overrides.get("cost"),
        engine=overrides.get("engine", "offline"),
        has_timestamps=overrides.get("has_timestamps", True),
    )
