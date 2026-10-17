"""Web 层夹具：不启动真实线程池，也不碰用户 state.db。

`create_app` 会调 `validate_dist()`，所以这组用例要求先 `npm run build`——
这正是想要的效果：产物不全时接口测试就该红。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from transcript.config import Config
from transcript.store import Store
from transcript.web.app import create_app
from transcript.web.jobs import JobManager


@pytest.fixture
def client(config: Config, store: Store) -> Iterator[TestClient]:
    """接口客户端。JobManager 在夹具结束后收掉线程池，避免用例互相拖。"""
    manager = JobManager(config, store)
    app = create_app(config, store, jobs=manager)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        manager.shutdown()
