"""RULE-062 —— SRT 拒绝倒序时间、编号只数存活行。

规则卡 Given：段落 `[空文本, (12.0,20.0), (30.0,29.0)]`
→ 空段跳过、第二段编号为 1、倒序的第三段**抛 `ValueError`** 使任务失败且不写 SRT；
若全被过滤则返回空字符串。

失败语义（NFR-3 / 规则卡的「rather than emitting a corrupt file」）：错误绝不当结果返回 ——
由于异常在写文件之前抛出，`.srt` 不会被写下（落盘路径的判据见 `test_rule_132`）。
"""

from __future__ import annotations

import re

import pytest

from transcript_reimagined.post import Segment, fmt_timestamp, to_srt

SRT_TIME = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$")


@pytest.mark.rule("RULE-062")
class TestRule062Given:
    def test_inverted_segment_raises_value_error(self):
        segments = [Segment(0.0, 1.0, "   "), Segment(12.0, 20.0, "乙"), Segment(30.0, 29.0, "丙")]
        with pytest.raises(ValueError):
            to_srt(segments)

    def test_error_message_names_the_inversion_and_the_text(self):
        with pytest.raises(ValueError, match="时间倒序"):
            to_srt([Segment(30.0, 29.0, "丙")])

    def test_empty_segment_is_skipped_and_numbering_stays_continuous(self):
        srt = to_srt([Segment(0.0, 1.0, "   "), Segment(12.0, 20.0, "乙")])
        assert srt.splitlines()[0] == "1"
        assert "00:00:12,000 --> 00:00:20,000" in srt
        assert "\n2\n" not in "\n" + srt

    def test_numbering_is_assigned_after_filtering(self):
        srt = to_srt([Segment(0.0, 1.0, ""), Segment(1.0, 2.0, "甲"), Segment(2.0, 3.0, "乙")])
        assert [ln for ln in srt.splitlines() if ln.isdigit()] == ["1", "2"]

    def test_all_filtered_returns_empty_string(self):
        assert to_srt([Segment(0.0, 1.0, ""), Segment(1.0, 2.0, "  \n ")]) == ""

    def test_comment_lines_are_dropped_when_no_body_survives(self):
        assert to_srt([Segment(0.0, 1.0, "")], comment_lines=["词表替换：甲→乙 ×1"]) == ""


@pytest.mark.rule("RULE-062")
class TestRule062Boundaries:
    def test_zero_length_segment_is_accepted(self):
        # 只有严格倒序才报错（end == start 合法）。
        srt = to_srt([Segment(5.0, 5.0, "瞬时")])
        assert "00:00:05,000 --> 00:00:05,000" in srt

    def test_segment_text_is_stripped_before_writing(self):
        srt = to_srt([Segment(0.0, 1.0, "  甲  ")])
        assert srt.strip().splitlines()[2] == "甲"

    def test_comment_block_precedes_entry_one_and_is_prefixed(self):
        srt = to_srt([Segment(0.0, 1.0, "甲")], comment_lines=["词表替换：甲→乙 ×1"])
        assert srt.startswith("# 词表替换：甲→乙 ×1")


@pytest.mark.rule("RULE-025")
class TestRule062TimestampInteraction:
    """与本规则直接相邻的时间格式要求（`RULE-025`，自有验收测试文件）。"""

    def test_timestamp_never_renders_a_1000_millisecond_field(self):
        srt = to_srt([Segment(0.0, 59.9996, "边界")])
        assert "1000" not in srt
        assert "00:01:00,000" in srt

    def test_timestamp_format_is_well_formed(self):
        srt = to_srt([Segment(0.0, 65.25, "句子。")])
        assert SRT_TIME.match(srt.splitlines()[1])

    def test_negative_time_is_clamped_to_zero(self):
        assert fmt_timestamp(-1.5) == "00:00:00,000"
