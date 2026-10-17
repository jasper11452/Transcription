"""RULE-022 —— 替换顺序与变更计数。

规则卡 Given：规则 `集成→集诚` 与 `成→诚`、文本 `我们把集成做完了`
→ `集成` 先替（2 字先于 1 字）得 `我们把集诚做完了`；`成` 已无匹配故不再改；
`changes` 记录 1 次；计数只统计**实际替换处数**。

两条与 legacy 逐字一致的既有语义（规则卡 `Parameters` 明写「rules are never applied
twice to the same text」）：

1. 同一条规则只跑一遍 `str.replace`，它自己产出的文本不会被它自己复扫；
2. 但后续（更短的）规则看到的是**已被前面规则改过**的文本 —— 替换是链式累积的。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import Change, GlossaryRule, apply_rules, change_comment, change_header_line

GIVEN_RULES = [GlossaryRule("集成", "集诚"), GlossaryRule("成", "诚")]


@pytest.mark.rule("RULE-022")
class TestRule022Given:
    def test_longest_wrong_word_first(self):
        out, changes = apply_rules("我们把集成做完了", GIVEN_RULES)
        assert out == "我们把集诚做完了"
        assert changes == [Change(wrong="集成", right="集诚", count=1)]

    def test_no_match_is_a_noop(self):
        out, changes = apply_rules("完全干净的文本。", GIVEN_RULES)
        assert (out, changes) == ("完全干净的文本。", [])

    def test_sort_key_is_wrong_length_descending(self):
        # 短词先替会把长词切碎，长词再也匹配不上。
        rules = [GlossaryRule("集成", "即创"), GlossaryRule("集成平台", "即创平台")]
        out, changes = apply_rules("集成平台发布了集成方案", rules)
        assert out == "即创平台发布了即创方案"
        assert [c.wrong for c in changes] == ["集成平台", "集成"]


@pytest.mark.rule("RULE-022")
class TestRule022Counting:
    def test_count_is_the_number_of_occurrences_actually_replaced(self):
        rules = [GlossaryRule("艾麦", "集诚"), GlossaryRule("佳路", "嘉鹿")]
        out, changes = apply_rules("艾麦和佳路，还有艾麦。", rules)
        assert out == "集诚和嘉鹿，还有集诚。"
        assert {c.wrong: c.count for c in changes} == {"艾麦": 2, "佳路": 1}

    def test_a_rule_is_never_applied_twice_to_the_same_text(self):
        # 一次替换后文本里已无「成」以外的匹配面：结果幂等，第二次调用不再产生变更。
        out, _ = apply_rules("我们把集成做完了", GIVEN_RULES)
        again, changes = apply_rules(out, GIVEN_RULES)
        assert again == out
        assert changes == []

    def test_a_later_shorter_rule_sees_the_earlier_rules_output(self):
        # 长词先替（甲乙→甲乙丙），随后短词（丙→丁）在**已改过**的文本上生效。
        rules = [GlossaryRule("甲乙", "甲乙丙"), GlossaryRule("丙", "丁")]
        out, changes = apply_rules("甲乙", rules)
        assert out == "甲乙丁"
        assert [(c.wrong, c.count) for c in changes] == [("甲乙", 1), ("丙", 1)]


@pytest.mark.rule("RULE-022")
class TestRule022ChangeDescription:
    def test_describe_format_is_wrong_arrow_right_times_n(self):
        assert Change("艾麦", "集诚", 3).describe() == "艾麦→集诚 ×3"

    def test_header_line_lists_every_change(self):
        line = change_header_line([Change("艾麦", "集诚", 3), Change("佳路", "嘉鹿", 1)])
        assert line == "词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3，佳路→嘉鹿 ×1"

    def test_no_changes_means_no_header(self):
        assert change_header_line([]) == ""
        assert change_comment([]) == []
