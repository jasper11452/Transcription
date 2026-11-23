"""`transcript_reimagined.state` —— `state.db` 的唯一写入者。

全仓只有本包可以 import `sqlite3`（import-linter 契约强制）。公开面见 README.md。
"""

from __future__ import annotations

from .store import (
    CHUNK_STATUSES,
    SCHEMA,
    TASK_STATUSES,
    TERMINAL_STATUSES,
    ChunkState,
    Store,
    TaskRecord,
    task_flags,
)

__all__ = [
    "CHUNK_STATUSES",
    "SCHEMA",
    "TASK_STATUSES",
    "TERMINAL_STATUSES",
    "ChunkState",
    "Store",
    "TaskRecord",
    "task_flags",
]
