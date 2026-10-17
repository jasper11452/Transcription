"""词级对齐单测：用真实模型输出录制的夹具（tests/data/offline_fixture.json）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcript.align import (
    build_segments,
    enforce_monotonic,
    map_times,
    normalize_for_compare,
    split_sentence_ranges,
)
from transcript.models import Segment, Word

FIXTURE = Path(__file__).parent / "data" / "offline_fixture.json"


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def words(fixture: dict) -> list[Word]:
    return [
        Word(w["text"], w["start"], w["end"], w["probability"]) for w in fixture["whisper"]["words"]
    ]


def test_fixture_has_both_sources(fixture: dict):
    """夹具必须真的含两侧数据，否则这组测试是自欺欺人。"""
    assert fixture["qwen"]["text"].strip()
    assert len(fixture["whisper"]["words"]) > 10
    assert fixture["whisper"]["words"][0]["start"] == 0.0


def test_qwen_text_is_fully_preserved(fixture: dict, words: list[Word]):
    """最重要的不变式：一个字都不能丢。"""
    text = fixture["qwen"]["text"]
    segments = build_segments(text, words)
    assert segments, "对齐不能产出空结果"
    got = normalize_for_compare("".join(s.text for s in segments))
    assert got == normalize_for_compare(text)


def test_times_are_monotonic_and_in_range(fixture: dict, words: list[Word]):
    duration = max(w.end for w in words)
    segments = build_segments(fixture["qwen"]["text"], words)
    prev = 0.0
    for seg in segments:
        assert seg.start >= prev - 1e-6, "时间倒序会让播放器丢弃整段字幕"
        assert seg.end > seg.start
        assert seg.start >= -1e-6
        assert seg.end <= duration + 1.0
        prev = seg.start
    assert segments[0].start < 1.0
    assert segments[-1].end >= duration - 1.0


def test_all_content_chars_get_a_time(fixture: dict, words: list[Word]):
    """未匹配到的字符靠插值补上，不允许出现 None（否则会整句丢时间）。"""
    times = map_times(fixture["qwen"]["text"], words)
    content = [t for t in times if t is not None]
    assert len(content) == len(normalize_for_compare(fixture["qwen"]["text"]))
    assert all(t is not None for t in content)


def test_dropping_words_does_not_lose_text(words: list[Word]):
    """whisper 漏词（真实存在）时，文本仍须完整保留。"""
    text = "第一，离线转写的质量；第二，在线字幕的生成；第三，专有名词的校对。"
    partial = words[::3]  # 只留 1/3 词，制造大面积错配
    segments = build_segments(text, partial)
    assert normalize_for_compare("".join(s.text for s in segments)) == normalize_for_compare(text)


def test_no_words_at_all_is_handled():
    """没有任何时间戳时不能崩，也不能伪造出离谱时间。"""
    segments = build_segments("没有任何时间戳的文本。", [])
    assert normalize_for_compare("".join(s.text for s in segments)) == "没有任何时间戳的文本"


def test_offset_shifts_into_absolute_timeline(words: list[Word]):
    base = build_segments("转录工具冒烟测试。", words)
    shifted = build_segments("转录工具冒烟测试。", words, offset=100.0)
    assert shifted[0].start >= 100.0
    assert shifted[0].end > base[0].end


def test_enforce_monotonic_repairs_overlap():
    segs = [
        Segment(start=0.0, end=2.0, text="甲"),
        Segment(start=1.0, end=3.0, text="乙"),  # 与上一段重叠
        Segment(start=0.5, end=1.0, text="丙"),  # 倒序
    ]
    fixed = enforce_monotonic(segs)
    assert [s.text for s in fixed] == ["甲", "乙", "丙"]
    assert fixed[1].start >= fixed[0].end
    assert fixed[2].start >= fixed[1].end


def test_split_sentence_ranges_respects_max_duration():
    """超长无标点文本必须被硬切开，否则一条字幕能横跨好几分钟。"""
    times = [(float(i) * 0.5, float(i) * 0.5 + 0.5) for i in range(200)]
    text = "甲" * 200
    ranges = split_sentence_ranges(times, text, max_segment_s=10.0, soft_min_chars=5)
    assert len(ranges) >= 1
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(text)


def test_soft_break_does_not_end_on_dangling_lead_in():
    """字幕不能停在“第二，”这种悬空引导词上——人读到一半就断了。"""
    text = "第一，离线转写的质量；第二，在线字幕的生成；第三，专有名词的校对。"
    times = [(float(i) * 0.2, float(i) * 0.2 + 0.2) for i in range(len(text))]
    ranges = split_sentence_ranges(times, text, max_segment_s=15.0)
    pieces = [text[s:e] for s, e in ranges]
    assert not any(p.strip().endswith(("第二，", "第三，", "第一，")) for p in pieces), pieces
    assert "".join(pieces) == text, "切句不能丢字"


def test_soft_break_happens_when_line_is_long_enough():
    text = "离线转写使用本地模型，因为它不需要网络，而且数据不出本机。"
    times = [(float(i) * 0.3, float(i) * 0.3 + 0.3) for i in range(len(text))]
    ranges = split_sentence_ranges(times, text)
    assert len(ranges) >= 2, "够长的句子应该在句中标点处断开，而不是挤成一整段"
