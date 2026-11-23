"""RULE-060 —— 词表语法与条目校验。

规则卡 Given（`BUSINESS_RULES.md` §RULE-060 / `AI_NATIVE_SPEC.md` §5.2）用的 6 行样本：
`小新` / `艾麦 -> 集诚` / `-> 集诚` / `集诚 = 集诚` / `艾麦 -> 集成` / `艾麦 => 艾麦科技  # 公司简称`

本模板**保留** legacy 的判定顺序（缺边 → 同词 → 重复），即第 5、6 行都报「已在第 2 行定义」，
而**不是**报与第 5 行重复。改这个优先级属于行为变更，需先回规格。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import (
    GlossaryIssue,
    GlossaryRule,
    is_hot_word_line,
    parse_glossary,
    parse_glossary_report,
    parse_hot_words,
    split_entries,
)

SAMPLE_6_LINES = (
    "小新\n艾麦 -> 集诚\n-> 集诚\n集诚 = 集诚\n艾麦 -> 集成\n艾麦 => 艾麦科技  # 公司简称\n"
)


@pytest.mark.rule("RULE-060")
class TestRule060SixLineSample:
    """规则卡里那 6 行样本的逐行判据。"""

    def test_bare_hot_word_is_legal_and_not_a_rule(self):
        rules, issues = parse_glossary_report(SAMPLE_6_LINES)
        # 裸热词不产生规则，也不产生问题。
        assert "小新" not in [r.wrong for r in rules]
        assert parse_hot_words(SAMPLE_6_LINES) == ["小新"]

    def test_rule_line_becomes_a_rule(self):
        rules = parse_glossary(SAMPLE_6_LINES)
        assert rules == [GlossaryRule(wrong="艾麦", right="集诚")]

    @pytest.mark.parametrize(
        ("line", "message"),
        [
            (3, "错词和正确词都要填写"),
            (4, "错词和正确词不能相同"),
            (5, "“艾麦”已在第 2 行定义"),
            (6, "“艾麦”已在第 2 行定义"),
        ],
    )
    def test_malformed_and_duplicate_lines_are_reported_with_line_number(self, line, message):
        _, issues = parse_glossary_report(SAMPLE_6_LINES)
        assert GlossaryIssue(line, message) in issues

    def test_every_problem_line_is_named(self):
        _, issues = parse_glossary_report(SAMPLE_6_LINES)
        assert [i.line for i in issues] == [3, 4, 5, 6]

    def test_first_definition_wins(self):
        rules, _ = parse_glossary_report(SAMPLE_6_LINES)
        assert [(r.wrong, r.right) for r in rules] == [("艾麦", "集诚")]

    def test_trailing_comment_is_stripped_only_because_hash_follows_whitespace(self):
        # 第 6 行的 `# 公司简称` 前有空白，因此整段尾巴是注释。
        rules, issues = parse_glossary_report(SAMPLE_6_LINES)
        assert "公司简称" not in [r.right for r in rules]
        # 重复检查发生在注释剥离之后，所以行 6 报的是重复而不是「词里带 #」。
        assert [i.line for i in issues] == [3, 4, 5, 6]


@pytest.mark.rule("RULE-060")
class TestRule060Grammar:
    @pytest.mark.parametrize(
        "line",
        ["艾麦 -> 集诚", "艾麦 => 集诚", "艾麦 → 集诚", "艾麦 = 集诚", "艾麦\t集诚", "艾麦 | 集诚"],
    )
    def test_all_separators_are_accepted(self, line):
        assert parse_glossary(line) == [GlossaryRule("艾麦", "集诚")]

    def test_blank_and_comment_lines_are_skipped(self):
        rules, issues = parse_glossary_report("\n# 专名表\n   \n小新\n")
        assert (rules, issues) == ([], [])

    def test_hash_only_starts_a_comment_at_line_start_or_after_whitespace(self):
        # 行首 / 前有空白 → 注释，被剥掉。
        assert parse_glossary("艾麦 -> 集诚  # 说明") == [GlossaryRule("艾麦", "集诚")]
        assert parse_glossary("艾麦 -> 集诚\t# 说明") == [GlossaryRule("艾麦", "集诚")]
        # 紧贴词条的 `#` 属于词条本身。
        assert parse_glossary("艾麦 -> 集诚#标签") == [GlossaryRule("艾麦", "集诚#标签")]

    def test_split_entries_returns_line_numbers_and_none_for_bare_words(self):
        assert split_entries("小新\n艾麦 -> 集诚\n") == [
            (1, "小新", None),
            (2, "艾麦", "集诚"),
        ]

    @pytest.mark.parametrize(
        ("line", "expected"),
        [("小新", True), ("艾麦 -> 集诚", False), ("# 注释", False), ("   ", False)],
    )
    def test_is_hot_word_line(self, line, expected):
        assert is_hot_word_line(line) is expected

    def test_bare_hot_words_are_deduped_in_first_seen_order(self):
        assert parse_hot_words("小新\n选号侠\n小新\n") == ["小新", "选号侠"]

    def test_empty_left_or_right_after_stripping_is_rejected(self):
        rules, issues = parse_glossary_report("艾麦 ->   \n  -> 集诚\n")
        assert rules == []
        assert [i.line for i in issues] == [1, 2]
