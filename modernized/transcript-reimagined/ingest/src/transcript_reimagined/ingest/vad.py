"""vad —— 语音区间：丢掉过短的毛刺、并掉过短的停顿。

**Phase 3 才落地**（``REIMAGINED_ARCHITECTURE.md`` §5：``ingest/`` 在 Phase 1 只含
``chunking.py``）。本模块只固化签名、常量与不变量，不提供半成品实现。

归属理由（§2）：VAD 决定「语音在哪」，切片规划决定「该在哪切」；两者合起来回答
「音频该切成哪几片」。``speech_spans`` 的输出正是 ``chunking.plan_chunks`` 的
``spans`` 入参 —— 这就是本包内部的接缝。

Phase 3 要满足的规则：``RULE-028`` 语音活动门控（丢弃 < 0.25s 的毛刺；
间隔 <= 0.4s 的语音区间并成一个，句间停顿不该变成切片边界）。

**模型只在进程内缓存**（架构 §0/§附）：VAD 模型懒加载、进程内复用，
跨进程不共享 —— 这是保持单进程的理由，不要在 lifespan 里加预加载。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 门控常量（`RULE-028`；实现时不得放宽）。
MIN_SPEECH_S = 0.25
MAX_GAP_S = 0.4
# VAD 输出是**采样点**，单位混淆会让切片整体错位 —— 模型不报采样率时按此换算。
DEFAULT_SAMPLE_RATE = 16_000

#: 进程内模型缓存：``(model_id, model)``。
_model: Any = None
_model_id: str | None = None


def load_vad(model_id: str) -> Any:
    """加载并缓存 VAD 模型（进程内复用；模块级全局，不是 lifespan 钩子）。"""
    raise NotImplementedError(
        "vad.load_vad 属 Phase 3（RULE-028）；Phase 1 的 ingest 只含 chunking"
    )


def speech_spans(
    wav_path: Path | str,
    *,
    model_id: str,
    min_speech_s: float = MIN_SPEECH_S,
    max_gap_s: float = MAX_GAP_S,
) -> list[tuple[float, float]]:
    """返回语音区间（秒），已丢掉毛刺、并过短间隙、按起点排序（`RULE-028`）。

    不变量：
    - 每段时长 ``>= min_speech_s``（更短的是毛刺，丢掉）；
    - 相邻区间间隔 ``<= max_gap_s`` 的并成一个（边界情形 ``== max_gap_s`` 也并）；
    - 结果按起点升序；
    - 检测器没有输出时返回 ``[]`` —— 调用方（切片规划）会把「没有语音区间」
      当作连续语音处理（按 ``inner`` 硬切），不会退化成整段一片。
    """
    raise NotImplementedError(
        "vad.speech_spans 属 Phase 3（RULE-028）；Phase 1 的 ingest 只含 chunking"
    )


def merge_gaps(spans: list[tuple[float, float]], *, max_gap_s: float) -> list[tuple[float, float]]:
    """把间隔小于等于 ``max_gap_s`` 的语音区间并起来（`RULE-028`）。

    纯函数、无模型依赖，因此 Phase 3 可以单独单测。输入按起点排序是前置条件。
    区间按闭区间处理：间隔恰好等于 ``max_gap_s`` 也并。
    """
    raise NotImplementedError(
        "vad.merge_gaps 属 Phase 3（RULE-028）；Phase 1 的 ingest 只含 chunking"
    )
