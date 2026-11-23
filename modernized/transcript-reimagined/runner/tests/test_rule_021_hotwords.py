"""``RULE-021`` —— 热词列表组成与上限。

判据：词表含裸词 ``小新`` ``集成`` 与规则 ``艾麦 -> 集诚`` → 列表为
``['小新','集成','集诚','艾麦']``（裸词在前，每条规则的**正确写法在前、错词在后**，
去重保首次）；总结用时限 40 字符/词、80 词。
"""

from __future__ import annotations

from transcript_reimagined.post.glossary import (
    MAX_HOT_WORD_CHARS,
    MAX_HOT_WORDS,
    cap_hot_words_for_summary,
    hotwords,
    parse_glossary,
    parse_hot_words,
)

SPEC_GLOSSARY = "小新\n集成\n艾麦 -> 集诚\n"


def test_rule_021_spec_list_composition():
    """裸词在前；随后每条规则先正确写法、再错词写法；重复项保首次。"""
    rules = parse_glossary(SPEC_GLOSSARY)
    bare = parse_hot_words(SPEC_GLOSSARY)
    assert hotwords(rules, extra=bare) == ["小新", "集成", "集诚", "艾麦"]


def test_rule_021_bare_words_come_before_rule_spellings():
    rules = parse_glossary("艾麦 -> 集诚")
    assert hotwords(rules, extra=["小新"]) == ["小新", "集诚", "艾麦"]


def test_rule_021_dedupe_keeps_the_first_occurrence():
    rules = parse_glossary("艾麦 -> 集成")
    # 裸词里已有「集成」，规则的 right 也是「集成」 → 只留一次，且仍在裸词的位置
    assert hotwords(rules, extra=["集成", "小新"]) == ["集成", "小新", "艾麦"]


def test_rule_021_empty_or_missing_glossary_yields_no_hot_words():
    assert hotwords(parse_glossary("")) == []
    assert hotwords(parse_glossary("# 只有注释\n")) == []
    assert parse_hot_words("") == []


def test_rule_021_summary_caps_are_forty_chars_and_eighty_words():
    assert (MAX_HOT_WORD_CHARS, MAX_HOT_WORDS) == (40, 80)
    long_word = "超" * 60
    capped = cap_hot_words_for_summary([long_word, "小新", *[f"w{i}" for i in range(200)]])
    assert len(capped) == MAX_HOT_WORDS
    assert len(capped[0]) == MAX_HOT_WORD_CHARS
    assert capped[:2] == ["超" * 40, "小新"]


def test_rule_021_engine_path_is_not_truncated_by_the_summary_caps():
    """总结的截断是**显式**的一步；引擎热词路径拿到完整词与完整列表。"""
    word = "超" * 60
    words = hotwords(parse_glossary(""), extra=[word])
    assert words == [word]
    assert len(cap_hot_words_for_summary(words)[0]) == 40
