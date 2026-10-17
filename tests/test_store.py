"""持久化单测：分片续跑与"不存密钥"是这里的核心。"""

from __future__ import annotations

from pathlib import Path

from transcript.models import Word
from transcript.store import Store


def make_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "state.db")


def test_create_and_read_task(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(
        name="会议录音",
        source_path="/tmp/a.m4a",
        mode="offline",
        artifact="txt",
        engine="offline",
        duration_s=1800.0,
    )
    task = store.get_task(tid)
    assert task is not None
    assert task.status == "running"
    assert task.name == "会议录音"
    assert task.artifact == "txt"
    assert not task.is_terminal


def test_update_task_ignores_unknown_fields(tmp_path: Path):
    """只允许白名单字段，避免把任意 key（比如密钥）写进库。"""
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.update_task(tid, status="done", chars=42, DASHSCOPE_API_KEY="should-not-be-stored")
    task = store.get_task(tid)
    assert task is not None
    assert task.status == "done"
    assert task.chars == 42
    with store._conn() as conn:  # noqa: SLF001 - 测试直接验证库内容
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    assert "DASHSCOPE_API_KEY" not in cols


def test_chunks_roundtrip_with_words(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="srt")
    words = [Word("转", 0.0, 0.2, 0.9), Word("录", 0.2, 0.4, None)]
    store.upsert_chunk(
        tid, idx=0, start=0.0, end=60.0, status="done", text="转录", words=words, attempts=1
    )
    chunks = store.chunks_for(tid)
    assert len(chunks) == 1
    assert chunks[0].text == "转录"
    assert chunks[0].done
    assert chunks[0].words[0].text == "转"
    assert chunks[0].words[1].probability is None
    assert chunks[0].start == 0.0 and chunks[0].end == 60.0


def test_upsert_chunk_is_idempotent(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="online", artifact="txt")
    for _ in range(3):
        store.upsert_chunk(tid, idx=2, start=120.0, end=180.0, status="running", attempts=1)
    store.upsert_chunk(tid, idx=2, start=120.0, end=180.0, status="done", text="好")
    chunks = store.chunks_for(tid)
    assert len(chunks) == 1
    assert chunks[0].status == "done"
    assert chunks[0].text == "好"


def test_done_chunk_indices_supports_resume(tmp_path: Path):
    """续跑的关键：只重跑未完成的分片。"""
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.upsert_chunk(tid, idx=0, start=0, end=60, status="done", text="甲")
    store.upsert_chunk(tid, idx=1, start=60, end=120, status="failed", error="超时")
    store.upsert_chunk(tid, idx=2, start=120, end=180, status="done", text="丙")
    assert store.done_chunk_indices(tid) == {0, 2}


def test_failed_chunk_keeps_error_but_not_fake_text(tmp_path: Path):
    store = make_store(tmp_path)
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    store.upsert_chunk(
        tid,
        idx=0,
        start=0,
        end=60,
        status="failed",
        text="",
        error="上游拒绝请求（HTTP 400 unsupported format）",
    )
    chunk = store.chunks_for(tid)[0]
    assert chunk.status == "failed"
    assert chunk.text == ""
    assert "400" in (chunk.error or "")


def test_list_tasks_newest_first_and_delete_cascades(tmp_path: Path):
    store = make_store(tmp_path)
    first = store.create_task(name="a", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    second = store.create_task(name="b", source_path="/tmp/b.wav", mode="offline", artifact="srt")
    assert [t.id for t in store.list_tasks()] == [second, first]

    store.upsert_chunk(second, idx=0, start=0, end=1, status="done", text="x")
    store.delete_task(second)
    assert store.get_task(second) is None
    assert store.chunks_for(second) == []


def test_stats_aggregate(tmp_path: Path):
    store = make_store(tmp_path)
    for i in range(2):
        tid = store.create_task(
            name=f"n{i}", source_path=f"/tmp/{i}.wav", mode="online", artifact="txt"
        )
        store.update_task(tid, status="done", audio_seconds=600.0, cost_usd=0.0166, chars=1000)
    stats = store.stats()
    assert stats["tasks"] == 2
    assert abs(stats["cost_usd"] - 0.0332) < 1e-9
