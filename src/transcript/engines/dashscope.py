"""阿里云百炼（DashScope）适配器——默认的在线引擎。

用原生多模态接口（不是 OpenAI 兼容模式），实测依据（`spikes/probe_dashscope_native*.py`）：

- 原生 `POST /api/v1/services/aigc/multimodal-generation/generation` + **base64 data URL** → 200。
  不需要 SDK，也不需要把文件先传到 OSS（SDK 的 `file://` 内部就是干这件事）。
- **`parameters.format` 必须传**（`wav`/`mp3`）：缺它恒报 `UNSUPPORTED_FORMAT: format is empty`。
  之前走兼容模式一直失败就是这个原因——兼容模式无法把 format 传进去。
- 返回**字级时间戳**：`output.sentence.words[].begin_time/end_time`（毫秒），
  所以这条路能同时产出 txt 和 srt；文本放在 `output.text` / `output.sentence.text`。
- **单次上限 300s**：实测 330s 报 `AUDIO_DURATION_TOO_LONG: over service process (300s)`。
  所以引擎声明 `max_chunk_s = 300`，由 pipeline 保证切片不超过它。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from .. import audio as audio_mod
from ..align import build_segments
from ..config import DASHSCOPE_MAX_CHUNK_S, Config
from ..errors import FatalError, RecoverableError, classify_http
from ..models import TranscriptResult, Word

_FORMAT_BY_SUFFIX = {".mp3": "mp3", ".wav": "wav", ".m4a": "m4a", ".aac": "aac", ".flac": "flac"}

# 与上游错误码一一对应，便于在页面上说清"为什么失败、该怎么办"
_DURATION_TOO_LONG = "AUDIO_DURATION_TOO_LONG"
_FORMAT_EMPTY = "UNSUPPORTED_FORMAT"


class DashScopeEngine:
    """百炼原生多模态 ASR。带字级时间戳，所以 txt/srt 都能出。"""

    has_timestamps = True

    def __init__(
        self,
        config: Config,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        max_chunk_s: float | None = DASHSCOPE_MAX_CHUNK_S,
    ):
        self.config = config
        self.model = model or config.dashscope_model
        self.name = f"dashscope:{self.model}"
        self.max_chunk_s = max_chunk_s
        self._transport = transport

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        hotwords: list[str] | None = None,
        want_timestamps: bool = True,
    ) -> TranscriptResult:
        if not self.config.dashscope_api_key:
            raise FatalError(
                f"未配置 DASHSCOPE_API_KEY（{self.config.config_path}），无法使用百炼在线引擎"
            )
        path = Path(audio_path)
        suffix = path.suffix.lower()
        audio_format = _FORMAT_BY_SUFFIX.get(suffix)
        if audio_format is None:
            raise FatalError(
                f"百炼引擎只接受带已知容器的音频，收到 {suffix or '(无后缀)'}；"
                "请先走 ffmpeg 归一化（pipeline 会自动做）"
            )

        # 本地先卡时长：宁可本地报错，也不要花一次带密钥的请求去换 AUDIO_DURATION_TOO_LONG
        if self.max_chunk_s:
            duration = audio_mod.probe(path).duration
            if duration > self.max_chunk_s + 0.5:
                raise FatalError(
                    f"这段音频 {duration:.1f}s 超过该模型单次上限 {self.max_chunk_s:.0f}s"
                    f"（实测上游报 {_DURATION_TOO_LONG}）；请调小 CHUNK_MAX_S 后重试"
                )

        payload: dict = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"audio": _data_url(path, audio_format)}]}
                ]
            },
            "parameters": {
                # format 必传：缺它会直接 UNSUPPORTED_FORMAT: format is empty
                "format": audio_format,
                "asr_options": {
                    "language": language or "zh",
                    "enable_itn": True,
                },
            },
        }
        url = f"{self.config.dashscope_base}/api/v1/services/aigc/multimodal-generation/generation"
        headers = {"Authorization": f"Bearer {self.config.dashscope_api_key}"}
        try:
            with httpx.Client(timeout=900, transport=self._transport) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise RecoverableError(f"百炼请求失败（网络）：{type(exc).__name__}") from exc

        if resp.status_code != 200:
            self._raise_for_error(resp)

        data = resp.json()
        words, text = _extract(data)
        if not text:
            raise FatalError(f"百炼返回了空文本（{json.dumps(data, ensure_ascii=False)[:200]}）")

        usage = data.get("usage") or {}
        seconds = usage.get("duration")
        segments = build_segments(text, words) if want_timestamps else []
        return TranscriptResult(
            text=text,
            segments=segments,
            language=language or "zh",
            audio_seconds=float(seconds) if seconds else None,
            cost_usd=None,  # 百炼按秒计费，单价随账号/活动变化，不在这里猜
            engine=self.name,
            has_timestamps=bool(segments),
        )

    def _raise_for_error(self, resp: httpx.Response) -> None:
        body = resp.text[:600]
        try:
            code = (resp.json() or {}).get("code")
        except json.JSONDecodeError:
            code = None

        if code == _DURATION_TOO_LONG or _DURATION_TOO_LONG in body:
            raise FatalError(
                f"音频超过模型单次上限（{self.max_chunk_s or DASHSCOPE_MAX_CHUNK_S:.0f}s）。"
                f"上游原文：{body[:200]}"
            )
        if code == _FORMAT_EMPTY or "format is empty" in body:
            raise FatalError(
                "上游报 format is empty：请求缺少 parameters.format（本适配器会带上它），"
                "若你改过请求体，请先跑 `transcript check --probe <音频>` 复验"
            )
        raise classify_http(resp.status_code, body)


def _data_url(path: Path, audio_format: str) -> str:
    """base64 data URL —— 原生接口吃这个，不需要公网 URL 或 SDK 的 OSS 上传。"""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:audio/{audio_format};base64,{encoded}"


def _extract(data: dict) -> tuple[list[Word], str]:
    """从原生响应里取出字级时间戳与文本。

    响应形状（实测）：
        {"output": {"output": {"sentence": {...}, "text": "..."}, "sentence": {...}, "text": "..."}}
    外层是兼容层的镜像，内层才是真正的结果；两处都取一遍以防版本差异。
    """
    outer = data.get("output") or {}
    inner = outer.get("output") if isinstance(outer.get("output"), dict) else outer
    sentences = inner.get("sentence") or outer.get("sentence") or []
    if isinstance(sentences, dict):
        sentences = [sentences]

    words: list[Word] = []
    for sentence in sentences:
        for word in sentence.get("words") or []:
            text = (word.get("text") or "").strip()
            if not text:
                continue
            words.append(
                Word(
                    text=text,
                    start=float(word.get("begin_time") or 0) / 1000.0,
                    end=float(word.get("end_time") or 0) / 1000.0,
                    probability=None,
                )
            )

    text = (inner.get("text") or outer.get("text") or "").strip()
    if not text:
        text = "".join(s.get("text") or "" for s in sentences).strip()
    if not text and words:
        text = "".join(w.text for w in words)
    return words, text
