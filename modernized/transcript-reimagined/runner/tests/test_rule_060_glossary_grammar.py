"""``RULE-060`` —— 词表语法与条目校验。

判据来自 ``AI_NATIVE_SPEC.md`` §5.2 的 6 行样本：
``小新`` / ``艾麦 -> 集诚`` / ``-> 集诚`` / ``集诚 = 集诚`` / ``艾麦 -> 集成`` /
``艾麦 => 艾麦科技  # 公司简称``
→ 裸热词合法；``艾麦 -> 集诚`` 成规则；``-> 集诚`` 与 ``集诚 = 集诚`` 报问题；
重复错词报「已在第 N 行定义」且**首次定义生效**；``#`` 仅在行首或前置空白时才算注释。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.domain.models import Rule
from transcript_reimagined.post.glossary import (
    is_hot_word_line,
    parse_glossary,
    parse_glossary_report,
    parse_hot_words,
    split_entries,
)

SAMPLE = "小新\n艾麦 -> 集诚\n-> 集诚\n集诚 = 集诚\n艾麦 -> 集成\n艾麦 => 艾麦科技  # 公司简称\n"


def test_rule_060_sample_reports_the_known_problems_per_line():
    """判据里的「两处问题」是同类问题的两个代表；逐行断言才是完整结果。

    第 5、6 行的 ``艾麦`` 是第 2 行已定义的重复错词，因此同样被报出来 —— 与
    「重复错词报已在第 N 行定义」是同一条规则，不是新的行为。
    """
    rules, issues = parse_glossary_report(SAMPLE)
    assert rules == [Rule(wrong="艾麦", right="集诚")], "只有第 2 行成了规则"
    assert [issue.line for issue in issues] == [3, 4, 5, 6]
    assert [parse_glossary_report(SAMPLE)], "报告与解析必须是同一次解析的两个视图"
    assert "已在第 2 行定义" in issues[2].message
    assert "已在第 2 行定义" in issues[3].message
    assert "公司简称" not in SAMPLE.splitlines()[5].split("#")[0], "行内注释必须被剥掉"


def test_rule_060_empty_side_is_reported_not_silently_ignored():
    issues = parse_glossary_report("-> 集诚")[1]
    assert [issue.line for issue in issues] == [1]
    assert "都要填写" in issues[0].message


def test_rule_060_identical_sides_are_reported():
    issues = parse_glossary_report("集诚 = 集诚")[1]
    assert [issue.line for issue in issues] == [1]
    assert "不能相同" in issues[0].message


def test_rule_060_duplicate_wrong_spelling_is_reported_with_the_first_line():
    issues = parse_glossary_report("艾麦 -> 集诚\n艾麦 -> 集成")[1]
    assert len(issues) == 1
    assert "已在第 1 行定义" in issues[0].message


def test_rule_060_the_first_definition_wins():
    """重复错词：首次定义生效，后面的不覆盖 —— 解析结果与顺序无关。"""
    rules = parse_glossary("艾麦 -> 集诚\n艾麦 -> 集成")
    assert rules == [Rule(wrong="艾麦", right="集诚")]


def test_rule_060_bare_hot_word_is_legal_and_not_a_rule():
    rules, issues = parse_glossary_report("小新")
    assert rules == []
    assert issues == []
    assert parse_hot_words("小新") == ["小新"]


def test_rule_060_comment_hash_counts_only_at_line_start_or_after_whitespace():
    """``#`` 只有位于行首或前面有空白才起注释作用，否则是词条的一部分。"""
    assert is_hot_word_line("# 整行注释") is False
    assert is_hot_word_line("   # 缩进的注释") is False
    assert is_hot_word_line("") is False
    assert is_hot_word_line("   ") is False
    # C# 这类带 # 的词条不是注释
    assert is_hot_word_line("C#") is True
    assert parse_hot_words("C#") == ["C#"]
    # 行内注释被剥掉，前面的词条保留
    assert parse_hot_words("小新   # 人名") == ["小新"]
    assert parse_glossary("艾麦 -> 集诚   # 公司简称") == [Rule(wrong="艾麦", right="集诚")]


def test_rule_060_every_declared_separator_works():
    """分隔符按顺序探测：``->`` ``=>`` ``→`` ``=`` 制表符 ``|``，首个命中者胜。"""
    for line in ("艾麦->集诚", "艾麦=>集诚", "艾麦→集诚", "艾麦=集诚", "艾麦\t集诚", "艾麦|集诚"):
        assert parse_glossary(line) == [Rule(wrong="艾麦", right="集诚")], line


def test_rule_060_separator_search_runs_before_the_hot_word_test():
    """已知的解析顺序（legacy 行为，逐字节等价保留）：分隔符先找，裸词后判。

    分隔符集合是 ``->`` ``=>`` ``→`` ``=`` 制表符 ``|`` —— 含 ``/`` 的词条（如
    ``小新/小旧``）**不是**规则，是合法裸词；含 ``=`` 的才会被切成规则。
    """
    assert is_hot_word_line("小新/小旧") is True
    assert parse_hot_words("小新/小旧") == ["小新/小旧"]
    assert is_hot_word_line("小新=小旧") is False
    assert parse_glossary("小新=小旧") == [Rule(wrong="小新", right="小旧")]


def test_rule_060_split_entries_reports_line_numbers_of_the_original_text():
    entries = split_entries("\n# 注释\n小新\n艾麦 -> 集诚\n")
    assert entries == [(3, "小新", None), (4, "艾麦", "集诚")]


def test_rule_060_blank_and_comment_lines_are_skipped_without_issues():
    rules, issues = parse_glossary_report("\n\n   \n# 只有注释\n")
    assert rules == []
    assert issues == []


@pytest.mark.parametrize("empty", ["", "\n\n", "# 什么都没有\n"])
def test_rule_060_empty_glossary_yields_nothing_and_no_error(empty):
    assert parse_glossary_report(empty) == ([], [])
