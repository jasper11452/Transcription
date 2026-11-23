"""编排层的两个值对象：进度事件与一次运行的结果。

`stage` 是稳定枚举（`AI_NATIVE_SPEC.md` §3.2）：`probe` `normalize` `vad` `plan`
`chunk` `retry` `chunk_failed` `failed` `diar` `merge` `write` `done`。
`scheduler` 把它原样塞进 SSE 的 `progress` 事件，不重新解释。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from transcript_reimagined.domain import Change


@dataclass
class Progress:
    """给页面的进度事件。stage 是稳定枚举，message 只用于展示。"""

    stage: str
    message: str
    current: int = 0
    total: int = 0
    chunk_index: int | None = None

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "chunk_index": self.chunk_index,
        }


@dataclass
class RunResult:
    """一次运行的结果。`srt_path` 为 None 表示按 artifact 没有写 SRT（Q9）。"""

    task_id: int
    status: str
    engine: str
    out_dir: Path | None = None
    txt_path: Path | None = None
    srt_path: Path | None = None
    raw_path: Path | None = None
    audio_seconds: float | None = None
    cost_usd: float | None = None
    chars: int = 0
    changes: list[Change] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "engine": self.engine,
            "out_dir": str(self.out_dir) if self.out_dir else None,
            "txt_path": str(self.txt_path) if self.txt_path else None,
            "srt_path": str(self.srt_path) if self.srt_path else None,
            "raw_path": str(self.raw_path) if self.raw_path else None,
            "audio_seconds": self.audio_seconds,
            "cost_usd": self.cost_usd,
            "chars": self.chars,
            "changes": [c.describe() for c in self.changes],
            "error": self.error,
        }
