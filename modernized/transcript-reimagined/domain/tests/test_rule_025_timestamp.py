"""`RULE-025` — SRT 时间戳格式与取整（`transcript_reimagined.domain.models.fmt_timestamp`）。

规则卡（`AI_NATIVE_SPEC.md` §5.2）：
    58 段边界 59.9996s → 毫秒四舍五入到 1000 并**进位**得 `00:01:00,000`
    （**绝不** `00:00:59,1000`）；负数渲染为 `00:00:00,000`。

人裁定（`AI_NATIVE_SPEC.md` §6b）：**改注释，代码不变** —— Python 的 `round()` 是
round-half-to-even，注释里「四舍五入进位」的措辞失真，代码行为是正确的。
因此本文件既断言行为，也断言注释措辞与真实语义一致。
"""

from __future__ import annotations

import inspect

import pytest

from transcript_reimagined.domain import fmt_timestamp

pytestmark = pytest.mark.rule("RULE-025")


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00,000"),
        (0.5, "00:00:00,500"),
        (1.0, "00:00:01,000"),
        (1.25, "00:00:01,250"),
        (5.007, "00:00:05,007"),
        (59.0, "00:00:59,000"),
        (59.9996, "00:01:00,000"),
        (60.0, "00:01:00,000"),
        (3599.9999, "01:00:00,000"),
        (3600.0, "01:00:00,000"),
        (3661.25, "01:01:01,250"),
        (359999.4, "99:59:59,400"),  # 小时位不截断
        (359999.9996, "100:00:00,000"),  # 进位可以跨过 100 小时
    ],
)
def test_rule_025_renders_hh_mm_ss_mmm(seconds: float, expected: str) -> None:
    assert fmt_timestamp(seconds) == expected


def test_rule_025_millisecond_1000_carries_instead_of_overflowing() -> None:
    """59.9996s 的关键点：毫秒位进位，绝不产出 4 位毫秒的 `00:00:59,1000`。"""
    out = fmt_timestamp(59.9996)
    assert out == "00:01:00,000"
    assert out != "00:00:59,1000"
    # 毫秒段恒为 3 位；逗号恒存在（SRT 语法）
    assert len(out.split(",")[1]) == 3


@pytest.mark.parametrize("seconds", [-0.0001, -0.5, -1.0, -59.9996, -3600.0])
def test_rule_025_negative_seconds_render_as_zero(seconds: float) -> None:
    assert fmt_timestamp(seconds) == "00:00:00,000"


def test_rule_025_just_below_the_carry_stays_on_the_previous_second() -> None:
    """进位只发生在取整后的毫秒数恰好为 1000 时，不能提前进。"""
    assert fmt_timestamp(59.9994) == "00:00:59,999"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0005, "00:00:00,000"),  # 0.5 毫秒 → 取偶 → 0
        (0.0015, "00:00:00,002"),  # 1.5 毫秒 → 取偶 → 2
        (0.0025, "00:00:00,002"),  # 2.5 毫秒 → 取偶 → 2
        (0.0035, "00:00:00,004"),  # 3.5 毫秒 → 取偶 → 4
    ],
)
def test_rule_025_rounding_is_half_to_even_not_half_up(seconds: float, expected: str) -> None:
    """人裁定保留的现行为：精确半毫秒取偶，不是 half-up。

    这条测试的作用是把「注释失真」冻结成可执行事实 —— 将来谁把注释当成
    「四舍五入」去改代码，这条会红。
    """
    assert fmt_timestamp(seconds) == expected


def test_rule_025_rounding_comment_states_half_to_even() -> None:
    """裁定是「改注释，代码不变」—— 所以派人检查注释本身。

    legacy 注释写的是「四舍五入进位」（half-up），与 `round()` 的真实语义
    （round-half-to-even）不符。重建版必须如实说明，并显式点出这不是缺陷修复项。
    """
    doc = inspect.getdoc(fmt_timestamp) or ""
    assert "round-half-to-even" in doc, "注释必须点名真实取整语义"
    assert "半值取偶" in doc, "注释必须用中文说出同一件事"
    assert "四舍五入" not in doc or "不是" in doc, "不得把取整描述成 half-up"
    # 关键场景仍要在 docstring 里留痕，避免注释在搬运中失传
    assert "59.9996" in doc
    assert "00:00:59,1000" in doc


def test_rule_025_separator_is_a_keyword_only_parameter() -> None:
    """`sep` 默认 ','（SRT），但可切换 —— 且必须关键字传入。"""
    assert fmt_timestamp(1.5, sep=".") == "00:00:01.500"
    with pytest.raises(TypeError):
        fmt_timestamp(1.5, ".")  # type: ignore[misc]  # 位置传入必须被拒绝
