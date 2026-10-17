"""Phase 1 的等价性证明：与 legacy 实现**双执行 diff**（方案书 §6 的 P1 主手段）。

legacy 快照是**只读基准**（``legacy/transcript/``，全程不改）。本文件把它当**预言机**
用：同一组输入分别喂给新旧实现，比较输出是否逐字节一致。它只 import 与调用纯函数，
不读凭据、不写文件、不碰 `state.db`。

快照不存在时**跳过**并说明原因 —— 这不是「通过」，而是「基准不在场，没查」。

注：legacy 版本快照里存在若干已知缺陷（`RULE-001` 的判据例子写错等）。本文件只比对
**本服务已实现的 11 条规则**所覆盖的函数，缺陷清单见 ``LEGACY_DEVIATIONS.md``。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _find_legacy_src() -> Path:
    """向上找 ``legacy/transcript/src``：基准快照的位置由仓库布局决定，不由本服务决定。"""
    for parent in ROOT.parents:
        candidate = parent / "legacy" / "transcript" / "src"
        if candidate.is_dir():
            return candidate
    return ROOT / "__no_legacy_snapshot__"


LEGACY_SRC = _find_legacy_src()


def _legacy(name: str):
    if not LEGACY_SRC.is_dir():
        pytest.skip(f"legacy 快照不在场：{LEGACY_SRC}（等价性未被执行）")
    if str(LEGACY_SRC) not in sys.path:
        sys.path.insert(0, str(LEGACY_SRC))
    return importlib.import_module(f"transcript.{name}")


CHUNK_CASES = [
    ([(0.0, 60.0), (61.2, 300.0)], 300.0, 30.0, 120.0, 0.5),
    ([(0.0, 400.0)], 400.0, 30.0, 120.0, 0.5),
    ([], 700.0, 30.0, 120.0, 0.5),
    ([(0.0, 320.0)], 320.0, 30.0, 300.0, 0.5),
    ([(0.0, 119.0), (120.4, 400.0)], 400.0, 30.0, 120.0, 0.5),
    ([], 20.0, 30.0, 120.0, 0.5),
    ([(0.0, 1200.0)], 1200.0, 30.0, 120.0, 0.5),
    ([(200.0, 400.0), (-5.0, 60.0), (61.2, 90.0)], 300.0, 30.0, 120.0, 0.5),
]


@pytest.mark.parametrize(("spans", "duration", "min_s", "max_s", "overlap_s"), CHUNK_CASES)
def test_plan_chunks_is_byte_for_byte_equivalent(spans, duration, min_s, max_s, overlap_s):
    legacy = _legacy("chunking")
    from transcript_reimagined.ingest.chunking import plan_chunks

    old = [
        (c.index, c.start, c.end)
        for c in legacy.plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    ]
    new = [
        (c.index, c.start, c.end)
        for c in plan_chunks(spans, duration, min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    ]
    assert new == old


TIMESTAMP_CASES = [
    0.0,
    0.001,
    1.0005,
    1.0015,
    1.5,
    59.9996,
    60.0,
    3599.9999,
    3600.0,
    86399.999,
    -1.0,
]


@pytest.mark.parametrize("seconds", TIMESTAMP_CASES)
def test_fmt_timestamp_is_byte_for_byte_equivalent(seconds):
    legacy = _legacy("models")
    from transcript_reimagined.domain.models import fmt_timestamp

    assert fmt_timestamp(seconds) == legacy.fmt_timestamp(seconds)
    assert fmt_timestamp(seconds, sep=".") == legacy.fmt_timestamp(seconds, sep=".")


GLOSSARY_CASES = [
    "",
    "小新",
    "小新\n艾麦 -> 集诚\n-> 集诚\n集诚 = 集诚\n艾麦 -> 集成\n艾麦 => 艾麦科技  # 公司简称\n",
    "艾麦->集诚",
    "艾麦=>集诚",
    "艾麦→集诚",
    "艾麦=集诚",
    "艾麦\t集诚",
    "艾麦|集诚",
    "小新/小旧",
    "C#",
    "小新   # 人名",
    "# 只有注释\n\n   \n",
    "  缩进的裸词  ",
]


@pytest.mark.parametrize("text", GLOSSARY_CASES)
def test_glossary_parsing_and_replacement_are_equivalent(text):
    legacy = _legacy("glossary")
    from transcript_reimagined.post.glossary import (
        apply_rules,
        is_hot_word_line,
        parse_glossary_report,
        parse_hot_words,
    )

    old_rules, old_issues = legacy.parse_glossary_report(text)
    new_rules, new_issues = parse_glossary_report(text)
    assert [(r.wrong, r.right) for r in new_rules] == [(r.wrong, r.right) for r in old_rules]
    assert [(i.line, i.message) for i in new_issues] == [(i.line, i.message) for i in old_issues]
    assert parse_hot_words(text) == legacy.parse_hot_words(text)
    assert is_hot_word_line(text.splitlines()[0] if text else "") == legacy.is_hot_word_line(
        text.splitlines()[0] if text else ""
    )

    sample = "我们把集成做完了。艾麦、艾麦。"
    old_rules_obj = legacy.parse_glossary(text)
    from transcript_reimagined.domain.models import Rule as NewRule

    new_rule_objs = [NewRule(r.wrong, r.right) for r in new_rules]
    old_text, old_changes = legacy.apply_rules(sample, old_rules_obj)
    new_text, new_changes = apply_rules(sample, new_rule_objs)
    assert new_text == old_text
    assert [(c.wrong, c.right, c.count) for c in new_changes] == [
        (c.wrong, c.right, c.count) for c in old_changes
    ]


@pytest.mark.parametrize("text", GLOSSARY_CASES)
def test_hotword_lists_are_equivalent(text):
    legacy = _legacy("glossary")
    from transcript_reimagined.domain.models import Rule as NewRule
    from transcript_reimagined.post.glossary import hotwords, parse_glossary, parse_hot_words

    old_words = legacy.hotwords(legacy.parse_glossary(text), extra=legacy.parse_hot_words(text))
    new_words = hotwords(
        [NewRule(r.wrong, r.right) for r in parse_glossary(text)], extra=parse_hot_words(text)
    )
    assert new_words == old_words


RENDER_SEGMENTS = [
    {"start": 0.0, "end": 20.0, "text": "我们把集成做完了。请", "speaker": "speaker_1"},
    {"start": 20.0, "end": 40.0, "text": "确认报价。", "speaker": "speaker_1"},
    {"start": 40.0, "end": 60.0, "text": "好的。", "speaker": "speaker_2"},
    {"start": 60.0, "end": 61.0, "text": "   ", "speaker": None},
    {"start": 61.0, "end": 62.0, "text": "甲" * 30 + "，" + "乙" * 29, "speaker": None},
]


def _pairs():
    legacy = _legacy("models")
    new_mod = importlib.import_module("transcript_reimagined.domain.models")
    return [
        (
            legacy.Segment(s["start"], s["end"], s["text"], speaker=s["speaker"]),
            new_mod.Segment(s["start"], s["end"], s["text"], speaker=s["speaker"]),
        )
        for s in RENDER_SEGMENTS
    ]


def test_to_srt_is_byte_for_byte_equivalent():
    legacy = _legacy("render")
    from transcript_reimagined.post.render import to_srt

    old_segments = [pair[0] for pair in _pairs()]
    new_segments = [pair[1] for pair in _pairs()]
    comments = ["词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3"]
    assert to_srt(new_segments, comment_lines=comments) == legacy.to_srt(
        old_segments, comment_lines=comments
    )


def test_to_txt_is_byte_for_byte_equivalent_on_both_paths():
    legacy = _legacy("render")
    from transcript_reimagined.post.render import to_txt

    old_segments = [pair[0] for pair in _pairs()]
    new_segments = [pair[1] for pair in _pairs()]
    text = "我们把集成做完了。"
    comments = ["词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3"]

    # 带 segments（说话人分块路径）
    assert to_txt(text, new_segments, comment_lines=comments) == legacy.to_txt(
        text, old_segments, comment_lines=comments
    )
    # 不带 segments（legacy pipeline 的调用方式）
    assert to_txt(text, None, comment_lines=comments) == legacy.to_txt(
        text, None, comment_lines=comments
    )


@pytest.mark.parametrize(
    "status", [408, 409, 425, 429, 500, 502, 503, 400, 401, 402, 403, 404, 422]
)
def test_classify_http_is_equivalent(status):
    legacy = _legacy("errors")
    from transcript_reimagined.domain.errors import classify_http

    for body in ('{"code":"Throttling"}', '{"code": "Throttling"}', "<html>oops</html>", ""):
        old = legacy.classify_http(status, body)
        new = classify_http(status, body)
        assert type(new).__name__ == type(old).__name__, (status, body)
        assert str(new) == str(old)
        assert new.recoverable == old.recoverable


def test_glossary_line_and_error_semantics_are_equivalent_on_the_spec_sample():
    legacy = _legacy("glossary")
    from transcript_reimagined.post.glossary import parse_glossary_report, split_entries

    sample = (
        "小新\n艾麦 -> 集诚\n-> 集诚\n集诚 = 集诚\n艾麦 -> 集成\n艾麦 => 艾麦科技  # 公司简称\n"
    )
    assert [
        (line_number, left, right) for line_number, left, right in split_entries(sample)
    ] == legacy.split_entries(sample)
    old_rules, old_issues = legacy.parse_glossary_report(sample)
    new_rules, new_issues = parse_glossary_report(sample)
    assert [(r.wrong, r.right) for r in new_rules] == [(r.wrong, r.right) for r in old_rules]
    assert [i.describe() for i in new_issues] == [i.describe() for i in old_issues]
