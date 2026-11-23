"""领域模型的契约测试 —— `AI_NATIVE_SPEC.md` §2 Domain Model。

这**不是**规则卡的验收判据（规则卡 `RULE-025`/`RULE-059` 各有自己的文件），
而是「所有引擎的公共语言」这层词汇本身的形状测试：谁能改、谁只读、
以及 `shifted()` 的时间轴语义。领域模型是四个引擎适配器与 `post`/`orchestrate`
共用的边界，形状漂移会在这里被最先发现。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from transcript_reimagined.domain import AudioInfo, Chunk, Segment, TranscriptResult, Word


def test_word_is_frozen_and_positional() -> None:
    w = Word("好", 0.0, 0.4, 0.93)
    assert (w.text, w.start, w.end, w.probability) == ("好", 0.0, 0.4, 0.93)
    assert Word("好", 0.0, 0.4).probability is None  # 百炼路径为 None
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.text = "改"  # type: ignore[misc]


def test_segment_duration_is_clamped_at_zero() -> None:
    assert Segment(1.0, 2.5, "x").duration == pytest.approx(1.5)
    assert Segment(2.5, 1.0, "x").duration == 0.0  # 倒序不产生负时长
    assert Segment(1.0, 1.0, "x").duration == 0.0


@pytest.mark.parametrize("duration", [0.0, -3.0, 12.5])
def test_chunk_duration_never_negative(duration: float) -> None:
    c = Chunk(index=0, start=100.0, end=100.0 + duration)
    assert c.duration == max(0.0, duration)
    assert c.index == 0


def test_segment_shifted_moves_words_by_the_same_offset() -> None:
    """分片内相对时间轴 → 整段音频绝对时间轴，词与段必须同步平移。"""
    seg = Segment(0.5, 1.5, "你好", words=[Word("你", 0.5, 0.9), Word("好", 0.9, 1.5)])
    out = seg.shifted(60.0)
    assert (out.start, out.end) == (60.5, 61.5)
    assert [(w.start, w.end) for w in out.words] == [(60.5, 60.9), (60.9, 61.5)]
    assert out.words[0].probability is None
    # 原对象不被就地修改
    assert seg.start == 0.5


def test_segment_shifted_does_not_carry_the_speaker_label() -> None:
    """已知 legacy 行为，刻意保留（见 `models.py` 的 `Segment.shifted` docstring）。

    `Segment.shifted` 丢 `speaker`。Phase 1 要逐字节等价，所以原样保留并在此钉住；
    改它是一次需要署名的行为变更，决策点在 Phase 3（`diar` 连通 + `RULE-136`
    要求 srt/txt 双产物都输出说话人）。谁改这里，先去看规格 §5.2 的 `RULE-136`。
    """
    seg = Segment(0.0, 1.0, "你好", speaker="speaker_1")
    assert seg.shifted(10.0).speaker is None


def test_transcript_result_shifted_shifts_every_segment() -> None:
    result = TranscriptResult(
        text="你好再见",
        segments=[Segment(0.0, 1.0, "你好"), Segment(1.0, 2.0, "再见")],
        language="zh",
        audio_seconds=2.0,
        cost_usd=0.0001,
        engine="dashscope",
        has_timestamps=True,
    )
    out = result.shifted(30.0)
    assert [s.start for s in out.segments] == [30.0, 31.0]
    assert out.segments[1].text == "再见"
    # 标量与文本原样透传（逐字节等价的前提）
    assert (out.text, out.language, out.engine) == ("你好再见", "zh", "dashscope")
    assert (out.audio_seconds, out.cost_usd, out.has_timestamps) == (2.0, 0.0001, True)
    assert result.segments[0].start == 0.0


def test_transcript_result_defaults_describe_a_plain_engine_answer() -> None:
    """默认值 = 「引擎只回了文本」：无段落、无时间戳、无成本。"""
    out = TranscriptResult(text="嗯")
    assert out.segments == []
    assert out.language is None
    assert out.audio_seconds is None
    assert out.cost_usd is None
    assert out.engine == ""
    assert out.has_timestamps is False


def test_audio_info_reports_megabytes_from_bytes() -> None:
    info = AudioInfo(
        path=Path("/tmp/fixture-not-a-real-file.m4a"),
        duration=3600.0,
        size_bytes=3_500_000,
        codec="aac",
        sample_rate=44100,
        channels=2,
        has_audio=True,
    )
    assert info.megabytes == pytest.approx(3.5)
    assert info.duration == 3600.0


def test_audio_info_accepts_unknown_probe_fields() -> None:
    """ffprobe 缺字段时用 None，不猜（`has_audio=False` 才是「没有音轨」的断言）。"""
    info = AudioInfo(
        path=Path("/tmp/fixture-no-audio-not-a-real-file.mp4"),
        duration=0.0,
        size_bytes=0,
        codec=None,
        sample_rate=None,
        channels=None,
        has_audio=False,
    )
    assert info.codec is None
    assert info.channels is None
    assert info.has_audio is False
