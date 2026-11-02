"""FastAPI 依赖：把 app.state 里的三个对象显式注入路由。

不建全局单例、不在路由里直接 import 一个模块级 config —— 每个 router 都能拿
一个独立的 AppContext 构造并测试（这正是旧 `create_app` 闭包缺的接缝）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from transcript_reimagined.config import Config
from transcript_reimagined.orchestrate import JobManager
from transcript_reimagined.state import Store


@dataclass(frozen=True)
class AppContext:
    config: Config
    store: Store
    jobs: JobManager
    dist_dir: Path
    allowed_hosts: frozenset[str]


def get_context(request: Request) -> AppContext:
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is None:  # pragma: no cover - create_app 一定会设置
        raise RuntimeError("应用未初始化 AppContext")
    return ctx
