"""OpenRouter 适配器——在线 srt 引擎（microsoft/mai-transcribe-2）。

实测约束：
- 端点 `POST {base}/audio/transcriptions`，multipart，`response_format=verbose_json` 返回
  `segments[].start/end/text` 与 `usage.cost`（≈$0.1/小时音频）；
- **m4a 会直接 400**，必须先用 ffmpeg 归一化为 mp3；
- 两级体积上限：请求体 50MiB；模型侧音频约 15.4MB 通过 / 18.4MB 被拒。

重建自 ``legacy/transcript/src/transcript/engines/openrouter.py``。引擎返回原生
**段级** segments（不经过 align）；`words` 为空。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from transcript_reimagined.config import Config
from transcript_reimagined.domain import (
    FatalError,
    RecoverableError,
    Segment,
    TranscriptResult,
    classify_http,
)

_TOO_LARGE_HINTS = (
    "does not support large audio inputs",
    "request body of",
    "exceeds the maximum allowed size",
)
MAX_HOTWORDS = 50

# 本地体积闸门（NFR-9 / RULE-058）。上游两级限制：
# - 请求体 50MiB；
# - 模型侧实测约 15.4MB 通过、18.4MB 被拒。
# 取模型侧的更严格值，在发请求前拦住 —— 超限分片不该花一次付费调用去换 400。
REQUEST_BODY_LIMIT_BYTES = 50 * 1024 * 1024
MODEL_AUDIO_LIMIT_BYTES = 15_400_000


class OpenRouterEngine:
    """带时间段与费用的转写引擎，也是在线 srt 的来源。"""

    has_timestamps = True

    def __init__(
        self, config: Config, model: str | None = None, transport: httpx.BaseTransport | None = None
    ):
        self.config = config
        self.model = model or config.openrouter_model
        self.name = f"openrouter:{self.model}"
        # 已知限制是“体积”而非“时长”（请求体 50MiB / 模型侧约 15.4MB），
        # 由码率与切片长度共同决定，这里不做时长级别的声明
        self.max_chunk_s = None
        self._transport = transport

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        hotwords: list[str] | None = None,
        want_timestamps: bool = True,  # noqa: ARG002 - 该引擎总是返回段级时间戳
        duration_s: float | None = None,  # noqa: ARG002 - 限制是体积不是时长
    ) -> TranscriptResult:
        if not self.config.openrouter_api_key:
            raise FatalError(
                f"未配置 OPENROUTER_API_KEY（{self.config.config_path}），无法使用在线 srt 引擎"
            )
        path = Path(audio_path)
        size = path.stat().st_size
        if size > MODEL_AUDIO_LIMIT_BYTES:
            raise FatalError(
                f"音频 {size / 1e6:.1f}MB 超过该模型的体积上限"
                f"（实测约 {MODEL_AUDIO_LIMIT_BYTES / 1e6:.1f}MB）；"
                "请减小分片长度或降低码率后重试（未发起付费请求）。"
            )
        data = {"model": self.model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        if hotwords:
            data["prompt"] = "术语参考：" + "、".join(hotwords[:MAX_HOTWORDS])

        url = f"{self.config.openrouter_base}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.config.openrouter_api_key}"}
        try:
            with (
                httpx.Client(timeout=900, transport=self._transport) as client,
                path.open("rb") as handle,
            ):
                resp = client.post(
                    url,
                    headers=headers,
                    data=data,
                    files={"file": (path.name, handle, "audio/mpeg")},
                )
        except httpx.HTTPError as exc:
            raise RecoverableError(f"OpenRouter 请求失败（网络）：{type(exc).__name__}") from exc

        if resp.status_code != 200:
            body = resp.text[:600]
            if any(hint in body.lower() for hint in _TOO_LARGE_HINTS):
                raise FatalError(
                    f"音频超出该模型的体积上限（{path.stat().st_size / 1e6:.1f}MB）。"
                    "减小分片长度或降低码率后重试。原始响应：" + body[:200]
                )
            raise classify_http(resp.status_code, body)

        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise FatalError(f"OpenRouter 返回非 JSON：{resp.text[:200]}") from exc

        usage = payload.get("usage") or {}
        segments = [
            Segment(
                start=float(seg.get("start") or 0.0),
                end=float(seg.get("end") or 0.0),
                text=(seg.get("text") or "").strip(),
            )
            for seg in (payload.get("segments") or [])
            if (seg.get("text") or "").strip()
        ]
        text = (payload.get("text") or "").strip()
        if not text and segments:
            text = "".join(s.text for s in segments)

        return TranscriptResult(
            text=text,
            segments=segments,
            language=payload.get("language"),
            audio_seconds=float(usage["seconds"]) if usage.get("seconds") else None,
            cost_usd=float(usage["cost"]) if usage.get("cost") is not None else None,
            engine=self.name,
            has_timestamps=bool(segments),
        )
