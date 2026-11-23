"""`transcript.domain` —— 全系统的公共词汇。

公开面只有这些名字（见 README.md）。不要从这里 re-export 其他包的符号：
本包在依赖图最底层，`domain ← config ← {ingest, engines, post, diar, state} ← orchestrate ← web`。
"""

from __future__ import annotations

from .errors import (
    BACKOFF_BASE_S,
    MAX_ATTEMPTS,
    FatalError,
    InputError,
    RecoverableError,
    TranscriptError,
    UpstreamError,
    classify_http,
    is_recoverable,
    retry_delay_s,
)
from .models import (
    AudioInfo,
    Change,
    Chunk,
    Issue,
    Rule,
    Segment,
    TranscriptResult,
    Word,
    fmt_timestamp,
)

__all__ = [
    # models —— 全系统的公共词汇
    "AudioInfo",
    "Change",
    "Chunk",
    "Issue",
    "Rule",
    "Segment",
    "TranscriptResult",
    "Word",
    "fmt_timestamp",
    # errors —— 错误分类法（`RecoverableError` vs `FatalError` 就是重试策略）
    "FatalError",
    "InputError",
    "RecoverableError",
    "TranscriptError",
    "UpstreamError",
    "classify_http",
    "is_recoverable",
    "retry_delay_s",
    "MAX_ATTEMPTS",
    "BACKOFF_BASE_S",
]
