"""``RULE-136`` —— 带说话人的文本输出分块。

判据：段落 ``[speaker_1:'你好', speaker_1:'我们开始', speaker_2:'好的', None:'会议结束']``
→ 输出 ``[speaker_1] 你好我们开始``、``[speaker_2] 好的``、``[?] 会议结束``；
无任何段落带 speaker 时改为一段一行；无 ``segments`` 时按合并文本原样输出。

这条规则只在 **segments 路径**上可达（legacy 的 pipeline 传 ``None``，所以它是死代码面）。
本切片的 runner 显式传 segments —— 因此它是**首次可被执行**的验收测试。
"""

from __future__ import annotations

from transcript_reimagined.domain.models import Segment
from transcript_reimagined.post.render import to_txt

SPEC_SEGMENTS = [
    Segment(start=0.0, end=1.0, text="你好", speaker="speaker_1"),
    Segment(start=1.0, end=2.0, text="我们开始", speaker="speaker_1"),
    Segment(start=2.0, end=3.0, text="好的", speaker="speaker_2"),
    Segment(start=3.0, end=4.0, text="会议结束", speaker=None),
]


def test_rule_136_spec_example_groups_consecutive_segments_per_speaker():
    out = to_txt("这个参数必须被忽略", SPEC_SEGMENTS)
    assert out == "[speaker_1] 你好我们开始\n[speaker_2] 好的\n[?] 会议结束\n"


def test_rule_136_segments_without_any_speaker_become_one_line_each():
    out = to_txt("忽略", [Segment(0.0, 1.0, "甲"), Segment(1.0, 2.0, "乙")])
    assert out == "甲\n乙\n"


def test_rule_136_without_segments_the_merged_text_is_kept_as_is():
    assert to_txt("  我们把集成做完了  ") == "我们把集成做完了\n"


def test_rule_136_whitespace_only_segments_are_skipped_and_do_not_break_a_run():
    segments = [
        Segment(0.0, 1.0, "你好", speaker="speaker_1"),
        Segment(1.0, 2.0, "   ", speaker="speaker_1"),
        Segment(2.0, 3.0, "我们开始", speaker="speaker_1"),
    ]
    assert to_txt("", segments) == "[speaker_1] 你好我们开始\n"


def test_rule_136_segment_text_is_stripped_before_concatenation():
    segments = [
        Segment(0.0, 1.0, "  你好  ", speaker="speaker_1"),
        Segment(1.0, 2.0, " 好的 ", speaker="speaker_1"),
    ]
    assert to_txt("", segments) == "[speaker_1] 你好好的\n"


def test_rule_136_comment_lines_are_prefixed_and_come_first():
    out = to_txt(
        "文本",
        [Segment(0.0, 1.0, "甲", speaker="speaker_1")],
        comment_lines=["词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3"],
    )
    assert out == "# 词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3\n[speaker_1] 甲\n"


def test_rule_136_an_empty_result_is_an_empty_string():
    assert to_txt("", None) == ""
    assert to_txt("", [Segment(0.0, 1.0, "  ")]) == ""
    assert to_txt("", None, comment_lines=[]) == ""
