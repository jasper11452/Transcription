"""post —— 后处理：对齐 · 去重 · 词表 · 渲染 · 产物。

对应 `REIMAGINED_ARCHITECTURE.md` §2 的 `post/` 包（承载 legacy 的
`align.py` `merge.py` `glossary.py` `render.py`）。

**本阶段（Phase 1）只含 `glossary` + `render`** —— 见 §5 的落地表：
align / merge 属 Phase 3，本包以显式 `NotImplementedError` 占位，不提供半成品实现。

对外只有两件事：把「已经拿到的文本与时间轴」变成产物；以及词表四规则。
本包不做 I/O 决策（落盘位置在 orchestrate 的单点决策里）、不碰网络、不碰 SQLite。
"""

from __future__ import annotations

__version__ = "0.1.0"

from .domain import Change, GlossaryIssue, GlossaryRule, Segment, Word, fmt_timestamp
from .glossary import (
    MAX_HOT_WORD_CHARS,
    MAX_HOT_WORDS,
    SUMMARY_MAX_HOT_WORD_CHARS,
    SUMMARY_MAX_HOT_WORDS,
    apply_rules,
    cap_hot_words_for_summary,
    change_comment,
    change_header_line,
    dedupe_rules,
    hotwords,
    is_hot_word_line,
    load_glossary,
    parse_glossary,
    parse_glossary_report,
    parse_hot_words,
    split_entries,
)
from .products import ProductSet, WrittenProducts, render_products, write_products
from .render import MAX_SRT_LINE_CHARS, _wrap, to_srt, to_txt, wrap_srt_line

__all__ = [
    "__version__",
    # domain
    "Change",
    "GlossaryIssue",
    "GlossaryRule",
    "Segment",
    "Word",
    "fmt_timestamp",
    # glossary（RULE-021 / 022 / 060 / 132）
    "SUMMARY_MAX_HOT_WORDS",
    "MAX_HOT_WORD_CHARS",
    "MAX_HOT_WORDS",
    "SUMMARY_MAX_HOT_WORD_CHARS",
    "apply_rules",
    "cap_hot_words_for_summary",
    "change_comment",
    "change_header_line",
    "dedupe_rules",
    "hotwords",
    "is_hot_word_line",
    "load_glossary",
    "parse_glossary",
    "parse_glossary_report",
    "parse_hot_words",
    "split_entries",
    # render（RULE-062 / 135 / 136）
    "MAX_SRT_LINE_CHARS",
    "to_srt",
    "to_txt",
    "wrap_srt_line",
    # products（RULE-132）
    "ProductSet",
    "WrittenProducts",
    "render_products",
    "write_products",
]
