"""任务生命周期的终态集合与非法状态拒绝。

`RULE-072`（P0）与 `RULE-089`：终态恰好是 {done, failed}；`pending` / `running` /
`cancelling` 都是非终态。写错状态必须立刻报错，而不是把任意字符串存进库。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript_reimagined.state import TASK_STATUSES, TERMINAL_STATUSES, Store, task_flags


def make_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "state.db")


@pytest.mark.rule("RULE-089")
def test_terminal_set_is_exactly_done_and_failed():
    assert {"done", "failed"} == TERMINAL_STATUSES
    assert {"pending", "running", "cancelling", "done", "failed"} == TASK_STATUSES


@pytest.mark.rule("RULE-089")
def test_terminal_property(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    assert not store.get_task(tid).is_terminal
    store.update_task(tid, status="failed")
    assert store.get_task(tid).is_terminal


@pytest.mark.rule("RULE-089")
def test_invalid_task_status_is_rejected(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    with pytest.raises(ValueError, match="非法的任务状态"):
        store.update_task(tid, status="finished-ish")
    assert store.get_task(tid).status == "running"


@pytest.mark.rule("RULE-074")
def test_invalid_chunk_status_is_rejected(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    with pytest.raises(ValueError, match="非法的分片状态"):
        store.upsert_chunk(tid, idx=0, start=0, end=1, status="half-done")
    assert store.chunks_for(tid) == []


@pytest.mark.rule("RULE-081")
def test_interrupted_is_decided_server_side(tmp_path: Path):
    """Q10：running 状态 + 本进程无活 job = interrupted，由服务端给出。"""
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")

    alive = task_flags(store.get_task(tid), live_task_ids={tid})
    assert alive == {
        "running": True,
        "interrupted": False,
        "cancelling": False,
        "resumable": False,
    }

    orphan = task_flags(store.get_task(tid), live_task_ids=set())
    assert orphan == {
        "running": False,
        "interrupted": True,
        "cancelling": False,
        "resumable": True,
    }

    store.update_task(tid, status="done")
    done = task_flags(store.get_task(tid), live_task_ids=set())
    assert done == {
        "running": False,
        "interrupted": False,
        "cancelling": False,
        "resumable": False,
    }
