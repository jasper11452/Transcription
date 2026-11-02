"""Agent 总结：显式授权、文本请求、异步状态与失败重试。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from transcript.config import Config
from transcript.store import Store
from transcript.summary import SummaryManager, hot_word_list, summarize


def wait_for_status(store: Store, task_id: int, status: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = store.get_summary(task_id)
        if state["status"] == status:
            return state
        time.sleep(0.01)
    return store.get_summary(task_id)


def make_done_task(store: Store, *, txt_path: Path | None = None) -> int:
    task_id = store.create_task(
        name="summary-sample",
        source_path="/tmp/summary.m4a",
        mode="offline",
        artifact="srt",
    )
    store.update_task(task_id, status="done", txt_path=str(txt_path) if txt_path else None)
    if txt_path is None:
        store.upsert_chunk(task_id, idx=0, start=0.0, end=1.0, status="done", text="占位文字。")
    return task_id
    return task_id


def test_summary_requires_explicit_openrouter_key(config: Config, store: Store) -> None:
    task_id = make_done_task(store)
    called = False

    def generate(_config: Config, _text: str) -> dict:
        nonlocal called
        called = True
        return {"title": "未授权标题", "overview": "不应执行", "key_points": [], "action_items": []}

    manager = SummaryManager(config, store, generate=generate)
    try:
        payload = manager.payload(task_id)
        assert payload["available"] is False
        assert payload["status"] == "disabled"
        with pytest.raises(ValueError, match="OpenRouter"):
            manager.enable(task_id)
        assert called is False
        assert store.get_summary(task_id)["status"] == "disabled"
    finally:
        manager.shutdown()


def test_summary_generates_from_persisted_text_and_survives_reload(
    config: Config, store: Store, tmp_path: Path
) -> None:
    config.openrouter_api_key = "test-summary-key"
    transcript = tmp_path / "summary.txt"
    transcript.write_text("第一段文字。\n第二段文字。", encoding="utf-8")
    task_id = make_done_task(store, txt_path=transcript)
    started = threading.Event()
    seen: list[str] = []

    def generate(_config: Config, text: str) -> dict:
        seen.append(text)
        started.set()
        return {
            "title": "两段文字的内容标题",
            "overview": "两段文字",
            "key_points": ["第一段文字。", "第二段文字。"],
            "action_items": [],
        }

    manager = SummaryManager(config, store, generate=generate)
    try:
        response = manager.enable(task_id)
        assert response["enabled"] is True
        assert response["status"] in {"waiting", "running", "done"}
        assert started.wait(timeout=3)
        state = wait_for_status(store, task_id, "done")
        assert state["content"]["title"] == "两段文字的内容标题"
        assert state["content"]["overview"] == "两段文字"
        assert seen == ["第一段文字。\n第二段文字。"]

        reloaded = Store(config.state_db)
        assert reloaded.get_summary(task_id)["content"]["key_points"] == [
            "第一段文字。",
            "第二段文字。",
        ]
    finally:
        manager.shutdown()


def test_summary_failure_can_be_retried(config: Config, store: Store) -> None:
    config.openrouter_api_key = "test-summary-key"
    task_id = make_done_task(store)
    calls = 0
    started = threading.Event()

    def generate(_config: Config, _text: str) -> dict:
        nonlocal calls
        calls += 1
        started.set()
        if calls == 1:
            raise ValueError("模型暂时不可用")
        return {"title": "重试标题", "overview": "重试成功", "key_points": [], "action_items": []}

    manager = SummaryManager(config, store, generate=generate)
    try:
        manager.enable(task_id)
        assert started.wait(timeout=3)
        failed = wait_for_status(store, task_id, "failed")
        assert failed["error"] == "模型暂时不可用"

        started.clear()
        manager.enable(task_id)
        assert started.wait(timeout=3)
        done = wait_for_status(store, task_id, "done")
        assert done["content"]["overview"] == "重试成功"
        assert calls == 2
    finally:
        manager.shutdown()


def test_summary_request_sends_text_json_only() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "会议项目标题",
                                    "overview": "会议结论",
                                    "key_points": ["确认方案"],
                                    "action_items": ["发送纪要"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
            request=request,
        )

    config = Config(
        openrouter_api_key="test-summary-key",
        openrouter_base="https://summary.test/v1",
    )
    result = summarize(config, "会议转录文字", transport=httpx.MockTransport(handler))

    assert result["title"] == "会议项目标题"
    assert result["overview"] == "会议结论"
    assert seen["url"] == "https://summary.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-summary-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["messages"][-1]["content"] == "会议转录文字"
    assert "audio" not in body


def test_hot_words_are_sent_as_glossary_hint(tmp_path: Path) -> None:
    """裸热词直接写正确写法，系统提示里带上它们，便于总结统一写法。"""
    glossary = tmp_path / "glossary.txt"
    glossary.write_text("小新\n选号侠\n艾麦 -> 砹脉\n", encoding="utf-8")
    config = Config(
        openrouter_api_key="test-summary-key",
        openrouter_base="https://summary.test/v1",
        glossary_path=glossary,
    )
    assert hot_word_list(config) == ["小新", "选号侠", "砹脉"]

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "标题",
                                    "overview": "主旨",
                                    "key_points": [],
                                    "action_items": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
            request=request,
        )

    summarize(config, "小新和选号侠讨论了方案。", transport=httpx.MockTransport(handler))
    system_prompt = seen["body"]["messages"][0]["content"]
    assert "小新" in system_prompt
    assert "砹脉" in system_prompt
    assert "专有名词表" in system_prompt
    # 转录原文仍然作为独立消息，不被提示词污染
    assert seen["body"]["messages"][-1]["content"] == "小新和选号侠讨论了方案。"


def test_hot_word_list_is_empty_without_glossary(tmp_path: Path) -> None:
    config = Config(glossary_path=tmp_path / "missing.txt")
    assert hot_word_list(config) == []
