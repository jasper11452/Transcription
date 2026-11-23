"""RULE-021 —— 热词列表组成与上限（引擎热词 + 总结用词）。

规则卡 Given：词表含裸词 `小新` `集成` 与规则 `艾麦 -> 集诚`
→ 列表为 `['小新','集成','集诚','艾麦']`（裸词在前，每条规则的**正确写法在前、错词在后**，
去重保首次）；总结用时限 40 字符/词、80 词（NFR-8，实现时不得放宽）。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post import (
    SUMMARY_MAX_HOT_WORD_CHARS,
    SUMMARY_MAX_HOT_WORDS,
    GlossaryRule,
    cap_hot_words_for_summary,
    hotwords,
    parse_glossary,
    parse_hot_words,
)

GIVEN_GLOSSARY = "小新\n集成\n艾麦 -> 集诚\n"


@pytest.mark.rule("RULE-021")
class TestRule021Composition:
    def test_caps_are_not_relaxed(self):
        # 上限是 NFR-8 的承诺，改这两个数就是行为变更。
        assert SUMMARY_MAX_HOT_WORDS == 80
        assert SUMMARY_MAX_HOT_WORD_CHARS == 40

    def test_bare_words_first_then_right_then_wrong(self):
        bare = parse_hot_words(GIVEN_GLOSSARY)
        rules = parse_glossary(GIVEN_GLOSSARY)
        assert bare == ["小新", "集成"]
        assert hotwords(rules, extra=bare) == ["小新", "集成", "集诚", "艾麦"]

    def test_order_is_bare_then_right_then_wrong_per_rule(self):
        rules = [GlossaryRule("艾麦", "集诚"), GlossaryRule("佳路", "嘉鹿")]
        assert hotwords(rules) == ["集诚", "艾麦", "嘉鹿", "佳路"]

    def test_dedupe_keeps_first_occurrence(self):
        rules = [GlossaryRule("艾麦", "集诚")]
        # 裸词里已出现「集诚」，规则的正确写法不再重复入列。
        assert hotwords(rules, extra=["集诚", "小新"]) == ["集诚", "小新", "艾麦"]

    def test_normalizing_a_rule_does_not_add_it(self):
        # 错词与正确写法相同不是规则，热词表里只出现一次。
        rules = [GlossaryRule("集成", "集成")]
        assert hotwords(rules) == ["集成"]

    def test_limit_truncates_from_the_tail(self):
        rules = [GlossaryRule("艾麦", "集诚"), GlossaryRule("佳路", "嘉鹿")]
        assert hotwords(rules, extra=["小新"], limit=3) == ["小新", "集诚", "艾麦"]

    def test_empty_glossary_yields_no_hot_words(self):
        assert hotwords([], extra=parse_hot_words("")) == []


@pytest.mark.rule("RULE-021")
class TestRule021SummaryCaps:
    def test_word_longer_than_40_chars_is_truncated(self):
        long_word = "甲" * 50
        assert cap_hot_words_for_summary([long_word]) == ["甲" * 40]

    def test_list_is_capped_at_80_words_keeping_the_front(self):
        words = [f"词{i:03d}" for i in range(120)]
        capped = cap_hot_words_for_summary(words)
        assert len(capped) == 80
        assert capped[0] == "词000"
        assert capped[-1] == "词079"

    def test_blank_words_are_dropped(self):
        assert cap_hot_words_for_summary(["小新", "   ", ""]) == ["小新"]
