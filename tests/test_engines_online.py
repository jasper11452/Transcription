"""在线引擎测试。

三条路全部用**录制的真实响应**做 mock（`tests/data/*.json`），并在 conftest 里
禁止真实网络请求——单元测试不该带着真密钥去打上游。

覆盖重点：请求形状（尤其百炼的 `parameters.format`，缺它会 400）、
时间戳解析、错误分类（可重试 vs 不可重试）、以及"本地能判定的错误先本地拦住"。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from transcript.config import DASHSCOPE_MAX_CHUNK_S, Config
from transcript.engines.base import (
    ONLINE_ENGINES,
    build_engine,
    chunk_max_for,
    engine_catalog,
    engine_kind_from_name,
    required_key_attrs,
    resolve_kind,
)
from transcript.engines.bcut import BcutEngine
from transcript.engines.dashscope import DashScopeEngine
from transcript.engines.openrouter import OpenRouterEngine
from transcript.errors import FatalError, RecoverableError
from transcript.models import AudioInfo

DATA = Path(__file__).parent / "data"
DS_FIXTURE = json.loads((DATA / "dashscope_native_fixture.json").read_text(encoding="utf-8"))
BCUT_FIXTURE = json.loads((DATA / "bcut_fixture.json").read_text(encoding="utf-8"))

MAI_OK = {
    "text": "转录工具冒烟测试。今天讨论三件事：第一，离线转写的质量。",
    "usage": {"seconds": 12, "cost": 0.0003333333333333333},
    "language": "zh",
    "duration": 11.88,
    "segments": [
        {
            "id": 0,
            "start": 0,
            "end": 11.875,
            "text": "转录工具冒烟测试。今天讨论三件事：第一，离线转写的质量。",
        }
    ],
}


@pytest.fixture(scope="module")
def audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """一段**真实**的 mp3。

    用假字节会让测试失去意义：百炼引擎会先 ffprobe 卡时长，而"能不能解析"
    恰好是上游最在意的部分（m4a 会被直接 400）。
    """
    import subprocess

    out = tmp_path_factory.mktemp("audio") / "chunk.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(out),
        ],
        check=True,
    )
    return out


def transport_for(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def make_config(tmp_path: Path, **kwargs) -> Config:
    cfg = Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "s.db",
        output_dir=tmp_path / "out",
        glossary_path=tmp_path / "g.txt",
    )
    for key, value in kwargs.items():
        setattr(cfg, key, value)
    return cfg


# ==================== 百炼（qwen-audio-3.1-asr-flash，原生接口） ====================


def test_dashscope_request_shape_is_the_one_that_works(audio: Path, tmp_path: Path):
    """回归护栏：原生端点 + base64 data URL + `parameters.format`。

    这三样缺一样就是当初绕了好几轮的 400 `format is empty`。
    """
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=DS_FIXTURE)

    cfg = make_config(tmp_path, dashscope_api_key="sk-secret-1234")
    engine = DashScopeEngine(cfg, transport=transport_for(handler))
    engine.transcribe(audio, language="zh")

    assert "/api/v1/services/aigc/multimodal-generation/generation" in seen["url"]
    body = seen["body"]
    assert body["model"] == cfg.dashscope_model  # 默认 qwen-audio-3.1-asr-flash
    audio_item = body["input"]["messages"][0]["content"][0]
    assert audio_item["audio"].startswith("data:audio/mp3;base64,")
    # format 必须在 parameters 里；这是这个模型唯一的"必传参数"
    assert body["parameters"]["format"] == "mp3"
    assert body["parameters"]["asr_options"]["language"] == "zh"
    assert seen["auth"] == "Bearer sk-secret-1234"


def test_dashscope_parses_word_timestamps_into_segments(audio: Path, tmp_path: Path):
    cfg = make_config(tmp_path, dashscope_api_key="k")
    engine = DashScopeEngine(
        cfg, transport=transport_for(lambda r: httpx.Response(200, json=DS_FIXTURE))
    )
    result = engine.transcribe(audio, language="zh")

    assert "冒烟测试" in result.text
    assert result.has_timestamps is True
    assert result.segments, "字级时间戳必须转成段落"
    assert result.audio_seconds == 12.0  # usage.duration
    assert engine.max_chunk_s == DASHSCOPE_MAX_CHUNK_S  # 单次上限声明在引擎上

    prev_end = 0.0
    for seg in result.segments:
        assert seg.end > seg.start
        assert seg.start >= prev_end - 1e-6, "时间必须单调不减"
        prev_end = seg.end
    assert result.segments[-1].end > 8.0


def test_dashscope_keeps_every_character_of_the_text(audio: Path, tmp_path: Path):
    from transcript.align import normalize_for_compare

    cfg = make_config(tmp_path, dashscope_api_key="k")
    engine = DashScopeEngine(
        cfg, transport=transport_for(lambda r: httpx.Response(200, json=DS_FIXTURE))
    )
    result = engine.transcribe(audio)
    joined = normalize_for_compare("".join(s.text for s in result.segments))
    assert joined == normalize_for_compare(result.text)


def test_dashscope_duration_too_long_is_fatal_and_explained(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "code": "AUDIO_DURATION_TOO_LONG",
                "message": "audio duration (330000.0ms) over service process (300s)",
            },
        )

    cfg = make_config(tmp_path, dashscope_api_key="k")
    engine = DashScopeEngine(cfg, transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "上限" in str(exc.value)


def test_dashscope_format_empty_error_points_at_the_cause(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "format is empty", "code": "UNSUPPORTED_FORMAT"}}
        )

    cfg = make_config(tmp_path, dashscope_api_key="k")
    engine = DashScopeEngine(cfg, transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "format" in str(exc.value)


def test_dashscope_transient_errors_are_recoverable(audio: Path, tmp_path: Path):
    for status in (429, 503):
        cfg = make_config(tmp_path, dashscope_api_key="k")
        engine = DashScopeEngine(
            cfg, transport=transport_for(lambda r, s=status: httpx.Response(s, text="busy"))
        )
        with pytest.raises(RecoverableError):
            engine.transcribe(audio)


def test_dashscope_network_error_is_recoverable(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    cfg = make_config(tmp_path, dashscope_api_key="k")
    engine = DashScopeEngine(cfg, transport=transport_for(handler))
    with pytest.raises(RecoverableError):
        engine.transcribe(audio)


def test_dashscope_without_key_makes_no_request(audio: Path, tmp_path: Path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=DS_FIXTURE)

    engine = DashScopeEngine(make_config(tmp_path), transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "DASHSCOPE_API_KEY" in str(exc.value)
    assert calls == []


def test_dashscope_rejects_unknown_container_locally(audio: Path, tmp_path: Path):
    bad = tmp_path / "a.ogg"
    bad.write_bytes(b"OggS" + b"\x00" * 32)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=DS_FIXTURE)

    engine = DashScopeEngine(
        make_config(tmp_path, dashscope_api_key="k"), transport=transport_for(handler)
    )
    with pytest.raises(FatalError) as exc:
        engine.transcribe(bad)
    assert "归一化" in str(exc.value)
    assert calls == []


def test_dashscope_guards_duration_locally_before_spending_a_request(
    audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """本地就能判定的超限，不该花一次带密钥的请求去换上游报错。"""
    calls: list[str] = []
    monkeypatch.setattr(
        "transcript.engines.dashscope.audio_mod.probe",
        lambda path: AudioInfo(
            path=Path(path),
            duration=330.0,
            size_bytes=1,
            codec="mp3",
            sample_rate=16000,
            channels=1,
            has_audio=True,
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=DS_FIXTURE)

    engine = DashScopeEngine(
        make_config(tmp_path, dashscope_api_key="k"), transport=transport_for(handler)
    )
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "300" in str(exc.value) and "CHUNK_MAX_S" in str(exc.value)
    assert calls == []


def test_dashscope_error_never_leaks_the_key(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "X", "message": "bad"})

    cfg = make_config(tmp_path, dashscope_api_key="sk-verysecret-9999")
    engine = DashScopeEngine(cfg, transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "sk-verysecret-9999" not in str(exc.value)


# ==================== OpenRouter（mai-transcribe-2） ====================


def test_openrouter_parses_segments_and_cost(audio: Path, tmp_path: Path):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(200, json=MAI_OK)

    cfg = make_config(tmp_path, openrouter_api_key="or-secret")
    engine = OpenRouterEngine(cfg, "microsoft/mai-transcribe-2", transport=transport_for(handler))
    result = engine.transcribe(audio)

    assert result.has_timestamps is True
    assert result.segments[0].end == 11.875
    assert result.cost_usd is not None and result.cost_usd < 0.001
    assert result.audio_seconds == 12.0
    assert "/audio/transcriptions" in seen["url"]
    assert "multipart/form-data" in seen["content_type"]


def test_openrouter_large_input_error_explains_the_cause(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "The selected model does not support large audio inputs"}},
        )

    cfg = make_config(tmp_path, openrouter_api_key="k")
    engine = OpenRouterEngine(cfg, transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "体积上限" in str(exc.value)


def test_openrouter_request_body_too_large_is_fatal_with_size(audio: Path, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413,
            text="Request body of 66021394 bytes exceeds the maximum "
            "allowed size of 52428800 bytes",
        )

    cfg = make_config(tmp_path, openrouter_api_key="k")
    engine = OpenRouterEngine(cfg, transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "MB" in str(exc.value)


def test_openrouter_rate_limit_is_recoverable(audio: Path, tmp_path: Path):
    cfg = make_config(tmp_path, openrouter_api_key="k")
    engine = OpenRouterEngine(
        cfg, transport=transport_for(lambda r: httpx.Response(429, text="rate limited"))
    )
    with pytest.raises(RecoverableError):
        engine.transcribe(audio)


def test_openrouter_without_key_fails_fast(audio: Path, tmp_path: Path):
    engine = OpenRouterEngine(make_config(tmp_path))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_openrouter_falls_back_to_segments_when_text_missing(audio: Path, tmp_path: Path):
    payload = {k: v for k, v in MAI_OK.items() if k != "text"}
    cfg = make_config(tmp_path, openrouter_api_key="k")
    engine = OpenRouterEngine(
        cfg, transport=transport_for(lambda r: httpx.Response(200, json=payload))
    )
    assert "冒烟测试" in engine.transcribe(audio).text


# ==================== 必剪（bcut，匿名免费） ====================


def bcut_transport(
    *,
    states: list[int] | None = None,
    fail_at: str | None = None,
    fail_status: int = 500,
    fail_body: str = "upstream boom",
) -> httpx.MockTransport:
    """按真实四步流程回放必剪接口（响应取自 tests/data/bcut_fixture.json）。"""
    pending = list(states or [4])
    fixture = BCUT_FIXTURE

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if fail_at and fail_at in path and request.method != "GET":
            return httpx.Response(fail_status, text=fail_body)
        if path.endswith("/resource/create"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "in_boss_key": "boss-key",
                        "resource_id": "res-1",
                        "upload_id": "up-1",
                        "upload_urls": ["https://up.example/part1"],
                        "per_size": fixture["create"]["per_size"],
                    }
                },
            )
        if request.method == "PUT":
            return httpx.Response(200, headers={"Etag": "etag-1"})
        if path.endswith("/resource/create/complete"):
            return httpx.Response(
                200, json={"data": {"download_url": fixture["complete"]["download_url"]}}
            )
        if path.endswith("/task"):
            return httpx.Response(200, json={"data": {"task_id": fixture["task"]["task_id"]}})
        if path.endswith("/task/result"):
            state = pending.pop(0) if len(pending) > 1 else pending[0]
            if state == 4:
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "state": 4,
                            "result": json.dumps(fixture["result"], ensure_ascii=False),
                        }
                    },
                )
            return httpx.Response(200, json={"data": {"state": state}})
        return httpx.Response(404, text=f"unexpected {request.method} {path}")

    return httpx.MockTransport(handler)


def test_bcut_full_flow_produces_segments(audio: Path, tmp_path: Path):
    cfg = make_config(tmp_path)
    engine = BcutEngine(cfg, transport=bcut_transport(), sleep=lambda s: None)
    result = engine.transcribe(audio)

    assert result.has_timestamps is True
    assert result.cost_usd == 0.0  # 免费接口
    assert len(result.segments) == len(BCUT_FIXTURE["result"]["utterances"])
    assert "冒烟测试" in result.text
    assert result.segments[0].start == 0.0
    assert result.segments[0].end > 1.0
    assert result.segments[-1].end > 9.0
    # 时间单调
    prev = 0.0
    for seg in result.segments:
        assert seg.start >= prev - 1e-6
        prev = seg.end


def test_bcut_polls_until_done(audio: Path, tmp_path: Path):
    """state 未到 4 时要继续等，不能把中间态当成结果。"""
    cfg = make_config(tmp_path)
    engine = BcutEngine(cfg, transport=bcut_transport(states=[1, 2, 4]), sleep=lambda s: None)
    result = engine.transcribe(audio)
    assert result.segments


def test_bcut_poll_timeout_is_recoverable(audio: Path, tmp_path: Path):
    cfg = make_config(tmp_path)
    engine = BcutEngine(
        cfg, transport=bcut_transport(states=[1]), sleep=lambda s: None, poll_timeout_s=0.0
    )
    with pytest.raises(RecoverableError) as exc:
        engine.transcribe(audio)
    assert "等待" in str(exc.value)


def test_bcut_upload_failure_is_recoverable(audio: Path, tmp_path: Path):
    cfg = make_config(tmp_path)
    engine = BcutEngine(
        cfg, transport=bcut_transport(fail_at="/resource/create"), sleep=lambda s: None
    )
    with pytest.raises(RecoverableError):
        engine.transcribe(audio)


def test_bcut_412_explains_risk_control_and_suggests_resume(audio: Path, tmp_path: Path):
    """412 是 B 站风控（request was banned），不是"参数错了"。

    实测（2026-09-19，55 分钟长音频）：`POST /task` 返回
    `{"code":-412,"message":"request was banned"}`，建任务这一步被挡；
    文案必须给出可执行的出路（等一等 / 续跑 / 换引擎），而不是笼统的"上游拒绝请求"。
    风控是对整个接口的：冷却期内不能再发请求，否则只会延长封禁。
    """
    cfg = make_config(tmp_path)
    calls: list[str] = []
    base = bcut_transport(
        fail_at="/task",
        fail_status=412,
        fail_body='{"code":-412,"message":"request was banned","ttl":1}',
    )

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return base.handler(request)  # type: ignore[attr-defined]

    engine = BcutEngine(
        cfg,
        transport=httpx.MockTransport(counting_handler),
        sleep=lambda s: None,
    )
    with pytest.raises(FatalError) as exc:
        engine.transcribe(audio)
    message = str(exc.value)
    assert "412" in message
    assert "风控" in message
    assert "续跑" in message

    attempts = len(calls)
    with pytest.raises(FatalError) as exc2:
        engine.transcribe(audio)
    assert "冷却期" in str(exc2.value)
    assert len(calls) == attempts, "冷却期内不该再打上游"


def test_bcut_requires_mp3_without_touching_the_network(tmp_path: Path):
    """接口把上传物声明成 mp3，声明与实际不符时对端行为不可预期，本地先拦。"""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    engine = BcutEngine(make_config(tmp_path), transport=transport_for(handler))
    with pytest.raises(FatalError) as exc:
        engine.transcribe(wav)
    assert "mp3" in str(exc.value)
    assert calls == []


def test_bcut_rejects_empty_payload(tmp_path: Path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    engine = BcutEngine(make_config(tmp_path))
    with pytest.raises(FatalError):
        engine.transcribe(empty)


def test_bcut_needs_no_credentials(audio: Path, tmp_path: Path):
    """匿名接口：没有任何密钥也应能跑通（这是它作为在线选项的价值）。"""
    cfg = make_config(tmp_path)  # 故意不配任何 key
    assert cfg.dashscope_api_key == "" and cfg.openrouter_api_key == ""
    result = BcutEngine(cfg, transport=bcut_transport(), sleep=lambda s: None).transcribe(audio)
    assert result.segments


# ==================== 引擎选择与限制 ====================


def test_resolve_kind_by_artifact_and_explicit_choice(tmp_path: Path):
    cfg = make_config(tmp_path)
    assert resolve_kind(cfg, mode="offline", artifact="txt") == "offline"
    assert resolve_kind(cfg, mode="online", artifact="txt") == "dashscope"
    assert resolve_kind(cfg, mode="online", artifact="srt") == "openrouter"
    # 显式指定覆盖按产物映射；bcut 同时能出 txt 与 srt
    for artifact in ("txt", "srt"):
        assert resolve_kind(cfg, mode="online", artifact=artifact, online_engine="bcut") == "bcut"
    assert (
        resolve_kind(cfg, mode="online", artifact="srt", online_engine="dashscope") == "dashscope"
    )


def test_resolve_kind_rejects_unknown(tmp_path: Path):
    cfg = make_config(tmp_path, online_engine="magic")
    with pytest.raises(ValueError, match="未知的在线引擎"):
        resolve_kind(cfg, mode="online", artifact="txt")


def test_required_key_attrs_matches_the_engine_that_will_run(tmp_path: Path):
    cfg = make_config(tmp_path)
    assert required_key_attrs(cfg, mode="offline", artifact="txt") == ()
    assert required_key_attrs(cfg, mode="online", artifact="txt") == ("dashscope_api_key",)
    assert required_key_attrs(cfg, mode="online", artifact="srt") == ("openrouter_api_key",)
    assert required_key_attrs(cfg, mode="online", artifact="srt", online_engine="bcut") == ()
    assert required_key_attrs(cfg, mode="online", artifact="txt", online_engine="dashscope") == (
        "dashscope_api_key",
    )


def test_engine_kind_from_name_for_resume(tmp_path: Path):
    assert engine_kind_from_name("dashscope:qwen-audio-3.0-asr-flash") == "dashscope"
    assert engine_kind_from_name("bcut:8") == "bcut"
    assert engine_kind_from_name("offline:qwen3-asr+whisper") == "offline"
    assert engine_kind_from_name("mystery") is None
    assert engine_kind_from_name(None) is None


def test_chunk_max_is_clamped_by_engine_limit(tmp_path: Path):
    cfg = make_config(tmp_path, chunk_max_s=600.0)
    # 百炼原生单次上限 300s → 切片必须收紧，否则注定被拒
    assert chunk_max_for(cfg, mode="online", artifact="txt") == DASHSCOPE_MAX_CHUNK_S
    cfg_small = make_config(tmp_path, chunk_max_s=120.0)
    assert chunk_max_for(cfg_small, mode="online", artifact="txt") == 120.0
    assert chunk_max_for(cfg_small, mode="offline", artifact="txt") == 120.0
    # bcut 没有时长上限声明 → 用配置值
    assert chunk_max_for(cfg, mode="online", artifact="srt", online_engine="bcut") == 600.0


def test_engine_catalog_lists_all_choices(tmp_path: Path):
    catalog = engine_catalog(make_config(tmp_path))
    ids = [e["id"] for e in catalog]
    assert ids == list(ONLINE_ENGINES)
    bcut = next(e for e in catalog if e["id"] == "bcut")
    assert bcut["needs_key"] == [], "必剪是匿名接口，不该要求密钥"
    dashscope = next(e for e in catalog if e["id"] == "dashscope")
    assert dashscope["max_chunk_s"] == DASHSCOPE_MAX_CHUNK_S


def test_build_engine_kinds(tmp_path: Path):
    cfg = make_config(tmp_path, dashscope_model="custom-ds", openrouter_model="custom-or")
    assert build_engine("dashscope", cfg, artifact="txt").model == "custom-ds"
    assert build_engine("openrouter", cfg, artifact="srt").model == "custom-or"
    assert build_engine("bcut", cfg, artifact="srt").name.startswith("bcut")
    assert build_engine("offline", cfg, artifact="txt").name.startswith("offline")
    with pytest.raises(ValueError, match="未知引擎"):
        build_engine("nope", cfg, artifact="txt")


def test_model_ids_are_configurable_from_file(tmp_path: Path):
    cfg_file = tmp_path / "config.env"
    cfg_file.write_text(
        "DASHSCOPE_API_KEY=k1\nOPENROUTER_API_KEY=k2\n"
        "ONLINE_ENGINE=bcut\nDASHSCOPE_MODEL=m1\nOPENROUTER_MODEL=m2\n",
        encoding="utf-8",
    )
    cfg = Config.load(cfg_file)
    assert cfg.online_engine == "bcut"
    assert cfg.dashscope_model == "m1"
    assert cfg.openrouter_model == "m2"
