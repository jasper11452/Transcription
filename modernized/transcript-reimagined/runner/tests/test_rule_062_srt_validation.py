"""``RULE-062`` —— SRT 拒绝倒序时间、编号只数存活行。

判据：段落 ``[空文本, (12.0,20.0), (30.0,29.0)]`` → 空段跳过、第二段编号为 1、
倒序的第三段**抛 ``ValueError``** 使任务失败且不写 SRT；若全被过滤则返回空字符串。

这条是「错误文本绝不混进产物」的执行体：宁可任务失败，也不产出坏字幕。
"""

from __future__ import annotations

import re

import pytest

from transcript_reimagined.domain.models import Segment
from transcript_reimagined.post.render import MAX_SRT_LINE_CHARS, to_srt


def test_rule_062_spec_example_raises_before_writing_a_corrupt_file():
    segments = [
        Segment(start=0.0, end=10.0, text="   "),
        Segment(start=12.0, end=20.0, text="第一句"),
        Segment(start=30.0, end=29.0, text="倒序的句子"),
    ]
    with pytest.raises(ValueError):
        to_srt(segments)


def test_rule_062_empty_segments_are_skipped_and_numbering_stays_contiguous():
    segments = [
        Segment(start=0.0, end=10.0, text=""),
        Segment(start=12.0, end=20.0, text="第一句"),
        Segment(start=30.0, end=40.0, text="第二句"),
    ]
    srt = to_srt(segments)
    assert re.findall(r"(?m)^(\d+)$", srt) == ["1", "2"], srt
    assert srt.count("-->") == 2


def test_rule_062_whitespace_only_text_does_not_survive():
    assert to_srt([Segment(start=3.0, end=4.0, text=" \n\t ")]) == ""


def test_rule_062_nothing_survives_returns_an_empty_string_without_comments():
    out = to_srt([Segment(start=0.0, end=1.0, text="")], comment_lines=["词表替换：无"])
    assert out == ""


def test_rule_062_end_equal_to_start_is_accepted():
    """只有严格倒序才抛错；零长度段落是合法的。"""
    srt = to_srt([Segment(start=5.0, end=5.0, text="瞬时")])
    assert "00:00:05,000 --> 00:00:05,000" in srt


def test_rule_062_body_text_is_stripped():
    srt = to_srt([Segment(start=0.0, end=1.0, text="  有空格  ")])
    assert "有空格" in srt
    assert "  有空格" not in srt


def test_rule_062_blocks_are_separated_by_a_blank_line_and_end_with_a_newline():
    srt = to_srt([Segment(start=0.0, end=1.0, text="甲"), Segment(start=1.0, end=2.0, text="乙")])
    assert srt.endswith("\n")
    assert "\n\n2\n" in srt


def test_rule_062_comment_lines_precede_entry_one_and_are_prefixed():
    srt = to_srt(
        [Segment(start=0.0, end=1.0, text="甲")],
        comment_lines=["词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3"],
    )
    assert srt.startswith("# 词表替换")
    assert srt.split("\n\n")[1].splitlines()[0] == "1"


def test_rule_062_line_limit_constant_is_42_chars():
    assert MAX_SRT_LINE_CHARS == 42
