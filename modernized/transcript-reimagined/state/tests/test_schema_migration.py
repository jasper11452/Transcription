"""schema 迁移：旧库补列，不重建、不丢数据。

方案书 Phase 2 的决定：保留现有 `state.db`，启动时只做幂等加列迁移。这里用一个
「旧版 schema」的库验证 `segments_json` 与 `progress` 会被补上，且已有行保留。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from transcript_reimagined.state import Store

OLD_SCHEMA = """
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    mode TEXT NOT NULL,
    artifact TEXT NOT NULL,
    engine TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    duration_s REAL,
    audio_seconds REAL,
    cost_usd REAL,
    chars INTEGER,
    out_dir TEXT,
    txt_path TEXT,
    srt_path TEXT,
    raw_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE chunks (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    text TEXT,
    words_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    updated_at TEXT,
    PRIMARY KEY (task_id, idx)
);
CREATE TABLE task_summaries (
    task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'disabled',
    content TEXT,
    error TEXT,
    model TEXT
);
INSERT INTO tasks (name, source_path, mode, artifact, status, created_at, updated_at)
VALUES ('历史任务', '/tmp/old.m4a', 'offline', 'txt', 'done', '2026-10-01T00:00:00+00:00',
        '2026-10-01T00:00:00+00:00');
INSERT INTO chunks (task_id, idx, start, end, status, text, attempts)
VALUES (1, 0, 0, 60, 'done', '历史分片', 1);
"""


def test_migration_adds_missing_columns_without_rebuilding(tmp_path: Path):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()

    store = Store(db)

    task = store.get_task(1)
    assert task is not None
    assert task.name == "历史任务"
    assert task.progress == 0.0  # 新列默认值
    chunk = store.get_chunk(1, 0)
    assert chunk is not None
    assert chunk.text == "历史分片"
    assert chunk.segments == []  # 新列可为空

    with store._conn() as check:  # noqa: SLF001 - 验证迁移结果
        task_cols = {r["name"] for r in check.execute("PRAGMA table_info(tasks)")}
        chunk_cols = {r["name"] for r in check.execute("PRAGMA table_info(chunks)")}
    assert "progress" in task_cols
    assert "segments_json" in chunk_cols


def test_migration_is_idempotent(tmp_path: Path):
    db = tmp_path / "state.db"
    Store(db)
    Store(db)
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
    assert "progress" in cols
