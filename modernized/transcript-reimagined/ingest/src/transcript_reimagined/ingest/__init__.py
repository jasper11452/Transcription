"""ingest —— 音频入料：探测 · 归一化 · 切片规划 · VAD。

对应 ``REIMAGINED_ARCHITECTURE.md`` §2 的 ``ingest/`` 包（承载 legacy 的
``audio.py`` ``vad.py`` ``chunking.py``）。它只回答「音频是什么、该切成哪几片」，
不回答「转写结果怎么落盘」（那是 ``orchestrate`` / ``post`` 的事）。

**本阶段（Phase 1）只含 ``chunking.py``** —— 见 §5 的落地表：
``audio`` / ``vad`` 属 Phase 3，本包以显式 ``NotImplementedError`` 占位，
不提供半成品实现（与 ``post`` 对 ``align`` / ``merge`` 的做法一致）。

边界（可由 lint / AST 检查）：
- 只依赖 ``domain``（架构的依赖图：``domain <- ingest <- orchestrate``）；
- 不写文件、不碰网络、不碰 SQLite；
- ``chunking`` 是**纯函数**，零副作用 —— 切片错了后面全错，所以它可以独立单测；
- 唯一碰 ffmpeg 的地方（Phase 3 的 ``audio.py``）也住在这里。
"""

from __future__ import annotations

__version__ = "0.1.0"

from .chunking import plan_chunks, plan_chunks_with
from .plan import MIN_GAP_FOR_CUT_S, MIN_INNER_S, ChunkPlan

__all__ = [
    "__version__",
    # 切片预算（RULE-011 / RULE-012 的参数与不变量）
    "ChunkPlan",
    "MIN_GAP_FOR_CUT_S",
    "MIN_INNER_S",
    # 切片规划（RULE-011 / RULE-012）
    "plan_chunks",
    "plan_chunks_with",
]

# audio / vad 属 Phase 3。**不**在这里 re-export：它们的调用会抛
# NotImplementedError，从包根导出会让人误以为已经可用。需要引用签名时显式写
# `from transcript_reimagined.ingest import audio` 或 `... import vad`。
