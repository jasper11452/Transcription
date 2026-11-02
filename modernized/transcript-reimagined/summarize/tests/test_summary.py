"""总结：输出契约、分批、流式、错误分类与独立状态机（C7 / RULE-027 / RULE-070 / RULE-088）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.state import Store

from transcript_reimagined.summarize import (
    MAX_BATCH_CHARS,
    MAX_REASONING_CHARS,
    SummaryManager,
    summarize,
    summarize_stream,
)
from transcript_reimagined.summarize.summary import _http_error_message, _parse_content


def make_config(tmp_path: Path, *, key: str = "sk-test") -> Config:
    return Config(
        config_path=tmp_path / "config.env",
        glossary_path=tmp_path / "glossary.txt",
        openrouter_api_key=key,
        openrouter_base="https://summary.test/api/v1",
        summary_model="test/model",
    )


def completion(payload: dict, *, reasoning: str = "") -> httpx.Response:
    message = {"content": json.dumps(payload, ensure_ascii=False)}
    if reasoning:
        message["reasoning"] = reasoning
    return httpx.Response(200, json={"choices": [{"message": message}]})


# ---------------------------------------------------------------- 输出契约


@pytest.mark.rule("RULE-070")
def test_parse_content_normalizes_and_caps():
    raw = json.dumps(
        {
            "title": "标" * 100,
            "overview": "主" * 3000,
            "key_points": [f"点{i}" for i in range(10)],
            "action_items": [" 待办 ", "", "第二项"],
        }
    )
    result = _parse_content(raw)
    assert len(result["title"]) == 80
    assert len(result["overview"]) == 2000
    assert len(result["key_points"]) == 8
    assert result["action_items"] == ["待办", "第二项"]


@pytest.mark.rule("RULE-070")
def test_parse_content_rejects_empty_and_invalid():
    with pytest.raises(ValueError, match="格式不正确"):
        _parse_content("not json")
    with pytest.raises(ValueError, match="格式不正确"):
        _parse_content('{"title": "", "overview": ""}')
    with pytest.raises(ValueError, match="格式不正确"):
        _parse_content("[]")


@pytest.mark.rule("RULE-070")
def test_reasoning_is_capped():
    result = _parse_content('{"title":"T","overview":"O"}', "思" * (MAX_REASONING_CHARS + 10))
    assert len(result["reasoning"]) == MAX_REASONING_CHARS


# ---------------------------------------------------------------- 请求与错误


@pytest.mark.rule("RULE-027")
def test_summarize_single_batch(tmp_path: Path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion(
            {"title": "标题", "overview": "主旨", "key_points": ["一"], "action_items": []}
        )

    result = summarize(make_config(tmp_path), "一段转录", transport=httpx.MockTransport(handler))
    assert result["title"] == "标题"
    assert result["key_points"] == ["一"]
    assert len(seen) == 1
    body = json.loads(seen[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 8000
    assert body["stream"] is False
    assert seen[0].headers["authorization"] == "Bearer sk-test"


@pytest.mark.rule("RULE-027")
def test_long_material_is_batched_and_then_summarized(tmp_path: Path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion({"title": "T", "overview": "O", "key_points": [], "action_items": []})

    text = "字" * (MAX_BATCH_CHARS + 100)
    summarize(make_config(tmp_path), text, transport=httpx.MockTransport(handler))
    # 两个批次各归纳一次，再把归纳结果汇总一次。
    assert len(seen) == 3


@pytest.mark.rule("RULE-027")
def test_summarize_rejects_empty_material(tmp_path: Path):
    with pytest.raises(ValueError, match="为空"):
        summarize(make_config(tmp_path), "   ")


@pytest.mark.rule("RULE-088")
def test_http_error_messages_are_actionable_and_do_not_echo_the_body():
    response = httpx.Response(401, json={"error": {"message": "bad key"}})
    message = _http_error_message(response, "m")
    assert "401" in message and "bad key" in message
    assert "Authorization" not in message
    assert "sk-" not in message
    assert "429" in _http_error_message(httpx.Response(429, text="slow"), "m")
    assert "404" in _http_error_message(httpx.Response(404), "m")


# ---------------------------------------------------------------- 流式


@pytest.mark.rule("RULE-027")
def test_stream_emits_partials_and_parses_final_json(tmp_path: Path):
    parts = ['{"title":"标题",', '"overview":"主旨","key_points":[],"action_items":[]}']
    body = "".join(
        "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n"
        for piece in parts
    ) + "data: [DONE]\n\n"

    partials: list[tuple[str, str]] = []
    result = summarize_stream(
        make_config(tmp_path),
        "材料",
        lambda content, reasoning: partials.append((content, reasoning)),
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, text=body)),
    )
    assert result["title"] == "标题"
    assert partials, "流式增量至少回传一次"


# ---------------------------------------------------------------- 独立状态机


def _done_task(store: Store, tmp_path: Path, *, text: str = "转录正文") -> int:
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    txt = tmp_path / "meeting.txt"
    txt.write_text(text, encoding="utf-8")
    store.update_task(tid, status="done", txt_path=str(txt))
    return tid


def _wait_summary(store: Store, tid: int, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = store.get_summary(tid)
        if state["status"] not in {"waiting", "running"}:
            return state
        time.sleep(0.01)
    raise AssertionError("总结没有在超时内结束")


@pytest.mark.rule("RULE-088")
def test_manager_enable_runs_and_does_not_touch_task_status(tmp_path: Path):
    store = Store(tmp_path / "state.db")
    tid = _done_task(store, tmp_path)

    def generate(config, text, on_partial=None):
        assert text == "转录正文"
        if on_partial:
            on_partial('{"title":', "思考")
        return {"title": "T", "overview": "O", "key_points": [], "action_items": []}

    manager = SummaryManager(make_config(tmp_path), store, generate=generate)
    try:
        manager.enable(tid)
        state = _wait_summary(store, tid)
        assert state["status"] == "done"
        assert state["content"]["title"] == "T"
        assert store.get_task(tid).status == "done", "总结失败/成功都不改变转录终态"
        payload = manager.payload(tid)
        assert payload["available"] is True
        assert payload["model"] == "test/model"
    finally:
        manager.shutdown()


@pytest.mark.rule("RULE-088")
def test_manager_requires_a_key(tmp_path: Path):
    store = Store(tmp_path / "state.db")
    tid = _done_task(store, tmp_path)
    manager = SummaryManager(make_config(tmp_path, key=""), store)
    try:
        with pytest.raises(ValueError, match="API Key"):
            manager.enable(tid)
    finally:
        manager.shutdown()


@pytest.mark.rule("RULE-088")
def test_manager_interrupts_running_summaries_at_startup(tmp_path: Path):
    store = Store(tmp_path / "state.db")
    tid = _done_task(store, tmp_path)
    store.set_summary(tid, enabled=True, status="running")
    manager = SummaryManager(make_config(tmp_path), store, generate=lambda *a, **k: {})
    try:
        assert store.get_summary(tid)["status"] == "failed"
        assert "中断" in store.get_summary(tid)["error"]
    finally:
        manager.shutdown()


@pytest.mark.rule("RULE-088")
def test_manager_does_not_start_for_a_task_that_is_not_done(tmp_path: Path):
    store = Store(tmp_path / "state.db")
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.set_summary(tid, enabled=True, status="waiting")
    manager = SummaryManager(make_config(tmp_path), store, generate=lambda *a, **k: {})
    try:
        manager.start_if_enabled(tid)
        assert store.get_summary(tid)["status"] == "waiting"
    finally:
        manager.shutdown()
