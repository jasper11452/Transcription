"""RULE-136 —— 带说话人的文本输出分块。

规则卡 Given：段落 `[speaker_1:'你好', speaker_1:'我们开始', speaker_2:'好的', None:'会议结束']`
→ 输出 `[speaker_1] 你好我们开始`、`[speaker_2] 好的`、`[?] 会议结束`；
无任何段落带 speaker 时改为**一段一行**；无 `segments` 时按合并文本原样输出。

规则卡同时附带一条硬约束：`speaker` 恒为 `None` 的**在线**路径不得因本规则而变成
`[?]` 分块输出 —— 没有任何段落带 speaker 时走一段一行的分支。这条为本规则的一部分，
故在此断言；`C8` 侧「在线引擎不产出说话人」的归属在其它服务，不重复。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import Segment, to_txt


def _segments():
    return [
        Segment(0.0, 1.0, "你好", speaker="speaker_1"),
        Segment(1.0, 2.0, "我们开始", speaker="speaker_1"),
        Segment(2.0, 3.0, "好的", speaker="speaker_2"),
        Segment(3.0, 4.0, "会议结束"),
    ]


@pytest.mark.rule("RULE-136")
class TestRule136Given:
    def test_consecutive_same_speaker_segments_form_one_block(self):
        assert to_txt("忽略我", _segments()) == (
            "[speaker_1] 你好我们开始\n[speaker_2] 好的\n[?] 会议结束\n"
        )

    def test_blocks_carry_no_separator_between_concatenated_segments(self):
        assert "[speaker_1] 你好我们开始" in to_txt("", _segments())

    def test_missing_speaker_is_rendered_as_question_mark(self):
        assert "[?] 会议结束" in to_txt("", _segments())


@pytest.mark.rule("RULE-136")
class TestRule136Fallbacks:
    def test_without_any_speaker_segments_go_one_per_line(self):
        segments = [Segment(0.0, 1.0, "甲"), Segment(1.0, 2.0, "乙")]
        assert to_txt("忽略我", segments) == "甲\n乙\n"
        # 在线路径：没有 speaker 标签就不该出现 [?] 分块。
        assert "[?]" not in to_txt("", segments)

    def test_without_segments_the_merged_text_is_written_as_is(self):
        assert to_txt("只有正文", None) == "只有正文\n"
        assert to_txt("只有正文", []) == "只有正文\n"

    def test_no_content_is_empty_not_blank_noise(self):
        assert to_txt("", []) == ""
        assert to_txt("   ", None) == ""


@pytest.mark.rule("RULE-136")
class TestRule136Boundaries:
    def test_whitespace_only_segment_does_not_break_a_speaker_run(self):
        segments = [
            Segment(0.0, 1.0, "你好", speaker="speaker_1"),
            Segment(1.0, 2.0, "   ", speaker="speaker_1"),
            Segment(2.0, 3.0, "我们开始", speaker="speaker_1"),
        ]
        assert to_txt("", segments) == "[speaker_1] 你好我们开始\n"

    def test_segment_text_is_stripped_inside_a_block(self):
        segments = [
            Segment(0.0, 1.0, "  你好 ", speaker="speaker_1"),
            Segment(1.0, 2.0, " 我们开始", speaker="speaker_1"),
        ]
        assert to_txt("", segments) == "[speaker_1] 你好我们开始\n"

    def test_a_run_split_by_another_speaker_opens_a_new_block(self):
        segments = [
            Segment(0.0, 1.0, "甲", speaker="speaker_1"),
            Segment(1.0, 2.0, "乙", speaker="speaker_2"),
            Segment(2.0, 3.0, "丙", speaker="speaker_1"),
        ]
        assert to_txt("", segments) == "[speaker_1] 甲\n[speaker_2] 乙\n[speaker_1] 丙\n"

    def test_comment_lines_are_prefixed_and_precede_the_body(self):
        txt = to_txt("正文", None, comment_lines=["词表替换：甲→乙 ×1"])
        assert txt == "# 词表替换：甲→乙 ×1\n正文\n"
