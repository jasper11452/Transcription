"""调度层：事件重放、取消语义、存活集合与总结触发（RULE-029 / RULE-090 / RULE-081）。"""

from __future__ import annotations

import threading
import time

import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.state import Store

from transcript_reimagined.orchestrate import JobManager, Progress, RunResult


class FakePipeline:
    def __init__(self, store, on_event, *, gate: threading.Event | None = None):
        self.store = store
        self.on_event = on_event
        self.gate = gate or threading.Event()
        self.started = threading.Event()
        self.cancelled = False

    def run(self, source, *, task_id, **_kwargs):
        self.on_event(Progress("chunk", "分片完成", current=1, total=1, chunk_index=0))
        self.started.set()
        self.gate.wait(timeout=5)
        return RunResult(task_id=task_id, status="done", engine="fake")

    def cancel(self):
        self.cancelled = True
        self.gate.set()


class FakeSummaries:
    def __init__(self):
        self.started: list[int] = []
        self.shutdown_called = False

    def start_if_enabled(self, task_id: int):
        self.started.append(task_id)

    def shutdown(self):
        self.shutdown_called = True


class FailPipeline(FakePipeline):
    def run(self, source, *, task_id, **_kwargs):
        self.on_event(Progress("failed", "boom", current=0, total=1))
        return RunResult(task_id=task_id, status="failed", engine="fake", error="boom")


@pytest.fixture
def manager(tmp_path):
    store = Store(tmp_path / "state.db")
    summaries = FakeSummaries()
    gate = threading.Event()
    pipeline = FakePipeline(store, lambda _p: None, gate=gate)
    # on_event 由 JobManager 注入；这里只保留 gate 与记录能力。
    def factory(store, on_event):
        pipeline.store = store
        pipeline.on_event = on_event
        return pipeline

    mgr = JobManager(
        Config(config_path=tmp_path / "config.env"),
        store,
        pipeline_factory=factory,
        summaries=summaries,
    )
    yield mgr, store, pipeline, gate, summaries
    mgr.shutdown()


def _source(tmp_path):
    path = tmp_path / "meeting.wav"
    path.write_bytes(b"x")
    return path


def _wait_idle(manager: JobManager, task_id: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not manager.is_running(task_id):
            return
        time.sleep(0.01)
    raise AssertionError("任务没有在超时内结束")


@pytest.mark.rule("RULE-090")
def test_stream_replays_history_then_close(tmp_path, manager):  # noqa: F811
    mgr, store, pipeline, gate, _summaries = manager
    tid = mgr.submit(source=_source(tmp_path), mode="offline", artifact="txt")
    assert pipeline.started.wait(timeout=5)
    gate.set()
    _wait_idle(mgr, tid)

    chunks = list(mgr.stream(tid))
    events = [line for line in chunks if line.startswith("data: ")]
    assert any('"type": "progress"' in line for line in events)
    assert any('"type": "result"' in line for line in events)
    assert any('"type": "close"' in line for line in events)
    assert chunks[-1] == 'data: {"type": "close"}\n\n'


@pytest.mark.rule("RULE-081")
def test_live_task_ids_tracks_running_jobs(tmp_path, manager):  # noqa: F811
    mgr, _store, pipeline, gate, _summaries = manager
    tid = mgr.submit(source=_source(tmp_path), mode="offline", artifact="txt")
    assert pipeline.started.wait(timeout=5)
    assert mgr.live_task_ids() == {tid}
    gate.set()
    _wait_idle(mgr, tid)
    assert mgr.live_task_ids() == set()


@pytest.mark.rule("RULE-089")
def test_cancel_sets_the_cancelling_flag_until_the_job_stops(tmp_path, manager):  # noqa: F811
    mgr, _store, pipeline, gate, _summaries = manager
    tid = mgr.submit(source=_source(tmp_path), mode="offline", artifact="txt")
    assert pipeline.started.wait(timeout=5)
    assert mgr.cancel(tid) is True
    assert pipeline.cancelled is True
    assert mgr.is_cancelling(tid) is True
    gate.set()
    _wait_idle(mgr, tid)
    assert mgr.is_cancelling(tid) is False


def test_cancel_unknown_task_returns_false(manager):  # noqa: F811
    mgr, *_ = manager
    assert mgr.cancel(9999) is False


def test_summary_is_triggered_only_after_a_done_task(tmp_path, manager):  # noqa: F811
    mgr, _store, _pipeline, gate, summaries = manager
    tid = mgr.submit(source=_source(tmp_path), mode="offline", artifact="txt")
    gate.set()
    _wait_idle(mgr, tid)
    assert summaries.started == [tid]


def test_history_is_capped_at_500_events(tmp_path, manager):  # noqa: F811
    mgr, store, _pipeline, _gate, _summaries = manager
    tid = store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    for i in range(600):
        mgr._publish(tid, {"type": "progress", "i": i})  # noqa: SLF001
    assert len(mgr.history(tid)) == 500
    assert mgr.history(tid)[0]["i"] == 100


def test_shutdown_stops_summaries(manager):  # noqa: F811
    mgr, _store, _pipeline, _gate, summaries = manager
    mgr.shutdown()
    assert summaries.shutdown_called is True


def test_task_failure_is_logged_with_task_id_and_code(tmp_path):
    import logging

    from transcript_reimagined.config import Config
    from transcript_reimagined.state import Store

    from transcript_reimagined.orchestrate import JobManager

    store = Store(tmp_path / "state.db")
    mgr = JobManager(
        Config(config_path=tmp_path / "config.env"),
        store,
        pipeline_factory=lambda s, on_event: FailPipeline(s, on_event),
        summaries=FakeSummaries(),
    )
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("transcript")
    handler = Capture()
    logger.addHandler(handler)
    try:
        tid = mgr.submit(source=_source(tmp_path), mode="offline", artifact="txt")
        _wait_idle(mgr, tid)
    finally:
        logger.removeHandler(handler)
        mgr.shutdown()

    failure = next(r for r in records if getattr(r, "code", None) == "task_failed")
    assert str(failure.task_id) == str(tid)
    assert "boom" in failure.getMessage()
