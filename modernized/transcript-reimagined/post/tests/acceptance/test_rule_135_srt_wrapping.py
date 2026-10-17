"""RULE-135 —— SRT 长行折行（42 字符上限）。

规则卡 Given：60 字符字幕行，逗号落在**精确中点之后 3 个字符**处
→ 在该逗号**之后**断成两行（逗号留在前一行）；中点后 10 字符内无标点则在中点硬切；
42 字符以内不折；**只折一次**。

该 Given 的字面构造：`"甲"*33 + "，" + "乙"*26` —— 长度 60，中点下标 30，逗号下标 33。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import MAX_SRT_LINE_CHARS, Segment, to_srt, wrap_srt_line

GIVEN_60_CHAR_LINE = "甲" * 33 + "，" + "乙" * 26
GIVEN_60_CHAR_NO_PUNCT = "甲" * 33 + "乙" * 27


@pytest.mark.rule("RULE-135")
class TestRule135LineLengthConstant:
    def test_limit_is_42_and_not_relaxed(self):
        assert MAX_SRT_LINE_CHARS == 42


@pytest.mark.rule("RULE-135")
class TestRule135Given:
    def test_given_line_shape_is_what_the_card_says(self):
        assert len(GIVEN_60_CHAR_LINE) == 60
        assert GIVEN_60_CHAR_LINE.index("，") == 33  # 中点 30 之后 3 个字符

    def test_breaks_after_the_comma_nearest_after_the_midpoint(self):
        wrapped = wrap_srt_line(GIVEN_60_CHAR_LINE)
        first, second = wrapped.split("\n")
        assert first.endswith("，")  # 逗号留在前一行
        assert first == GIVEN_60_CHAR_LINE[:34]
        assert second == GIVEN_60_CHAR_LINE[34:]

    def test_srt_body_contains_the_wrapped_two_lines(self):
        srt = to_srt([Segment(0.0, 5.0, GIVEN_60_CHAR_LINE)])
        body = srt.strip().splitlines()[2:]
        assert len(body) == 2
        assert body[0].endswith("，")

    def test_hard_split_at_the_midpoint_when_no_punctuation_follows(self):
        wrapped = wrap_srt_line(GIVEN_60_CHAR_NO_PUNCT)
        assert wrapped == GIVEN_60_CHAR_NO_PUNCT[:30] + "\n" + GIVEN_60_CHAR_NO_PUNCT[30:]


@pytest.mark.rule("RULE-135")
class TestRule135Boundaries:
    @pytest.mark.parametrize("length", [1, 41, 42])
    def test_lines_at_or_under_42_chars_are_not_wrapped(self, length):
        text = "甲" * length
        assert wrap_srt_line(text) == text

    def test_a_43_char_line_is_wrapped(self):
        text = "甲" * 43
        assert "\n" in wrap_srt_line(text)

    @pytest.mark.parametrize("punctuation", list("，,。；;、：:！？!?"))
    def test_all_supported_punctuation_stays_on_the_first_line(self, punctuation):
        text = "甲" * 30 + punctuation + "乙" * 29
        first, _ = wrap_srt_line(text).split("\n")
        assert first.endswith(punctuation)

    def test_only_one_split_is_ever_made(self):
        # 折完仍可能超过 42 字符 —— 这是既有行为（规则卡的 edge case），不是缺陷。
        text = "甲" * 300
        assert wrap_srt_line(text).count("\n") == 1
        assert len(wrap_srt_line(text).split("\n")[0]) == 150

    def test_text_is_stripped_before_measuring(self):
        assert wrap_srt_line("  " + "甲" * 42 + "  ") == "甲" * 42
