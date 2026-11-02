"""任务管理：后台线程 + SSE 进度。

并发策略（spec 第 5 节）：**离线串行、在线并行**。
离线串行是硬约束——本地模型独占内存，两个任务同时跑只会互相拖慢；
在线并行是免费的吞吐（分片级并发在 engine/pipeline 里，这里控制任务级）。
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..pipeline import Pipeline, Progress, RunResult
from ..store import Store
from ..summary import SummaryManager

MAX_EVENTS_PER_TASK = 500


@dataclass
class Job:
    task_id: int
    source: str
    mode: str
    artifact: str
    language: str | None = None
    online_engine: str | None = None


class JobManager:
    """把 Pipeline 放进线程池，并把进度事件广播给所有订阅者。"""

    def __init__(
        self,
        config: Config,
        store: Store,
        pipeline_factory: Callable[[Store, Callable[[Progress], None]], Pipeline] | None = None,
    ):
        self.config = config
        self.store = store
        self.summaries = SummaryManager(config, store)
        self._pipeline_factory = pipeline_factory or self._default_pipeline
        self._offline = ThreadPoolExecutor(max_workers=1, thread_name_prefix="offline")
        self._online = ThreadPoolExecutor(max_workers=2, thread_name_prefix="online")
        self._events: dict[int, list[dict]] = {}
        self._subscribers: dict[int, list[queue.Queue]] = {}
        self._running: set[int] = set()
        self._cancelling: set[int] = set()
        self._finished: set[int] = set()
        self._pipelines: dict[int, Pipeline] = {}
        self._lock = threading.Lock()

    def _default_pipeline(self, store: Store, on_event: Callable[[Progress], None]) -> Pipeline:
        return Pipeline(self.config, store, on_event=on_event)

    # ---------- 提交 ----------

    def submit(
        self,
        *,
        source: Path,
        mode: str,
        artifact: str,
        language: str | None = None,
        task_id: int | None = None,
        online_engine: str | None = None,
    ) -> int:
        source = Path(source).expanduser()
        tid = task_id
        if tid is None:
            tid = self.store.create_task(
                name=source.stem, source_path=str(source), mode=mode, artifact=artifact, engine=None
            )
        with self._lock:
            self._running.add(tid)
            self._finished.discard(tid)
            # 每轮 run 一份事件日志。续跑沿用同一个 task_id，若保留上一轮的
            # result/close，新订阅者会先被重放旧 close 并立刻停止跟随——
            # 后端已跑完、页面却永远停在续跑前的读数（2026-09-19 浏览器实测）。
            self._events[tid] = []
        # 每次真正开跑都记一个起点：页面用它显示"已用时"，续跑也不会继承旧时长。
        self.store.update_task(tid, started_at=datetime.now(UTC).isoformat(timespec="seconds"))
        executor = self._offline if mode == "offline" else self._online
        executor.submit(self._run, Job(tid, str(source), mode, artifact, language, online_engine))
        return tid

    def _run(self, job: Job) -> None:
        def on_event(progress: Progress) -> None:
            event = {"type": "progress", **progress.as_dict()}
            if progress.chunk_index is not None and progress.stage in {"chunk", "chunk_failed"}:
                chunk = self.store.get_chunk(job.task_id, progress.chunk_index)
                if chunk:
                    event["chunk"] = chunk.as_payload()
                # 在线分片会乱序完成，不能用分片下标当已完成数量。
                event["current"] = len(self.store.done_chunk_indices(job.task_id))
            if progress.total > 0:
                self.store.update_task(
                    job.task_id, progress=event["current"] / progress.total * 100
                )
            self._publish(job.task_id, event)

        result: RunResult | None = None
        try:
            pipeline = self._pipeline_factory(self.store, on_event)
            with self._lock:
                self._pipelines[job.task_id] = pipeline
            result = pipeline.run(
                job.source,
                mode=job.mode,
                artifact=job.artifact,
                language=job.language,
                task_id=job.task_id,
                online_engine=job.online_engine,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底：任何异常都要变成可见的任务失败
            self.store.update_task(job.task_id, status="failed", error=f"内部错误：{exc}")
            result = RunResult(
                task_id=job.task_id, status="failed", engine="-", error=f"内部错误：{exc}"
            )
        finally:
            with self._lock:
                # 终态可见之前，结果必须已记入历史并进入现有订阅者的队列。
                # 与 submit/stream 共用锁，避免续跑清空日志后又混入旧 result/close。
                if result is not None:
                    self._publish_locked(
                        job.task_id,
                        {"type": "result", **result.as_dict()},
                        {"type": "close"},
                    )
                self._running.discard(job.task_id)
                self._cancelling.discard(job.task_id)
                self._finished.add(job.task_id)
                self._pipelines.pop(job.task_id, None)

        if result is not None and result.status == "done":
            self.summaries.start_if_enabled(job.task_id)

    def cancel(self, task_id: int) -> bool:
        """请求停止正在跑的任务；分片边界生效。返回是否找到了可取消的流水线。

        “已请求停止”和“已经停下”是两回事：请求之后任务还会把当前分片跑完。
        这里把请求记下来，页面才能诚实地说“停止中”，而不是回到“进行中”。
        """
        with self._lock:
            pipeline = self._pipelines.get(task_id)
            if pipeline is None:
                return False
            self._cancelling.add(task_id)
        pipeline.cancel()
        return True

    # ---------- 事件广播 ----------

    def _publish(self, task_id: int, event: dict) -> None:
        with self._lock:
            self._publish_locked(task_id, event)

    def _publish_locked(self, task_id: int, *events: dict) -> None:
        """调用方持锁；订阅队列无容量上限，入队不等待消费者、不做网络 I/O。"""
        history = self._events.setdefault(task_id, [])
        history.extend(events)
        if len(history) > MAX_EVENTS_PER_TASK:
            del history[: len(history) - MAX_EVENTS_PER_TASK]
        for q in self._subscribers.get(task_id, []):
            for event in events:
                q.put_nowait(event)

    def stream(self, task_id: int, *, heartbeat_s: float = 15.0) -> Iterator[str]:
        """SSE 事件流。先补发历史（刷新页面不丢进度），再实时推送。"""
        q: queue.Queue = queue.Queue()
        with self._lock:
            history = list(self._events.get(task_id, []))
            already_done = task_id in self._finished
            self._subscribers.setdefault(task_id, []).append(q)

        try:
            for event in history:
                yield _sse(event)
            if already_done or any(e.get("type") == "close" for e in history):
                yield _sse({"type": "close"})
                return
            while True:
                try:
                    event = q.get(timeout=heartbeat_s)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if event.get("type") == "close":
                    return
        finally:
            with self._lock:
                subs = self._subscribers.get(task_id, [])
                if q in subs:
                    subs.remove(q)

    def is_running(self, task_id: int) -> bool:
        with self._lock:
            return task_id in self._running

    def is_cancelling(self, task_id: int) -> bool:
        with self._lock:
            return task_id in self._cancelling

    def history(self, task_id: int) -> list[dict]:
        with self._lock:
            return list(self._events.get(task_id, []))

    def shutdown(self) -> None:
        self.summaries.shutdown()
        self._offline.shutdown(wait=False, cancel_futures=True)
        self._online.shutdown(wait=False, cancel_futures=True)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
