"""渲染与词表单测。"""

from __future__ import annotations

import re

from transcript.align import normalize_for_compare
from transcript.glossary import (
    Change,
    Rule,
    apply_rules,
    change_comment,
    hotwords,
    is_hot_word_line,
    parse_glossary,
    parse_glossary_report,
    parse_hot_word_groups,
    parse_hot_words,
)
from transcript.models import Segment
from transcript.render import parse_srt, to_srt, to_txt

SRT_TIME = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$")


# ---------- SRT ----------


def test_srt_format_is_valid():
    segs = [Segment(0.0, 2.5, "第一句。"), Segment(2.5, 65.25, "第二句。")]
    lines = to_srt(segs).strip().splitlines()
    assert lines[0] == "1"
    assert SRT_TIME.match(lines[1])
    assert lines[2] == "第一句。"
    assert lines[3] == ""
    assert lines[4] == "2"
    assert SRT_TIME.match(lines[5])


def test_srt_timestamps_roll_over_correctly():
    """59.9996s 这类边界不能出现 00:01:00,1000。"""
    srt = to_srt([Segment(0.0, 59.9996, "边界")])
    assert "00:01:00,000" in srt
    assert "1000" not in srt


def test_srt_skips_empty_segments_and_keeps_numbering_continuous():
    segs = [Segment(0.0, 1.0, "甲"), Segment(1.0, 2.0, "   "), Segment(2.0, 3.0, "乙")]
    srt = to_srt(segs)
    assert "\n1\n" in "\n" + srt
    assert "2\n00:00:02,000" in srt
    assert "乙" in srt


def test_srt_rejects_reversed_time():
    """宁可直接失败，也不写出播放器会丢弃的坏字幕。"""
    try:
        to_srt([Segment(5.0, 1.0, "倒序")])
    except ValueError as exc:
        assert "倒序" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("时间倒序必须报错")


def test_srt_wraps_long_lines():
    long_text = "这是一句很长的字幕内容，需要在标点处折成两行，避免被播放器压扁成不可读的一整行。"
    srt = to_srt([Segment(0.0, 5.0, long_text)])
    body = srt.strip().splitlines()[2:]
    assert len(body) <= 2
    assert all(len(line) <= 42 for line in body)


def test_srt_comment_lines_are_prefixed():
    srt = to_srt([Segment(0.0, 1.0, "甲")], comment_lines=["词表替换：甲→乙 ×1"])
    assert srt.startswith("# 词表替换：甲→乙 ×1")


def test_txt_prefers_segments_then_raw_text():
    segs = [Segment(0.0, 1.0, "甲。"), Segment(1.0, 2.0, "乙。")]
    assert to_txt("忽略我", segs).strip() == "甲。\n乙。"
    assert to_txt("只有正文", []).strip() == "只有正文"


def test_txt_with_no_content_is_empty_not_blank_noise():
    assert to_txt("", []) == ""


def test_two_transcripts_differ_only_in_punctuation():
    """spec 的一致性判据：归一化后应相同（差异只在标点）或明显不同。"""
    assert normalize_for_compare("转录工具冒烟测试。") == normalize_for_compare(
        "转录工具冒烟测试，"
    )
    assert normalize_for_compare("转录工具冒烟测试。") != normalize_for_compare(
        "转录工具冒烟测试补充内容。"
    )


# ---------- 词表 ----------


def test_parse_glossary_supports_multiple_separators_and_comments():
    text = """
    # 专名表
    艾麦 -> 砹脉
    佳路 => 嘉鹿
    集成 → 即创
    冒烟测试 = 冒烟测试2
    空 ->   # 右值为空，忽略
    """
    rules = parse_glossary(text)
    pairs = {(r.wrong, r.right) for r in rules}
    assert ("艾麦", "砹脉") in pairs
    assert ("佳路", "嘉鹿") in pairs
    assert ("集成", "即创") in pairs
    assert all(r.wrong and r.right for r in rules)
    assert len(rules) == 4


def test_parse_glossary_report_names_every_silently_ignored_line():
    rules, issues = parse_glossary_report(
        "艾麦 -> 砹脉\n小新\n艾麦 -> 另一个写法\n相同 -> 相同\n"
    )
    assert rules == [Rule("艾麦", "砹脉")]
    assert [issue.line for issue in issues] == [3, 4]
    assert "第 1 行" in issues[0].message
    assert "不能相同" in issues[1].message


def test_hot_word_lines_are_valid_not_issues():
    """裸热词（只写正确写法）是合法写法，不该被当成缺分隔符的错行。"""
    text = "# 词表\n小新\n选号侠\n艾麦 -> 砹脉\n小新\n"
    rules, issues = parse_glossary_report(text)
    assert issues == []
    assert rules == [Rule("艾麦", "砹脉")]
    assert parse_hot_words(text) == ["小新", "选号侠"]
    assert is_hot_word_line("小新") is True
    assert is_hot_word_line("艾麦 -> 砹脉") is False
    assert is_hot_word_line("# 注释") is False
    assert is_hot_word_line("   ") is False


def test_hotwords_puts_bare_words_first():
    words = hotwords([Rule("艾麦", "砹脉")], extra=["小新"])
    assert words == ["小新", "砹脉", "艾麦"]


def test_parse_hot_word_groups_keeps_order_legacy_words_and_empty_groups():
    text = "# 普通注释\n旧词\n## 产品 # 说明\n小新\n小新\n## 客户\n选号侠\n## 空组\n### 不是分组\n"
    groups = parse_hot_word_groups(text)
    assert [(group.name, group.words) for group in groups] == [
        ("", ("旧词",)),
        ("产品", ("小新",)),
        ("客户", ("选号侠",)),
        ("空组", ()),
    ]


def test_apply_rules_is_deterministic_and_counts():
    rules = [Rule("艾麦", "砹脉"), Rule("佳路", "嘉鹿")]
    out, changes = apply_rules("艾麦和佳路，还有艾麦。", rules)
    assert out == "砹脉和嘉鹿，还有砹脉。"
    counts = {c.wrong: c.count for c in changes}
    assert counts == {"艾麦": 2, "佳路": 1}


def test_apply_rules_prefers_longer_wrong_words():
    """短词先替换会把长词切碎，导致长词再也匹配不上。"""
    rules = [Rule("集成", "即创"), Rule("集成平台", "即创平台")]
    out, changes = apply_rules("集成平台发布了集成方案", rules)
    assert out == "即创平台发布了即创方案"
    assert {c.wrong for c in changes} == {"集成平台", "集成"}


def test_apply_rules_no_match_is_noop():
    out, changes = apply_rules("完全干净的文本。", [Rule("艾麦", "砹脉")])
    assert out == "完全干净的文本。"
    assert changes == []


def test_hotwords_includes_both_spellings():
    words = hotwords([Rule("艾麦", "砹脉")])
    assert words == ["砹脉", "艾麦"]


def test_change_comment_is_empty_without_changes():
    assert change_comment([]) == []
    assert "艾麦→砹脉 ×2" in change_comment([Change("艾麦", "砹脉", 2)])[0]


def test_parse_srt_是_to_srt_的逆运算() -> None:
    """折行只插换行不插空格；解析必须原样拼回，否则每轮保存都会往正文里加空格。"""
    long_text = "这是一段超过四十二个字符的长字幕用来验证折行还原是否正确" * 2
    segments = [Segment(0.0, 2.0, "第一句"), Segment(2.0, 4.0, long_text)]
    parsed = parse_srt(to_srt(segments))
    assert [segment.text for segment in parsed] == ["第一句", long_text]
    # 正文以 # 开头不是注释，必须原样读回
    assert [segment.text for segment in parse_srt(to_srt([Segment(0.0, 1.0, "#话题")]))] == ["#话题"]
    assert [round(segment.start, 3) for segment in parsed] == [0.0, 2.0]
