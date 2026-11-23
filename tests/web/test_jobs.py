"""JobManager：任务生命周期、SSE 补偿发送、事件上限。

用例全部用假的 pipeline（`pipeline_factory`），不起模型、不连网、不读用户音频。
真实转写的验证在 `-m smoke` 的端到端用例里。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from transcript.config import Config
from transcript.models import Segment
from transcript.pipeline import Progress, RunResult
from transcript.store import Store
from transcript.web.jobs import MAX_EVENTS_PER_TASK, JobManager


class FakePipeline:
    """按脚本跑：发若干 progress，然后返回一个结果或抛错。"""

    def __init__(
        self,
        store: Store,
        on_event: Callable[[Progress], None],
        *,
        steps: int = 2,
        fail: Exception | None = None,
        block: threading.Event | None = None,
    ):
        self.store = store
        self.on_event = on_event
        self.steps = steps
        self.fail = fail
        self.block = block
        self.cancelled = False

    def run(self, source, *, mode, artifact, language, task_id, online_engine=None) -> RunResult:
        for i in range(self.steps):
            self.on_event(
                Progress(stage="transcribe", message=f"第 {i} 片", current=i + 1, total=self.steps)
            )
        if self.block is not None:
            self.block.wait(timeout=5)
        if self.fail is not None:
            raise self.fail
        self.store.update_task(task_id, status="done", chars=3)
        return RunResult(task_id=task_id, status="done", engine="offline:fake", chars=3)

    def cancel(self) -> None:
        self.cancelled = True


def collect(stream: Iterator[str], *, limit: int = 50) -> list[dict]:
    """把 SSE 文本流读成事件列表；无 data 行（心跳）跳过。"""
    events: list[dict] = []
    for chunk in stream:
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                if events[-1].get("type") == "close":
                    return events
        if len(events) >= limit:
            break
    return events


@pytest.fixture
def manager(config: Config, store: Store) -> Iterator[JobManager]:
    m = JobManager(config, store)
    try:
        yield m
    finally:
        m.shutdown()


def test_提交建记录并按产物选线程池(manager: JobManager, store: Store, tmp_path: Path) -> None:
    source = tmp_path / "a.m4a"
    source.touch()
    tid = manager.submit(source=source, mode="offline", artifact="srt")
    task = store.get_task(tid)
    assert task is not None
    assert task.name == "a"
    assert task.mode == "offline"


def test_失败也要落库并广播_result_和_close(config: Config, store: Store, tmp_path: Path) -> None:
    """跑挂了必须让页面知道：只发 progress 不发 result 的话，页面会一直转圈。"""
    err = RuntimeError("模型炸了")
    m = JobManager(config, store, pipeline_factory=lambda s, e: FakePipeline(s, e, fail=err))
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="txt")
        m._online.shutdown(wait=False)
        # 等线程结束：_finished 由 _run 的 finally 添加
        for _ in range(200):
            if tid in m._finished:
                break
            threading.Event().wait(0.02)
        events = collect(m.stream(tid))
        assert [e["type"] for e in events][-2:] == ["result", "close"]
        assert events[-2]["status"] == "failed"
        assert "内部错误" in store.get_task(tid).error
    finally:
        m.shutdown()


def test_订阅时先补发历史(config: Config, store: Store, tmp_path: Path) -> None:
    """刷新页面不能丢进度：订阅要先把已发过的事件重放一遍。"""
    gate = threading.Event()
    m = JobManager(
        config, store, pipeline_factory=lambda s, e: FakePipeline(s, e, steps=5, block=gate)
    )
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="txt")
        for _ in range(250):
            if len(m.history(tid)) >= 4:
                break
            threading.Event().wait(0.02)
        gate.set()
        assert len(m.history(tid)) >= 4, "pipeline 还没发完就被放行了"
        events = collect(m.stream(tid), limit=4)
        assert [e["type"] for e in events[:4]] == ["progress"] * 4
        assert events[0]["current"] == 1, "重放要保持原有顺序"
    finally:
        gate.set()
        m.shutdown()


def test_续跑不重放上一轮的_close(config: Config, store: Store, tmp_path: Path) -> None:
    """回归用例：续跑沿用同一 task_id，若保留上一轮的 close，
    新订阅者会立刻停止跟随，页面永远停在旧读数。"""
    m = JobManager(config, store, pipeline_factory=lambda s, e: FakePipeline(s, e, steps=1))
    try:
        source = tmp_path / "a.m4a"
        source.touch()
        task_id = store.create_task(
            name="a", source_path=str(source), mode="offline", artifact="txt"
        )
        m.submit(source=source, mode="offline", artifact="txt", task_id=task_id)
        for _ in range(200):
            if task_id in m._finished:
                break
            threading.Event().wait(0.02)
        assert collect(m.stream(task_id))[-1]["type"] == "close"

        # 第二轮：同一个 task_id
        m.submit(source=source, mode="offline", artifact="txt", task_id=task_id)
        for _ in range(200):
            if m.history(task_id) and m.history(task_id)[0]["type"] == "progress":
                break
            threading.Event().wait(0.02)
        events = collect(m.stream(task_id), limit=3)
        assert events[0]["type"] == "progress", "上一轮的 close 不能出现在新一轮开头"
    finally:
        m.shutdown()


def test_事件日志有上限(config: Config, store: Store, tmp_path: Path) -> None:
    """事件堆积必须有天花板，否则长任务会把内存撑爆。"""
    m = JobManager(config, store, pipeline_factory=lambda s, e: FakePipeline(s, e, steps=1))
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="txt")
        for i in range(MAX_EVENTS_PER_TASK + 50):
            m._publish(tid, {"type": "progress", "stage": "x", "message": str(i)})
        history = m.history(tid)
        assert len(history) == MAX_EVENTS_PER_TASK
        # 保留的是最近的：最老那条已经被丢掉
        assert history[0]["message"] != "0"
    finally:
        m.shutdown()


def test_取消先记请求再等分片结束(config: Config, store: Store, tmp_path: Path) -> None:
    """“已请求停止”和“已经停下”是两个状态，页面靠 is_cancelling 说“停止中”。"""
    gate = threading.Event()
    made: list[FakePipeline] = []

    def factory(s: Store, e) -> FakePipeline:
        p = FakePipeline(s, e, block=gate)
        made.append(p)
        return p

    m = JobManager(config, store, pipeline_factory=factory)
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="txt")
        for _ in range(200):
            if made:
                break
            threading.Event().wait(0.02)
        assert m.cancel(tid) is True
        assert m.is_cancelling(tid) is True
        assert m.is_running(tid) is True, "请求取消不等于已经停下来了"
        assert made[0].cancelled is True
        gate.set()
        for _ in range(200):
            if tid in m._finished:
                break
            threading.Event().wait(0.02)
        assert m.is_running(tid) is False
        assert m.is_cancelling(tid) is False
    finally:
        m.shutdown()


def test_取消与完成交错时不残留停止中(
    config: Config, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = threading.Event(), threading.Event()

    class FinishingPipeline(FakePipeline):
        def run(self, *args, **kwargs):
            started.set()
            return super().run(*args, **kwargs)

    m = JobManager(
        config, store, pipeline_factory=lambda s, e: FinishingPipeline(s, e, block=release)
    )
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="txt")
        assert started.wait(timeout=3)
        # 同一串行池的尾部哨兵：完成后，流水线的终态清理和广播都已结束。
        finished = m._offline.submit(lambda: None)
        original_lock = m._lock
        caller = threading.current_thread()

        class FinishAtUnlock:
            armed = True

            def __enter__(self):
                original_lock.acquire()

            def __exit__(self, *exc):
                original_lock.release()
                if self.armed and threading.current_thread() is caller:
                    self.armed = False
                    # 强制任务在 cancel 的首次解锁后结束，避免概率性 sleep 测试。
                    release.set()
                    finished.result(timeout=3)

        monkeypatch.setattr(m, "_lock", FinishAtUnlock())
        assert m.cancel(tid) is True
        assert m.is_running(tid) is False
        assert m.is_cancelling(tid) is False, "终态不能被稍晚写入的取消标记覆盖"
        assert [e["type"] for e in m.history(tid)][-2:] == ["result", "close"]
    finally:
        release.set()
        m.shutdown()


@pytest.mark.parametrize("resume", [False, True], ids=["subscribe", "resume"])
@pytest.mark.parametrize("mode", ["offline", "online"])
@pytest.mark.parametrize("fail", [False, True], ids=["done", "failed"])
def test_终态可见时结果已广播且不会污染续跑(
    config: Config,
    store: Store,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    resume: bool,
    fail: bool,
) -> None:
    gates = [threading.Event(), threading.Event()]
    started = [threading.Event(), threading.Event()]
    terminal, release_terminal = threading.Event(), threading.Event()
    made: list[FakePipeline] = []

    def factory(s: Store, e) -> FakePipeline:
        index = len(made)

        class GatedPipeline(FakePipeline):
            def run(self, *args, **kwargs):
                started[index].set()
                return super().run(*args, **kwargs)

        p = GatedPipeline(
            s, e, steps=0, block=gates[index], fail=RuntimeError("模拟失败") if fail else None
        )
        made.append(p)
        return p

    m = JobManager(config, store, pipeline_factory=factory)
    source = tmp_path / "a.m4a"
    live = None
    try:
        tid = m.submit(source=source, mode=mode, artifact="txt")
        assert started[0].wait(timeout=3)
        live = m.stream(tid, heartbeat_s=0.01)
        assert next(live) == ": keep-alive\n\n"  # 注册一个结束前已连接的订阅者。
        original_lock = m._lock

        class PauseAfterTerminalUnlock:
            def __enter__(self):
                original_lock.acquire()

            def __exit__(self, *exc):
                pause = tid in m._finished and not terminal.is_set()
                if pause:
                    terminal.set()
                original_lock.release()
                if pause:
                    assert release_terminal.wait(timeout=3)

        monkeypatch.setattr(m, "_lock", PauseAfterTerminalUnlock())
        gates[0].set()
        assert terminal.wait(timeout=3)
        assert not m.is_running(tid)
        if resume:
            m.submit(source=source, mode=mode, artifact="txt", task_id=tid)
            release_terminal.set()
            assert started[1].wait(timeout=3)
            # 在线有两个 worker，等第一轮彻底返回后再检查新一轮日志。
            if mode == "online":
                m._online.submit(lambda: None).result(timeout=3)
            assert m.is_running(tid)
            assert m.history(tid) == [], "上一轮 result/close 污染了正在运行的新一轮"
        else:
            events = collect(m.stream(tid))
            assert [e["type"] for e in events] == ["result", "close"]
            assert events[0]["status"] == ("failed" if fail else "done")
        events = collect(live)
        assert [e["type"] for e in events] == ["result", "close"]
        assert events[0]["status"] == ("failed" if fail else "done")
    finally:
        release_terminal.set()
        for gate in gates:
            gate.set()
        if live is not None:
            live.close()
        m.shutdown()


def test_取消没在跑的任务返回_false(manager: JobManager) -> None:
    assert manager.cancel(12345) is False


class ChunkPipeline:
    """先落一条已完成的分片，再发 chunk 事件：验证 SSE 事件带上字幕负载。"""

    def __init__(self, store: Store, on_event: Callable[[Progress], None]):
        self.store = store
        self.on_event = on_event

    def run(self, source, *, mode, artifact, language, task_id, online_engine=None) -> RunResult:
        self.store.upsert_chunk(
            task_id,
            idx=0,
            start=0.0,
            end=2.5,
            status="done",
            text="你好 世界",
            segments=[Segment(start=0.0, end=2.5, text="你好 世界")],
        )
        self.on_event(
            Progress(stage="chunk", message="分片 1 完成", current=0, total=1, chunk_index=0)
        )
        self.store.update_task(task_id, status="done", chars=4)
        return RunResult(task_id=task_id, status="done", engine="offline:fake", chars=4)

    def cancel(self) -> None:
        pass


def test_chunk_事件携带字幕负载且current按已完成统计(
    config: Config, store: Store, tmp_path: Path
) -> None:
    """详情页的实时字幕来自 SSE 事件里的 chunk 负载：没有它页面只能看到进度条。"""
    m = JobManager(config, store, pipeline_factory=lambda s, e: ChunkPipeline(s, e))
    try:
        tid = m.submit(source=tmp_path / "a.m4a", mode="offline", artifact="srt")
        for _ in range(200):
            if tid in m._finished:
                break
            threading.Event().wait(0.02)
        events = collect(m.stream(tid))
        chunk_events = [e for e in events if e.get("stage") == "chunk"]
        assert chunk_events, events
        payload = chunk_events[0]["chunk"]
        assert payload["idx"] == 0
        assert payload["status"] == "done"
        assert payload["text"] == "你好 世界"
        assert payload["segments"][0]["text"] == "你好 世界"
        assert chunk_events[0]["current"] == 1
    finally:
        m.shutdown()
