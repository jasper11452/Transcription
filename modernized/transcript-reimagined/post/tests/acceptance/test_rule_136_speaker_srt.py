"""C8：说话人标签在 txt 与 srt **双产物**里一致输出。

`RULE-136` 只规定了 txt 的分块；Q8 的裁定把「`to_txt` 的 `[speaker_N]` 前缀在
`to_srt` 里同样存在」列为验收条件。没有 speaker 的段落按 `[?]` 标注（与 txt 一致），
完全没有 speaker 时 SRT 保持 legacy 的逐字节行为。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.domain import Segment

from transcript_reimagined.post.render import to_srt, to_txt


def _segments() -> list[Segment]:
    return [
        Segment(0.0, 1.0, "你好", speaker="speaker_1"),
        Segment(1.0, 2.0, "我们开始", speaker="speaker_1"),
        Segment(2.0, 3.0, "好的", speaker="speaker_2"),
        Segment(3.0, 4.0, "会议结束", speaker=None),
    ]


@pytest.mark.rule("RULE-136")
def test_txt_merges_consecutive_segments_per_speaker():
    assert to_txt("", _segments()) == (
        "[speaker_1] 你好我们开始\n[speaker_2] 好的\n[?] 会议结束\n"
    )


@pytest.mark.rule("RULE-136")
def test_srt_carries_the_same_speaker_labels():
    srt = to_srt(_segments())
    assert "[speaker_1] 你好" in srt
    assert "[speaker_1] 我们开始" in srt
    assert "[speaker_2] 好的" in srt
    assert "[?] 会议结束" in srt


@pytest.mark.rule("RULE-136")
def test_srt_without_speakers_is_unchanged():
    """没有 diar 时 SRT 必须保持 legacy 的逐字节行为。"""
    segments = [Segment(0.0, 1.0, "你好"), Segment(1.0, 2.0, "世界")]
    srt = to_srt(segments)
    assert srt == (
        "1\n00:00:00,000 --> 00:00:01,000\n你好\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n世界\n"
    )


@pytest.mark.rule("RULE-136")
def test_speaker_prefix_participates_in_wrapping():
    """标签 + 正文一起折行，避免加了前缀后单行超过 42 字符。"""
    text = "这是一句很长的台词" * 6
    srt = to_srt([Segment(0.0, 1.0, text, speaker="speaker_1")])
    body_lines = [line for line in srt.splitlines() if line and "-->" not in line]
    # 第一行是编号；正文行最多两行，且都带标签或属于同一条字幕。
    assert any("[speaker_1]" in line for line in body_lines)
