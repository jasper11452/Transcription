"""``RULE-022`` —— 替换顺序与变更计数。

判据：规则 ``集成→集诚`` 与 ``成→诚``、文本 ``我们把集成做完了`` → ``集成`` 先替
（2 字先于 1 字）得 ``我们把集诚做完了``；``成`` 已无匹配故不再改；``changes`` 记录 1 次；
计数只统计**实际替换处数**。
"""

from __future__ import annotations

from transcript_reimagined.domain.models import Rule
from transcript_reimagined.post.glossary import apply_rules, change_comment, parse_glossary

TEXT = "我们把集成做完了"


def test_rule_022_longest_wrong_spelling_is_replaced_first():
    rules = parse_glossary("集成 -> 集诚\n成 -> 诚")
    out, changes = apply_rules(TEXT, rules)
    assert out == "我们把集诚做完了"
    assert [(c.wrong, c.right, c.count) for c in changes] == [("集成", "集诚", 1)]


def test_rule_022_count_is_the_number_of_occurrences_actually_replaced():
    rules = parse_glossary("艾麦 -> 集诚")
    out, changes = apply_rules("艾麦、艾麦、还是艾麦。", rules)
    assert out == "集诚、集诚、还是集诚。"
    assert [(c.wrong, c.right, c.count) for c in changes] == [("艾麦", "集诚", 3)]


def test_rule_022_rules_that_do_not_match_are_not_reported():
    out, changes = apply_rules("没有错字", parse_glossary("艾麦 -> 集诚"))
    assert out == "没有错字"
    assert changes == []


def test_rule_022_a_rule_never_runs_twice_on_the_same_text():
    """替换是单向的：替换后的文本不会再被同一条规则匹配一次。"""
    rules = parse_glossary("集成 -> 集成部")
    out, changes = apply_rules(TEXT, rules)
    assert out == "我们把集成部做完了"
    assert changes[0].count == 1


def test_rule_022_result_does_not_depend_on_the_rule_list_order():
    forward = [Rule("集成", "集诚"), Rule("成", "诚")]
    backward = [Rule("成", "诚"), Rule("集成", "集诚")]
    assert apply_rules(TEXT, forward)[0] == apply_rules(TEXT, backward)[0]


def test_rule_022_no_rules_leaves_the_text_untouched():
    assert apply_rules(TEXT, []) == (TEXT, [])


def test_rule_022_change_comment_is_only_emitted_when_something_changed():
    _, changes = apply_rules("艾麦、艾麦、艾麦", parse_glossary("艾麦 -> 集诚"))
    comment = change_comment(changes)
    assert len(comment) == 1
    assert "艾麦→集诚 ×3" in comment[0]
    assert "原始转写见 .raw.json" in comment[0]
    assert change_comment([]) == []
