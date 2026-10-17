"""Pipeline 测试的共用桩：假引擎、假音频、假 VAD。

不碰 ffmpeg、不碰 MLX、不发网络请求 —— P0 与续跑语义只需要「分片边界」。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import (
    AudioInfo,
    FatalError,
    RecoverableError,
    TranscriptResult,
    Word,
)
from transcript_reimagined.state import Store

from transcript_reimagined.orchestrate import pipeline as pipeline_mod


class FakeEngine:
    """按分片下标返回固定文本；可指定失败/重试的片。"""

    name = "fake:engine"
    max_chunk_s = None

    def __init__(
        self,
        *,
        fail_indexes: set[int] | None = None,
        recoverable_once_indexes: set[int] | None = None,
        has_timestamps: bool = True,
        empty_text_indexes: set[int] | None = None,
    ):
        self.fail_indexes = fail_indexes or set()
        self.recoverable_once_indexes = recoverable_once_indexes or set()
        self.has_timestamps = has_timestamps
        self.empty_text_indexes = empty_text_indexes or set()
        self.calls: list[int] = []
        self._seen_recoverable: set[int] = set()

    def transcribe(
        self,
        audio_path: Path,
        *,
        language=None,
        hotwords=None,
        want_timestamps=False,
        duration_s=None,
    ) -> TranscriptResult:
        idx = int(Path(audio_path).stem.rsplit("_", 1)[-1])
        self.calls.append(idx)
        if idx in self.recoverable_once_indexes and idx not in self._seen_recoverable:
            self._seen_recoverable.add(idx)
            raise RecoverableError("网络抖动")
        if idx in self.fail_indexes:
            raise FatalError(f"分片 {idx} 注定失败")
        text = "" if idx in self.empty_text_indexes else f"第{idx}片正文。"
        words = (
            [Word("第", 0.0, 0.2), Word("片", 0.2, 0.4)]
            if want_timestamps and self.has_timestamps
            else []
        )
        return TranscriptResult(
            text=text,
            segments=[],
            words=words,
            engine=self.name,
            has_timestamps=self.has_timestamps,
        )


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    return _make_env(tmp_path, monkeypatch, duration=6.0, chunk_min=3.0, chunk_max=5.0)


@pytest.fixture
def long_env(tmp_path: Path, monkeypatch):
    """6 分片场景：29.4s / 内预算 4.9s → 恰好 6 片。"""
    return _make_env(tmp_path, monkeypatch, duration=29.4, chunk_min=5.0, chunk_max=5.0)


def _make_env(tmp_path: Path, monkeypatch, *, duration: float, chunk_min: float, chunk_max: float):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "meeting.wav"
    source.write_bytes(b"source-bytes")
    info = AudioInfo(
        path=source,
        duration=duration,
        size_bytes=len(b"source-bytes"),
        codec="pcm_s16le",
        sample_rate=16_000,
        channels=1,
        has_audio=True,
    )

    def write(dst, payload: bytes) -> Path:
        path = Path(dst)
        path.write_bytes(payload)
        return path

    monkeypatch.setattr(pipeline_mod.audio_mod, "probe", lambda _p: info)
    monkeypatch.setattr(
        pipeline_mod.audio_mod, "to_wav16k", lambda _src, dst: write(dst, b"wav")
    )
    monkeypatch.setattr(
        pipeline_mod.audio_mod, "to_mp3_64k", lambda _src, dst: write(dst, b"mp3")
    )
    monkeypatch.setattr(pipeline_mod.audio_mod, "verify", lambda _p, _kind: info)
    monkeypatch.setattr(
        pipeline_mod.audio_mod,
        "cut",
        lambda _src, dst, _start, _end, **_kw: write(dst, b"chunk"),
    )

    config = Config(
        config_path=tmp_path / "config.env",
        # 必填：Config 的默认 state_db 指向用户真实的 ~/Documents/Transcript/state.db。
        # 测试夹具漏传这一项，子进程就会写进真实库（本文件踩过一次）。
        state_db=tmp_path / "state.db",
        glossary_path=tmp_path / "glossary.txt",
        output_dir=tmp_path / "fallback-output",
        chunk_min_s=chunk_min,
        chunk_max_s=chunk_max,
        chunk_overlap_s=0.1,
        max_attempts=2,
        backoff_base=0.0,
    )
    store = Store(tmp_path / "state.db")
    return config, store, source, source_dir


def make_pipeline(config, store, engine: FakeEngine, *, events=None, span_end: float = 6.0):
    return pipeline_mod.Pipeline(
        config,
        store,
        engine_factory=lambda _kind, _config, artifact=None: engine,
        vad_fn=lambda _wav: [(0.0, span_end)],
        sleep=lambda _s: None,
        on_event=None if events is None else events.append,
    )
