"""``RULE-135`` —— SRT 长行折行。

判据：60 字符行、中点后 3 字符处有逗号 → 在该逗号后断成两行（逗号留前一行）；
中点后 10 字符内无标点则在中点硬切；42 字符以内不折；**只折一次**。
"""

from __future__ import annotations

from transcript_reimagined.domain.models import Segment
from transcript_reimagined.post.render import _wrap, to_srt


def _body_of(text: str) -> str:
    """取出 SRT 里的正文（正文可能已经是两行）。"""
    return to_srt([Segment(start=0.0, end=1.0, text=text)]).split("\n", 2)[2].rstrip("\n")


def test_rule_135_sixty_char_line_breaks_after_the_punctuation_past_the_midpoint():
    text = "甲" * 30 + "，" + "乙" * 29  # 60 字符，逗号正好在中点（下标 30）

    assert len(text) == 60
    first, second = _body_of(text).splitlines()
    assert first == "甲" * 30 + "，", "逗号留在前一行"
    assert second == "乙" * 29


def test_rule_135_punctuation_three_chars_past_the_midpoint_is_used():
    """判据原文：中点之后 3 个字符处有逗号 → 在那个逗号后断。"""
    text = "甲" * 30 + "乙丙丁" + "，" + "戊" * 20
    first, second = _body_of(text).splitlines()
    assert first == "甲" * 30 + "乙丙丁" + "，"
    assert second == "戊" * 20


def test_rule_135_no_punctuation_within_ten_chars_of_the_midpoint_hard_cuts():
    text = "甲" * 30 + "乙" * 30
    first, second = _body_of(text).splitlines()
    assert first == "甲" * 30
    assert second == "乙" * 30


def test_rule_135_punctuation_ten_chars_past_the_midpoint_is_not_used():
    """窗口是**之后 10 个字符**（下标 mid..mid+9），第 11 个字符不算。"""
    text = "甲" * 30 + "乙" * 10 + "，" + "丙" * 19
    first, second = _body_of(text).splitlines()
    assert first == "甲" * 30
    assert second == "乙" * 10 + "，" + "丙" * 19


def test_rule_135_forty_two_chars_is_not_wrapped():
    text = "甲" * 42
    assert "\n" not in _body_of(text).rstrip("\n")


def test_rule_135_only_one_split_is_ever_made():
    text = "超" * 300
    parts = _body_of(text).splitlines()
    assert len(parts) == 2
    assert len(parts[0]) == 150  # 中点硬切，不迭代
    assert len(parts[1]) == 150


def test_rule_135_full_width_and_half_width_punctuation_both_work():
    for punct in "，,。；;、：:！？!?":
        assert _wrap("甲" * 30 + punct + "乙" * 40).count("\n") == 1, punct


def test_rule_135_text_is_stripped_before_measuring():
    assert _wrap("  短  ") == "短"
