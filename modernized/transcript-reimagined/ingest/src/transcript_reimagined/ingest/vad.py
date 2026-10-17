"""VAD：找出语音区间，供切片规划使用。

用 mlx-audio 的 Silero VAD（1.2MB，MLX 原生，**不需要 torch/onnxruntime**）。
模型懒加载并缓存；CLI 的 --help/测试路径不会因此背上推理依赖。

重建自 ``legacy/transcript/src/transcript/vad.py``。规则：`RULE-028`
（丢弃 < 0.25s 的毛刺；间隔 <= 0.4s 的语音区间并成一个）。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from transcript_reimagined.domain import InputError

MIN_SPEECH_S = 0.25
MAX_GAP_S = 0.4
# VAD 输出是**采样点**，单位混淆会让切片整体错位 —— 模型不报采样率时按此换算。
DEFAULT_SAMPLE_RATE = 16_000

#: 进程内模型缓存：``(model_id, model)``。
_model: Any = None
_model_id: str | None = None


def load_vad(model_id: str) -> Any:
    """加载并缓存 VAD 模型（进程内复用；模块级全局，不是 lifespan 钩子）。"""
    global _model, _model_id
    if _model is not None and _model_id == model_id:
        return _model
    try:
        from mlx_audio.vad import load
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise InputError("未安装 mlx-audio，无法做 VAD 切片（uv sync 后重试）") from exc
    _model = load(model_id)
    _model_id = model_id
    return _model


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
    model = load_vad(model_id)
    out = model.generate(str(wav_path))
    rate = int(getattr(out, "sample_rate", DEFAULT_SAMPLE_RATE) or DEFAULT_SAMPLE_RATE)
    raw = [
        (t["start"] / rate, t["end"] / rate)
        for t in (getattr(out, "timestamps", None) or [])
    ]
    spans = [(s, e) for s, e in raw if e - s >= min_speech_s]
    return merge_gaps(sorted(spans), max_gap_s=max_gap_s)


def merge_gaps(
    spans: Sequence[tuple[float, float]], *, max_gap_s: float = MAX_GAP_S
) -> list[tuple[float, float]]:
    """把间隔小于等于 ``max_gap_s`` 的语音区间并起来（`RULE-028`）。

    纯函数、无模型依赖。输入按起点排序是前置条件。
    区间按闭区间处理：间隔恰好等于 ``max_gap_s`` 也并。
    """
    if not spans:
        return []
    merged: list[tuple[float, float]] = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        # 浮点边界：10.4 - 10.0 == 0.40000000000000036，直接 <= 0.4 会漏掉
        # 「恰好等于 max_gap_s」这个规则卡明确要求合并的边界情形。
        if start - last_end <= max_gap_s + 1e-9:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
