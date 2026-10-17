"""必剪适配器：四步上传、句级时间戳、412 进程级冷却（RULE-015 / RULE-016 / RULE-054 / RULE-109）。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import FatalError, RecoverableError

from transcript_reimagined.engines import bcut
from transcript_reimagined.engines.bcut import BcutEngine

RESULT = {
    "utterances": [
        {"start_time": 0, "end_time": 1900, "transcript": "转录工具冒烟测试"},
        {"start_time": 1900, "end_time": 3000, "transcript": "今天讨论三件事"},
        {"start_time": 3000, "end_time": 3100, "transcript": "   "},
    ]
}


def make_mp3(tmp_path: Path) -> Path:
    path = tmp_path / "chunk.mp3"
    path.write_bytes(b"fake-mp3-bytes")
    return path


def happy_handler(request: httpx.Request, seen: list[httpx.Request]) -> httpx.Response:
    seen.append(request)
    if request.method == "PUT":
        return httpx.Response(200, headers={"Etag": "etag-1"})
    path = request.url.path
    if path == "/resource/create":
        return httpx.Response(
            200,
            json={
                "data": {
                    "in_boss_key": "key",
                    "upload_id": "upload",
                    "upload_urls": ["https://upload.test/part-0"],
                    "per_size": 5 * 1024 * 1024,
                    "resource_id": "resource",
                }
            },
        )
    if path == "/resource/create/complete":
        return httpx.Response(200, json={"data": {"download_url": "https://dl.test/a.mp3"}})
    if path == "/task":
        return httpx.Response(200, json={"data": {"task_id": "task-1"}})
    if path == "/task/result":
        return httpx.Response(200, json={"data": {"state": 4, "result": RESULT}})
    return httpx.Response(404, text=f"unexpected {request.method} {path}")


def make_engine(tmp_path: Path, handler, **kwargs) -> tuple[BcutEngine, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    config = Config(config_path=tmp_path / "config.env", bcut_base="https://bcut.test")
    return (
        BcutEngine(
            config,
            transport=httpx.MockTransport(lambda r: handler(r, seen)),
            **kwargs,
        ),
        seen,
    )


@pytest.mark.rule("RULE-015")
@pytest.mark.rule("RULE-016")
def test_full_four_step_flow_yields_segments(tmp_path: Path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request, calls: list[httpx.Request]) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, headers={"Etag": "etag-1"})
        path = request.url.path
        if path == "/resource/create":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "in_boss_key": "key",
                        "upload_id": "upload",
                        "upload_urls": ["https://upload.test/part-0"],
                        "per_size": 5 * 1024 * 1024,
                        "resource_id": "resource",
                    }
                },
            )
        if path == "/resource/create/complete":
            return httpx.Response(200, json={"data": {"download_url": "https://dl.test/a.mp3"}})
        if path == "/task":
            return httpx.Response(200, json={"data": {"task_id": "task-1"}})
        return httpx.Response(200, json={"data": {"state": 4, "result": RESULT}})

    engine = BcutEngine(
        Config(config_path=tmp_path / "config.env", bcut_base="https://bcut.test"),
        transport=httpx.MockTransport(lambda r: seen.append(r) or handler(r, seen)),
    )
    result = engine.transcribe(make_mp3(tmp_path), language=None)
    assert [s.text for s in result.segments] == ["转录工具冒烟测试", "今天讨论三件事"]
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == pytest.approx(1.9)
    assert result.text == "转录工具冒烟测试今天讨论三件事"  # 无分隔拼接
    assert result.cost_usd == 0.0
    assert result.has_timestamps is True
    assert [r.method for r in seen] == ["POST", "PUT", "POST", "POST", "GET"]


@pytest.mark.rule("RULE-054")
def test_non_mp3_is_rejected_before_any_network_call(tmp_path: Path):
    seen: list[httpx.Request] = []
    engine = BcutEngine(
        Config(config_path=tmp_path / "config.env", bcut_base="https://bcut.test"),
        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(500)),
    )
    wrong = tmp_path / "chunk.wav"
    wrong.write_bytes(b"not-mp3")
    with pytest.raises(FatalError, match="按 mp3 声明"):
        engine.transcribe(wrong)
    assert seen == []


@pytest.mark.rule("RULE-109")
def test_412_sets_a_process_wide_cooldown(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bcut, "_banned_until", 0.0)
    seen: list[httpx.Request] = []

    def banned(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "PUT":
            return httpx.Response(200, headers={"Etag": "etag-1"})
        path = request.url.path
        if path == "/resource/create":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "in_boss_key": "k",
                        "upload_id": "u",
                        "upload_urls": ["https://upload.test/p"],
                        "per_size": 5 * 1024 * 1024,
                        "resource_id": "r",
                    }
                },
            )
        if path == "/resource/create/complete":
            return httpx.Response(200, json={"data": {"download_url": "https://dl.test/a.mp3"}})
        return httpx.Response(412, text='{"code":-412,"message":"request was banned"}')

    engine = BcutEngine(
        Config(config_path=tmp_path / "config.env", bcut_base="https://bcut.test"),
        transport=httpx.MockTransport(banned),
    )
    with pytest.raises(FatalError, match="412"):
        engine.transcribe(make_mp3(tmp_path))
    assert bcut.cooldown_remaining_s() > 0

    # D6：另一个实例也必须看到同一个冷却（进程级），且不再发请求。
    calls_before = len(seen)
    other = BcutEngine(
        Config(config_path=tmp_path / "config.env", bcut_base="https://bcut.test"),
        transport=httpx.MockTransport(banned),
    )
    with pytest.raises(FatalError, match="冷却期"):
        other.transcribe(make_mp3(tmp_path))
    assert len(seen) == calls_before


@pytest.mark.rule("RULE-109")
def test_cooldown_expiry_allows_requests_again(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bcut, "_banned_until", 0.0)
    engine, seen = make_engine(tmp_path, happy_handler)
    assert engine.transcribe(make_mp3(tmp_path)).segments
    assert len(seen) == 5


@pytest.mark.rule("RULE-108")
def test_poll_timeout_is_recoverable(tmp_path: Path):
    def handler(request: httpx.Request, _seen: list[httpx.Request]) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, headers={"Etag": "e"})
        path = request.url.path
        if path == "/resource/create":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "in_boss_key": "k",
                        "upload_id": "u",
                        "upload_urls": ["https://upload.test/p"],
                        "per_size": 5 * 1024 * 1024,
                        "resource_id": "r",
                    }
                },
            )
        if path == "/resource/create/complete":
            return httpx.Response(200, json={"data": {"download_url": "https://dl.test/a.mp3"}})
        if path == "/task":
            return httpx.Response(200, json={"data": {"task_id": "t"}})
        return httpx.Response(200, json={"data": {"state": 3}})

    engine, _ = make_engine(
        tmp_path, handler, sleep=lambda _s: None, poll_timeout_s=0.1
    )
    with pytest.raises(RecoverableError, match="等待超过"):
        engine.transcribe(make_mp3(tmp_path))


def test_empty_utterances_are_fatal(tmp_path: Path):
    def handler(request: httpx.Request, _seen: list[httpx.Request]) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, headers={"Etag": "e"})
        path = request.url.path
        if path == "/resource/create":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "in_boss_key": "k",
                        "upload_id": "u",
                        "upload_urls": ["https://upload.test/p"],
                        "per_size": 5 * 1024 * 1024,
                        "resource_id": "r",
                    }
                },
            )
        if path == "/resource/create/complete":
            return httpx.Response(200, json={"data": {"download_url": "https://dl.test/a.mp3"}})
        if path == "/task":
            return httpx.Response(200, json={"data": {"task_id": "t"}})
        return httpx.Response(200, json={"data": {"state": 4, "result": {"utterances": []}}})

    engine, _ = make_engine(tmp_path, handler)
    with pytest.raises(FatalError, match="空结果"):
        engine.transcribe(make_mp3(tmp_path))
