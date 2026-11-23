"""离线引擎：文本取 Qwen、时间轴取 whisper，且**只取一次**（Q3 死分支修复）。

不加载真实 MLX 模型：用同形状的桩对象验证调用次数与结果形状。真实模型的
端到端行为由 Phase 5 的编排测试在隔离环境下覆盖。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from transcript_reimagined.config import Config
from transcript_reimagined.domain import Word, classify_http

from transcript_reimagined.engines import offline


class _FakeQwen:
    def __init__(self, text="你好世界。", language=("zh",)):
        self.calls: list[dict] = []
        self._text = text
        self._language = list(language)

    def generate(self, _path, *, hotwords=None, language=None):
        self.calls.append({"hotwords": hotwords, "language": language})
        return SimpleNamespace(text=self._text, language=self._language)


def test_text_comes_from_qwen_and_words_from_whisper_once(tmp_path: Path, monkeypatch):
    qwen = _FakeQwen()
    whisper_calls: list[Path] = []

    def fake_whisper(path, *, repo, language):
        whisper_calls.append(Path(path))
        return [Word("你", 0.0, 0.2), Word("好", 0.2, 0.4)]

    monkeypatch.setattr(offline, "_load_qwen", lambda _model: qwen)
    monkeypatch.setattr(offline, "_whisper_words", fake_whisper)

    engine = offline.OfflineEngine(Config())
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"x")
    result = engine.transcribe(audio, want_timestamps=True, language="zh")

    assert result.text == "你好世界。"
    assert [w.text for w in result.words] == ["你", "好"]
    assert result.segments == []  # 对齐由 orchestrate 调 post.align 完成
    assert result.has_timestamps is True
    assert result.cost_usd == 0.0
    assert result.language == "zh"
    assert len(whisper_calls) == 1, "Q3：词级时间轴只算一次，不跑第二次同参数调用"


def test_no_whisper_call_when_timestamps_are_not_requested(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(offline, "_load_qwen", lambda _model: _FakeQwen())
    called = []
    monkeypatch.setattr(offline, "_whisper_words", lambda *a, **k: called.append(1) or [])
    result = offline.OfflineEngine(Config()).transcribe(
        tmp_path / "chunk.wav", want_timestamps=False
    )
    assert called == []
    assert result.words == []


def test_empty_text_skips_whisper(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(offline, "_load_qwen", lambda _model: _FakeQwen(text=""))
    called = []
    monkeypatch.setattr(offline, "_whisper_words", lambda *a, **k: called.append(1) or [])
    result = offline.OfflineEngine(Config()).transcribe(
        tmp_path / "chunk.wav", want_timestamps=True
    )
    assert called == []
    assert result.text == ""


def test_hotwords_are_forwarded_to_qwen(tmp_path: Path, monkeypatch):
    qwen = _FakeQwen()
    monkeypatch.setattr(offline, "_load_qwen", lambda _model: qwen)
    monkeypatch.setattr(offline, "_whisper_words", lambda *a, **k: [])
    offline.OfflineEngine(Config()).transcribe(
        tmp_path / "chunk.wav", hotwords=["集诚", "离线"], want_timestamps=False
    )
    assert qwen.calls[0]["hotwords"] == ["集诚", "离线"]


def test_offline_engine_has_no_chunk_ceiling():
    engine = offline.OfflineEngine(Config())
    assert engine.max_chunk_s is None
    assert engine.has_timestamps is True


def test_http_classification_is_the_retry_policy():
    from transcript_reimagined.domain import RecoverableError, UpstreamError

    assert isinstance(classify_http(429, ""), RecoverableError)
    assert isinstance(classify_http(503, ""), RecoverableError)
    assert isinstance(classify_http(400, ""), UpstreamError)
