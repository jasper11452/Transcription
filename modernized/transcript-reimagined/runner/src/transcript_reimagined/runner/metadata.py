"""音频元数据 JSON 的读取与校验 —— Phase 1 的「探测」替身。

真实 ffprobe / VAD 属 Phase 3（``ingest.audio`` / ``ingest.vad``）。本阶段从一份 JSON
读同样的**事实**（时长、语音区间、待渲染文本），好处是切片入口因此零外部依赖、
可在临时目录里端到端复现。

JSON 形状（``tests/data/metadata.sample.json`` 是同一份契约的可执行样例）::

    {
      "path": "audio/会议.m4a",
      "duration_s": 300.0,
      "spans": [[0.0, 60.0], [61.2, 300.0]],
      "merged_text": "我们把集成做完了",
      "engine": "dashscope",
      "has_timestamps": true,
      "artifact": "srt",
      "chunk": {"min_s": 30.0, "max_s": 120.0, "overlap_s": 0.5},
      "segments": [
        {"start": 0.0, "end": 12.0, "text": "开会。请", "speaker": "speaker_1"}
      ]
    }

**安全边界（``NFR-4``）**：这份文件是**元数据**，不是凭据载体。任何疑似密钥的字段名
（``api_key`` / ``secret`` / ``token`` / ``password``）都会被拒绝，而不是被读进内存。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from transcript_reimagined.domain import AudioInfo, Segment
from transcript_reimagined.ingest import ChunkPlan

# 出现这些字段名就拒绝 —— 凭据永不进任务输入、产物与日志
_SECRET_KEY_MARKERS = ("api_key", "apikey", "secret", "token", "password", "credential")


class MetadataError(ValueError):
    """元数据文件缺失、不是 JSON、或形状不对。这类错误是致命的，不重试。"""


@dataclass(frozen=True)
class AudioMetadata:
    """切片入口需要知道的全部事实。"""

    path: Path
    duration_s: float
    spans: tuple[tuple[float, float], ...]
    segments: tuple[Segment, ...]
    merged_text: str
    chunk: ChunkPlan = field(default_factory=ChunkPlan)
    engine: str = ""
    has_timestamps: bool = True
    artifact: str = "srt"
    mode: str = "offline"
    task_id: int | str | None = None
    size_bytes: int = 0
    codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None

    @property
    def audio_info(self) -> AudioInfo:
        """领域层的 ``AudioInfo``：Phase 3 起由 ffprobe 填，现在由元数据填。"""
        return AudioInfo(
            path=self.path,
            duration=self.duration_s,
            size_bytes=self.size_bytes,
            codec=self.codec,
            sample_rate=self.sample_rate,
            channels=self.channels,
            has_audio=self.duration_s > 0,
        )


def _require_mapping(data: object) -> dict:
    if not isinstance(data, dict):
        raise MetadataError(f"元数据必须是 JSON 对象，收到：{type(data).__name__}")
    return data


def _require_number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetadataError(f"{key} 必须是数字，收到：{value!r}")
    return float(value)


def _reject_secret_fields(data: dict) -> None:
    for key in data:
        lowered = str(key).lower()
        if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
            raise MetadataError(f"元数据不得包含凭据字段：{key!r}（凭据只从环境/配置文件读）")


def _parse_spans(raw: object) -> tuple[tuple[float, float], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise MetadataError("spans 必须是 [start, end] 二元组的列表")
    spans: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise MetadataError(f"spans 的每一项必须形如 [start, end]，收到：{item!r}")
        start = _require_number(item[0], "spans[..][0]")
        end = _require_number(item[1], "spans[..][1]")
        if end <= start:  # 与 legacy 一致：空/倒序区间被丢弃，不参与切点选择
            continue
        spans.append((start, end))
    return tuple(spans)


def _parse_segments(raw: object) -> tuple[Segment, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise MetadataError("segments 必须是对象列表")
    segments: list[Segment] = []
    for item in raw:
        if not isinstance(item, dict):
            raise MetadataError(f"segments 的每一项必须是对象，收到：{item!r}")
        missing = [k for k in ("start", "end", "text") if k not in item]
        if missing:
            raise MetadataError(f"segments 缺少字段 {missing}，收到：{sorted(item)}")
        speaker = item.get("speaker")
        if speaker is not None and not isinstance(speaker, str):
            raise MetadataError(f"segments[].speaker 必须是字符串或 null，收到：{speaker!r}")
        segments.append(
            Segment(
                start=_require_number(item["start"], "segments[].start"),
                end=_require_number(item["end"], "segments[].end"),
                text=str(item["text"]),
                speaker=speaker,
            )
        )
    return tuple(segments)


def _parse_chunk_plan(raw: object) -> ChunkPlan:
    if raw is None:
        return ChunkPlan()
    if not isinstance(raw, dict):
        raise MetadataError("chunk 必须是对象，形如 {min_s, max_s, overlap_s}")
    default = ChunkPlan()
    plan = ChunkPlan(
        min_s=_require_number(raw.get("min_s", default.min_s), "chunk.min_s"),
        max_s=_require_number(raw.get("max_s", default.max_s), "chunk.max_s"),
        overlap_s=_require_number(raw.get("overlap_s", default.overlap_s), "chunk.overlap_s"),
    )
    if plan.min_s <= 0 or plan.max_s < plan.min_s or plan.overlap_s < 0:
        raise MetadataError(
            f"chunk 参数非法：min_s={plan.min_s} max_s={plan.max_s} overlap_s={plan.overlap_s}"
        )
    return plan


def parse_metadata(document: str) -> AudioMetadata:
    """解析元数据 JSON 文本。任何形状问题都抛 :class:`MetadataError`。"""
    try:
        data = _require_mapping(json.loads(document))
    except json.JSONDecodeError as exc:
        raise MetadataError(f"元数据不是合法 JSON：{exc}") from exc

    _reject_secret_fields(data)

    if "duration_s" not in data:
        raise MetadataError("元数据缺少 duration_s")
    duration_s = _require_number(data["duration_s"], "duration_s")
    if duration_s < 0:
        raise MetadataError(f"duration_s 不能为负：{duration_s}")

    merged_text = data.get("merged_text", "")
    if not isinstance(merged_text, str):
        raise MetadataError("merged_text 必须是字符串")

    has_timestamps = data.get("has_timestamps", True)
    if not isinstance(has_timestamps, bool):
        raise MetadataError("has_timestamps 必须是布尔值")

    chunk = _parse_chunk_plan(data.get("chunk"))
    if chunk.max_s < duration_s and duration_s > 0 and not data.get("spans"):
        # 只是提示：没有语音区间时切点只能硬切。不构成错误。
        pass

    return AudioMetadata(
        path=Path(str(data.get("path", "audio"))),
        duration_s=duration_s,
        spans=_parse_spans(data.get("spans")),
        segments=_parse_segments(data.get("segments")),
        merged_text=merged_text,
        chunk=chunk,
        engine=str(data.get("engine", "")),
        has_timestamps=has_timestamps,
        artifact=str(data.get("artifact", "srt")),
        mode=str(data.get("mode", "offline")),
        task_id=data.get("task_id"),
        size_bytes=int(_require_number(data.get("size_bytes", 0), "size_bytes")),
        codec=data.get("codec"),
        sample_rate=data.get("sample_rate"),
        channels=data.get("channels"),
    )


def load_metadata(path: Path | str) -> AudioMetadata:
    """从磁盘读元数据。文件不存在时抛 :class:`MetadataError`（不静默当空输入）。"""
    p = Path(path)
    if not p.exists():
        raise MetadataError(f"元数据文件不存在：{p}")
    try:
        return parse_metadata(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MetadataError(f"元数据文件读不了：{p}（{exc}）") from exc
