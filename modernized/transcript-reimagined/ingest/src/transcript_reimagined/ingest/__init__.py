"""ingest —— 音频入料：探测 · 归一化 · 切片规划 · VAD。

对应 ``REIMAGINED_ARCHITECTURE.md`` §2 的 ``ingest/`` 包（承载 legacy 的
``audio.py`` ``vad.py`` ``chunking.py``）。它只回答「音频是什么、该切成哪几片」，
不回答「转写结果怎么落盘」（那是 ``orchestrate`` / ``post`` 的事）。

**本包（Phase 3 之后）包含四个模块**：``chunking`` / ``plan`` 是纯函数；
``audio`` 是唯一碰 ffmpeg 的地方；``vad`` 懒加载 mlx-audio 模型。

边界（可由 lint / AST 检查）：
- 只依赖 ``domain``（架构的依赖图：``domain <- ingest <- orchestrate``）；
- 不写产物、不碰网络、不碰 SQLite；工作副本是临时品（NFR-2）；
- ``chunking`` 是**纯函数**，零副作用 —— 切片错了后面全错，所以它可以独立单测；
- 唯一碰 ffmpeg 的地方（``audio.py``）也住在这里。
"""

from __future__ import annotations

__version__ = "0.1.0"

from .audio import cut, probe, require_ffmpeg, to_mp3_64k, to_wav16k, verify
from .chunking import plan_chunks, plan_chunks_with
from .plan import MIN_GAP_FOR_CUT_S, MIN_INNER_S, ChunkPlan
from .vad import merge_gaps, speech_spans

__all__ = [
    "__version__",
    # 切片预算（RULE-011 / RULE-012 的参数与不变量）
    "ChunkPlan",
    "MIN_GAP_FOR_CUT_S",
    "MIN_INNER_S",
    # 切片规划（RULE-011 / RULE-012）
    "plan_chunks",
    "plan_chunks_with",
    # 探测 / 归一化 / 切（RULE-049 / RULE-050）
    "probe",
    "require_ffmpeg",
    "verify",
    "to_wav16k",
    "to_mp3_64k",
    "cut",
    # 语音活动门控（RULE-028）
    "speech_spans",
    "merge_gaps",
]
