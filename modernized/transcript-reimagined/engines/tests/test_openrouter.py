"""OpenRouter 适配器：段级时间戳、权威费用、体积错误（RULE-020 / RULE-058 / RULE-131）。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import FatalError, RecoverableError, UpstreamError

from transcript_reimagined.engines.openrouter import MAX_HOTWORDS, OpenRouterEngine

GOOD = {
    "text": "你好世界",
    "segments": [
        {"start": 0.0, "end": 1.0, "text": "你好"},
        {"start": 1.0, "end": 2.0, "text": "世界"},
        {"start": 2.0, "end": 2.1, "text": "   "},
    ],
    "language": "zh",
    "usage": {"seconds": 2.0, "cost": 0.000123},
}


def make_audio(tmp_path: Path) -> Path:
    path = tmp_path / "chunk.mp3"
    path.write_bytes(b"fake-mp3")
    return path


def make_engine(tmp_path: Path, handler) -> tuple[OpenRouterEngine, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    config = Config(config_path=tmp_path / "config.env", openrouter_api_key="sk-or")
    return OpenRouterEngine(config, transport=httpx.MockTransport(wrapped)), seen


@pytest.mark.rule("RULE-020")
def test_segments_text_and_authoritative_cost(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=GOOD))
    result = engine.transcribe(make_audio(tmp_path), language="zh")
    assert result.text == "你好世界"
    assert [s.text for s in result.segments] == ["你好", "世界"]  # 空白段被丢掉
    assert result.words == []
    assert result.language == "zh"
    assert result.audio_seconds == 2.0
    assert result.cost_usd == pytest.approx(0.000123)
    assert result.has_timestamps is True
    assert len(seen) == 1


@pytest.mark.rule("RULE-131")
def test_hotwords_are_capped_at_fifty(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=GOOD))
    hotwords = [f"term{i}" for i in range(MAX_HOTWORDS + 10)]
    engine.transcribe(make_audio(tmp_path), hotwords=hotwords)
    body = seen[0].content
    assert b"term49" in body
    assert b"term50" not in body


@pytest.mark.rule("RULE-058")
def test_large_audio_hint_becomes_a_fatal_error_with_size(tmp_path: Path):
    engine, _ = make_engine(
        tmp_path,
        lambda _r: httpx.Response(
            400, text="This model does not support large audio inputs."
        ),
    )
    with pytest.raises(FatalError, match="体积上限"):
        engine.transcribe(make_audio(tmp_path))


@pytest.mark.rule("RULE-058")
def test_oversize_file_is_blocked_locally_before_spending_a_call(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=GOOD))
    big = tmp_path / "big.mp3"
    with big.open("wb") as handle:
        handle.seek(15_400_001)
        handle.write(b"\0")
    with pytest.raises(FatalError, match="未发起付费请求"):
        engine.transcribe(big)
    assert seen == []


@pytest.mark.rule("RULE-059")
def test_429_is_recoverable_and_400_is_fatal(tmp_path: Path):
    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(429, text="slow down"))
    with pytest.raises(RecoverableError):
        engine.transcribe(make_audio(tmp_path))

    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(400, text='{"code":"bad"}'))
    with pytest.raises(UpstreamError):
        engine.transcribe(make_audio(tmp_path))


def test_missing_key_fails_before_any_request(tmp_path: Path):
    seen: list[httpx.Request] = []
    engine = OpenRouterEngine(
        Config(config_path=tmp_path / "config.env"),
        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)),
    )
    with pytest.raises(FatalError, match="OPENROUTER_API_KEY"):
        engine.transcribe(make_audio(tmp_path))
    assert seen == []


def test_non_json_response_is_fatal(tmp_path: Path):
    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(200, text="not json"))
    with pytest.raises(FatalError, match="非 JSON"):
        engine.transcribe(make_audio(tmp_path))


def test_text_falls_back_to_segments_when_absent(tmp_path: Path):
    payload = json.loads(json.dumps(GOOD))
    payload.pop("text")
    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(200, json=payload))
    assert engine.transcribe(make_audio(tmp_path)).text == "你好世界"
