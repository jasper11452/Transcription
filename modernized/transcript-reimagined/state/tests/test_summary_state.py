"""Agent 总结的独立状态：与转录终态解耦（C7）。

总结失败不改变任务的 done/failed；任务删除后后台总结不得重新建记录。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript_reimagined.state import Store


def make_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "state.db")


def test_default_summary_state(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    assert store.get_summary(tid) == {
        "enabled": False,
        "status": "disabled",
        "content": None,
        "error": None,
        "model": None,
    }


def test_summary_content_roundtrips_as_json(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    content = {"title": "标题", "key_points": ["一", "二"]}
    store.set_summary(tid, enabled=True, status="done", content=content, model="m")
    assert store.get_summary(tid) == {
        "enabled": True,
        "status": "done",
        "content": content,
        "error": None,
        "model": "m",
    }


@pytest.mark.rule("RULE-088")
def test_summary_failure_does_not_touch_task_status(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.update_task(tid, status="done")
    store.set_summary(tid, enabled=True, status="failed", error="上游超时")
    assert store.get_task(tid).status == "done"
    assert store.get_summary(tid)["status"] == "failed"


@pytest.mark.rule("RULE-088")
def test_interrupt_running_summaries(tmp_path: Path):
    store = make_store(tmp_path)
    a = store.create_task(name="a", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    b = store.create_task(name="b", source_path="/tmp/b.wav", mode="offline", artifact="txt")
    store.set_summary(a, enabled=True, status="running")
    store.set_summary(b, enabled=True, status="done")
    store.interrupt_summaries()
    assert store.get_summary(a)["status"] == "failed"
    assert "中断" in store.get_summary(a)["error"]
    assert store.get_summary(b)["status"] == "done"


def test_summary_is_not_recreated_after_task_delete(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.delete_task(tid)
    store.set_summary(tid, enabled=True, status="done")
    assert store.get_summary(tid)["status"] == "disabled"
