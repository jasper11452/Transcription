"""百炼适配器：请求形状、错误分类、本地 300s 拦截（RULE-055 / RULE-056 / RULE-057 / RULE-128）。

用录制的原生响应夹具回放，不发起真实付费调用。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import FatalError, RecoverableError, UpstreamError

from transcript_reimagined.engines.dashscope import DashScopeEngine, _extract

FIXTURE = json.loads(
    (Path(__file__).parent / "data" / "dashscope_native_fixture.json").read_text(encoding="utf-8")
)


def make_audio(tmp_path: Path, suffix: str = ".wav") -> Path:
    path = tmp_path / f"chunk{suffix}"
    path.write_bytes(b"fake-audio-bytes")
    return path


def make_engine(tmp_path: Path, handler) -> tuple[DashScopeEngine, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    config = Config(config_path=tmp_path / "config.env", dashscope_api_key="sk-test")
    return DashScopeEngine(config, transport=httpx.MockTransport(wrapped)), seen


@pytest.mark.rule("RULE-017")
def test_native_response_is_mapped_to_words_and_text(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=FIXTURE))
    result = engine.transcribe(make_audio(tmp_path), language=None, duration_s=12.0)
    assert result.words
    assert result.words[0].text == "转录"
    assert result.words[0].start == pytest.approx(0.120)
    assert result.text.startswith("转录工具冒烟测试")
    assert result.has_timestamps is True
    assert result.cost_usd is None  # 按 token 计费，不猜
    assert result.audio_seconds == pytest.approx(FIXTURE["usage"]["duration"])
    assert len(seen) == 1


@pytest.mark.rule("RULE-056")
def test_request_carries_format_and_default_asr_options(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=FIXTURE))
    engine.transcribe(make_audio(tmp_path), language=None, duration_s=12.0)
    payload = json.loads(seen[0].content)
    assert payload["parameters"]["format"] == "wav"
    assert payload["parameters"]["asr_options"] == {"language": "zh", "enable_itn": True}
    assert payload["input"]["messages"][0]["content"][0]["audio"].startswith(
        "data:audio/wav;base64,"
    )
    assert seen[0].headers["authorization"] == "Bearer sk-test"


@pytest.mark.rule("RULE-056")
def test_unknown_container_is_rejected_before_the_request(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=FIXTURE))
    with pytest.raises(FatalError, match="只接受带已知容器"):
        engine.transcribe(make_audio(tmp_path, ".txt"), duration_s=1.0)
    assert seen == []


@pytest.mark.rule("RULE-057")
def test_oversize_chunk_is_blocked_locally_without_a_paid_call(tmp_path: Path):
    engine, seen = make_engine(tmp_path, lambda _r: httpx.Response(200, json=FIXTURE))
    with pytest.raises(FatalError, match="超过该模型单次上限 300s"):
        engine.transcribe(make_audio(tmp_path), duration_s=330.0)
    assert seen == []


@pytest.mark.rule("RULE-055")
def test_429_is_recoverable_and_400_is_fatal(tmp_path: Path):
    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(429, text='{"code":"Throttling"}'))
    with pytest.raises(RecoverableError):
        engine.transcribe(make_audio(tmp_path), duration_s=1.0)

    engine, _ = make_engine(tmp_path, lambda _r: httpx.Response(400, text='{"code":"Bad"}'))
    with pytest.raises(UpstreamError):
        engine.transcribe(make_audio(tmp_path), duration_s=1.0)


@pytest.mark.rule("RULE-055")
def test_duration_too_long_upstream_is_mapped_to_an_actionable_fatal(tmp_path: Path):
    engine, _ = make_engine(
        tmp_path,
        lambda _r: httpx.Response(400, json={"code": "AUDIO_DURATION_TOO_LONG",
                                             "message": "over service process (300s)"}),
    )
    with pytest.raises(FatalError, match="单次上限"):
        engine.transcribe(make_audio(tmp_path), duration_s=1.0)


@pytest.mark.rule("RULE-055")
def test_format_empty_upstream_is_mapped_to_an_actionable_fatal(tmp_path: Path):
    engine, _ = make_engine(
        tmp_path,
        lambda _r: httpx.Response(400, json={"code": "UNSUPPORTED_FORMAT",
                                             "message": "format is empty"}),
    )
    with pytest.raises(FatalError, match="format is empty"):
        engine.transcribe(make_audio(tmp_path), duration_s=1.0)


def test_missing_key_fails_before_any_request(tmp_path: Path):
    seen: list[httpx.Request] = []
    engine = DashScopeEngine(
        Config(config_path=tmp_path / "config.env"),
        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)),
    )
    with pytest.raises(FatalError, match="DASHSCOPE_API_KEY"):
        engine.transcribe(make_audio(tmp_path), duration_s=1.0)
    assert seen == []


def test_extract_falls_back_to_sentence_text_and_words():
    data = {
        "output": {
            "output": {
                "sentence": [{"text": "", "words": [{"text": "甲", "begin_time": 0, "end_time": 100}]}]
            }
        }
    }
    words, text = _extract(data)
    assert [w.text for w in words] == ["甲"]
    assert text == "甲"
