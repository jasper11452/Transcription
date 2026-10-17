"""任务与分片的持久化（单文件 SQLite）。

设计要点：
- **分片是续跑单位**：任何一片落盘后进程被杀，重启都从已完成的分片接着跑；
- 每次调用开一个短连接（WAL 模式），避免线程池里的连接共享问题；
- 这里**永远不存密钥**，只存路径、状态和度量。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .models import Segment, Word

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    source_path   TEXT    NOT NULL,
    mode          TEXT    NOT NULL,
    artifact      TEXT    NOT NULL,
    engine        TEXT,
    status        TEXT    NOT NULL DEFAULT 'pending',
    progress      REAL    NOT NULL DEFAULT 0,
    duration_s    REAL,
    audio_seconds REAL,
    cost_usd      REAL,
    chars         INTEGER,
    out_dir       TEXT,
    txt_path      TEXT,
    srt_path      TEXT,
    raw_path      TEXT,
    error         TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    start         REAL    NOT NULL,
    end           REAL    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    text          TEXT,
    words_json    TEXT,
    segments_json TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    updated_at    TEXT,
    PRIMARY KEY (task_id, idx)
);

CREATE TABLE IF NOT EXISTS task_summaries (
    task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'disabled',
    content TEXT,
    error TEXT,
    model TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
"""

TERMINAL_STATUSES = frozenset({"done", "failed"})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class TaskRecord:
    id: int
    name: str
    source_path: str
    mode: str
    artifact: str
    status: str
    progress: float = 0.0
    engine: str | None = None
    duration_s: float | None = None
    audio_seconds: float | None = None
    cost_usd: float | None = None
    chars: int | None = None
    out_dir: str | None = None
    txt_path: str | None = None
    srt_path: str | None = None
    raw_path: str | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


@dataclass
class ChunkState:
    task_id: int
    idx: int
    start: float
    end: float
    status: str = "pending"
    text: str = ""
    words: list[Word] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    attempts: int = 0
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status == "done"

    def as_payload(self) -> dict:
        return {
            "idx": self.idx,
            "start": self.start,
            "end": self.end,
            "status": self.status,
            "chars": len(self.text),
            "text": self.text,
            "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in self.segments],
            "attempts": self.attempts,
            "error": self.error,
        }


class Store:
    """SQLite 封装。路径可注入，测试用 tmp_path。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """旧库补列。SQLite 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表加列。"""
        existing_chunks = {row["name"] for row in conn.execute("PRAGMA table_info(chunks)")}
        if "segments_json" not in existing_chunks:
            conn.execute("ALTER TABLE chunks ADD COLUMN segments_json TEXT")

        existing_tasks = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "progress" not in existing_tasks:
            conn.execute("ALTER TABLE tasks ADD COLUMN progress REAL NOT NULL DEFAULT 0")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- 任务 ----------

    def create_task(
        self,
        *,
        name: str,
        source_path: str,
        mode: str,
        artifact: str,
        engine: str | None = None,
        duration_s: float | None = None,
    ) -> int:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (name, source_path, mode, artifact, engine, status,"
                " duration_s, created_at, updated_at)"
                " VALUES (?,?,?,?,?,'running',?,?,?)",
                (name, source_path, mode, artifact, engine, duration_s, now, now),
            )
            return int(cur.lastrowid or 0)

    def update_task(self, task_id: int, **fields: object) -> None:
        allowed = {
            "status",
            "progress",
            "engine",
            "duration_s",
            "audio_seconds",
            "cost_usd",
            "chars",
            "out_dir",
            "txt_path",
            "srt_path",
            "raw_path",
            "error",
        }
        sets = [f"{k}=?" for k in fields if k in allowed]
        if not sets:
            return
        values = [fields[k] for k in fields if k in allowed]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(sets)}, updated_at=? WHERE id=?",
                (*values, _now(), task_id),
            )

    def get_task(self, task_id: int) -> TaskRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._to_task(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_task(r) for r in rows]

    def delete_task(self, task_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM chunks WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def stats(self) -> dict[str, float]:
        """给页面显示的累计量（含费用，便于"只显示不拦截"的预估对照）。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS tasks,"
                " COALESCE(SUM(audio_seconds),0) AS audio_seconds,"
                " COALESCE(SUM(cost_usd),0) AS cost_usd,"
                " COALESCE(SUM(chars),0) AS chars FROM tasks"
            ).fetchone()
        return {k: row[k] for k in row.keys()}

    # ---------- Agent 总结（独立状态，不影响转录成败） ----------

    def get_summary(self, task_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_summaries WHERE task_id=?", (task_id,)
            ).fetchone()
        if not row:
            return {
                "enabled": False,
                "status": "disabled",
                "content": None,
                "error": None,
                "model": None,
            }
        return {
            "enabled": bool(row["enabled"]),
            "status": row["status"],
            "content": json.loads(row["content"]) if row["content"] else None,
            "error": row["error"],
            "model": row["model"],
        }

    def set_summary(self, task_id: int, **fields: object) -> None:
        allowed = {"enabled", "status", "content", "error", "model"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        if fields.get("content") is not None:
            fields["content"] = json.dumps(fields["content"], ensure_ascii=False)
        with self._conn() as conn:
            # 任务被删除后，后台总结不得重新建记录。
            conn.execute(
                "INSERT OR IGNORE INTO task_summaries(task_id) SELECT id FROM tasks WHERE id=?",
                (task_id,),
            )
            conn.execute(
                f"UPDATE task_summaries SET {', '.join(f'{k}=?' for k in fields)} WHERE task_id=?",
                (*fields.values(), task_id),
            )

    def interrupt_summaries(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE task_summaries SET status='failed', error='总结被中断，请重试。' "
                "WHERE status='running'"
            )

    # ---------- 分片 ----------

    def upsert_chunk(
        self,
        task_id: int,
        *,
        idx: int,
        start: float,
        end: float,
        status: str,
        text: str = "",
        words: list[Word] | None = None,
        segments: list[Segment] | None = None,
        attempts: int = 0,
        error: str | None = None,
    ) -> None:
        payload = json.dumps(
            [
                {"text": w.text, "start": w.start, "end": w.end, "probability": w.probability}
                for w in (words or [])
            ],
            ensure_ascii=False,
        )
        seg_payload = json.dumps(
            [
                {"start": s.start, "end": s.end, "text": s.text, "speaker": s.speaker}
                for s in (segments or [])
            ],
            ensure_ascii=False,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chunks (task_id, idx, start, end, status, text, words_json,"
                " segments_json, attempts, error, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(task_id, idx) DO UPDATE SET"
                " status=excluded.status, text=excluded.text, words_json=excluded.words_json,"
                " segments_json=excluded.segments_json,"
                " attempts=excluded.attempts, error=excluded.error, updated_at=excluded.updated_at",
                (
                    task_id,
                    idx,
                    start,
                    end,
                    status,
                    text,
                    payload,
                    seg_payload,
                    attempts,
                    error,
                    _now(),
                ),
            )

    def ensure_chunk(self, task_id: int, *, idx: int, start: float, end: float) -> None:
        """只为缺失的分片建行，绝不覆盖已有状态（续跑时参数可能会变）。"""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chunks (task_id, idx, start, end, status, attempts,"
                " updated_at) VALUES (?,?,?,?,'pending',0,?)",
                (task_id, idx, start, end, _now()),
            )

    def get_chunk(self, task_id: int, idx: int) -> ChunkState | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE task_id=? AND idx=?", (task_id, idx)
            ).fetchone()
        return self._to_chunk(row) if row else None

    def chunks_for(self, task_id: int) -> list[ChunkState]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE task_id=? ORDER BY idx", (task_id,)
            ).fetchall()
        return [self._to_chunk(r) for r in rows]

    def done_chunk_indices(self, task_id: int) -> set[int]:
        """续跑用：这些分片不必重跑（也不必重新花钱）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT idx FROM chunks WHERE task_id=? AND status='done'", (task_id,)
            ).fetchall()
        return {int(r["idx"]) for r in rows}

    # ---------- 行转换 ----------

    @staticmethod
    def _to_task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(**{k: row[k] for k in row.keys()})

    @staticmethod
    def _to_chunk(row: sqlite3.Row) -> ChunkState:
        words: list[Word] = []
        if row["words_json"]:
            try:
                words = [
                    Word(w["text"], w["start"], w["end"], w.get("probability"))
                    for w in json.loads(row["words_json"])
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                words = []
        segments: list[Segment] = []
        seg_raw = row["segments_json"] if "segments_json" in row.keys() else None
        if seg_raw:
            try:
                segments = [
                    Segment(s["start"], s["end"], s["text"], speaker=s.get("speaker"))
                    for s in json.loads(seg_raw)
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                segments = []
        return ChunkState(
            task_id=int(row["task_id"]),
            idx=int(row["idx"]),
            start=float(row["start"]),
            end=float(row["end"]),
            status=row["status"],
            text=row["text"] or "",
            words=words,
            segments=segments,
            attempts=int(row["attempts"] or 0),
            error=row["error"],
        )
