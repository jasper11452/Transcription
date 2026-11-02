"""``RULE-025`` —— SRT 时间戳格式与取整。

判据：段边界 59.9996s → 毫秒取整到 1000 并**进位**得 ``00:01:00,000``（**绝不**
``00:00:59,1000``）；负数渲染为 ``00:00:00,000``。

取整语义（人裁定，``AI_NATIVE_SPEC.md`` §6b）：「改注释，代码不变」—— Python 的
``round()`` 是 round-half-to-even，代码行为正确，失真的是「四舍五入进位」这句注释。
**这不是缺陷修复项**，因此这里断言的是现行为。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.domain.models import Segment, fmt_timestamp
from transcript_reimagined.post.render import to_srt


def test_rule_025_carry_never_produces_a_thousand_millisecond_field():
    assert fmt_timestamp(59.9996) == "00:01:00,000"
    assert fmt_timestamp(3599.9999) == "01:00:00,000"


def test_rule_025_negative_times_clamp_to_zero():
    assert fmt_timestamp(-1.0) == "00:00:00,000"
    assert fmt_timestamp(-0.0001) == "00:00:00,000"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00,000"),
        (0.001, "00:00:00,001"),
        (1.5, "00:00:01,500"),
        (60.0, "00:01:00,000"),
        (3600.0, "01:00:00,000"),
        (86399.999, "23:59:59,999"),
    ],
)
def test_rule_025_zero_padding_and_field_widths(seconds, expected):
    """小时/分/秒补到 2 位，毫秒补到 3 位。"""
    assert fmt_timestamp(seconds) == expected


def test_rule_025_exact_half_millisecond_uses_pythons_tie_break():
    """裁定保留的实现细节：精确的半个毫秒走 round-half-to-even。

    这条是**已接受的等价行为**（人裁定「改注释，代码不变」），不是缺陷 ——
    断言它，是为了让以后「顺手改成 half-up」的人先看到这份记录。
    """
    assert fmt_timestamp(1.0005) == "00:00:01,000"  # 0.5 → 0（偶）
    assert fmt_timestamp(1.0015) == "00:00:01,002"  # 1.5 → 2（偶）


def test_rule_025_separator_is_a_parameter():
    assert fmt_timestamp(61.25, sep=".") == "00:01:01.250"


def test_rule_025_srt_bodies_use_the_same_format():
    srt = to_srt([Segment(start=59.9996, end=69.9996, text="结尾")])
    assert "00:01:00,000 --> 00:01:10,000" in srt
    assert ",1000" not in srt
