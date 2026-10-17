"""`transcript_reimagined.summarize` —— 显式开启的 Agent 总结。"""

from __future__ import annotations

from .summary import (
    DEFAULT_SUMMARY_PROMPT,
    MAX_BATCH_CHARS,
    MAX_HOT_WORD_CHARS,
    MAX_HOT_WORDS,
    MAX_PROMPT_CHARS,
    MAX_REASONING_CHARS,
    PARTIAL_THROTTLE_S,
    REQUEST_TIMEOUT_S,
    SummaryManager,
    hot_word_list,
    summarize,
    summarize_stream,
)

__all__ = [
    "DEFAULT_SUMMARY_PROMPT",
    "MAX_BATCH_CHARS",
    "MAX_HOT_WORD_CHARS",
    "MAX_HOT_WORDS",
    "MAX_PROMPT_CHARS",
    "MAX_REASONING_CHARS",
    "PARTIAL_THROTTLE_S",
    "REQUEST_TIMEOUT_S",
    "SummaryManager",
    "hot_word_list",
    "summarize",
    "summarize_stream",
]
