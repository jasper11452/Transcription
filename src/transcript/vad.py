"""VAD：找出语音区间，供切片规划使用。

用 mlx-audio 的 Silero VAD（1.2MB，MLX 原生，**不需要 torch/onnxruntime**）。
模型懒加载并缓存；CLI 的 --help/测试路径不会因此背上推理依赖。
"""

from __future__ import annotations

from pathlib import Path

from .errors import InputError

_model = None
_model_id: str | None = None


def load_vad(model_id: str):
    """加载并缓存 VAD 模型（进程内复用）。"""
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
    min_speech_s: float = 0.25,
    max_gap_s: float = 0.4,
) -> list[tuple[float, float]]:
    """返回语音区间（秒），已合并过短的静音间隙。

    VAD 输出是**采样点**，这里统一换算成秒——单位混淆会让切片整体错位。
    """
    model = load_vad(model_id)
    out = model.generate(str(wav_path))
    rate = int(getattr(out, "sample_rate", 16_000) or 16_000)
    raw = [(t["start"] / rate, t["end"] / rate) for t in (getattr(out, "timestamps", None) or [])]
    spans = [(s, e) for s, e in raw if e - s >= min_speech_s]
    return merge_gaps(sorted(spans), max_gap_s=max_gap_s)


def merge_gaps(spans: list[tuple[float, float]], *, max_gap_s: float) -> list[tuple[float, float]]:
    """把间隔小于 max_gap_s 的语音区间并起来（句间停顿不该成为切片边界）。"""
    if not spans:
        return []
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start - last_end <= max_gap_s:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
