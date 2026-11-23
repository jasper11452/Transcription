"""Web 测试的桩：JobManager 与 SummaryManager 的鸭子类型替身。"""

from __future__ import annotations

from types import SimpleNamespace


class FakeSummaries:
    def __init__(self) -> None:
        self.enabled: list[int] = []
        self.state = {
            "enabled": False,
            "status": "disabled",
            "content": None,
            "error": None,
            "model": "test/model",
            "available": True,
            "partial": {"content": "", "reasoning": ""},
        }

    def payload(self, _task_id: int) -> dict:
        return dict(self.state)

    def enable(self, task_id: int) -> dict:
        self.enabled.append(task_id)
        self.state = {**self.state, "enabled": True, "status": "waiting"}
        return dict(self.state)


class FakeJobs:
    def __init__(self, store) -> None:
        self.store = store
        self.running: set[int] = set()
        self.cancelling: set[int] = set()
        self.submitted: list[dict] = []
        self.cancelled: list[int] = []
        self.summaries = FakeSummaries()

    def submit(self, **kwargs) -> int:
        self.submitted.append(kwargs)
        return int(kwargs["task_id"])

    def is_running(self, task_id: int) -> bool:
        return task_id in self.running

    def is_cancelling(self, task_id: int) -> bool:
        return task_id in self.cancelling

    def live_task_ids(self) -> set[int]:
        return set(self.running)

    def cancel(self, task_id: int) -> bool:
        if task_id not in self.running:
            return False
        self.cancelled.append(task_id)
        self.cancelling.add(task_id)
        return True

    def stream(self, _task_id: int, **_kwargs):
        yield 'data: {"type": "close"}\n\n'


class Env(SimpleNamespace):
    pass
