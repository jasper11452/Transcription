"""Web 测试夹具：临时 dist、独立 state.db、桩 JobManager。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from transcript_reimagined.config import Config  # noqa: E402
from transcript_reimagined.state import Store  # noqa: E402

from transcript_reimagined.web import create_app  # noqa: E402
from web_fakes import Env, FakeJobs  # noqa: E402


def make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(
        "<html><head><title>t</title></head><body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    (dist / "task.html").write_text(
        "<html><head><title>t</title></head><body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    return dist


@pytest.fixture
def env(tmp_path: Path) -> Env:
    config = Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "state.db",
        output_dir=tmp_path / "output",
        glossary_path=tmp_path / "glossary.txt",
    )
    store = Store(config.state_db)
    jobs = FakeJobs(store)
    dist = make_dist(tmp_path)
    app = create_app(
        config,
        store,
        jobs,
        dist_dir=dist,
        allowed_hosts=frozenset({"testserver"}),
        validate_frontend=False,
    )
    return Env(app=app, config=config, store=store, jobs=jobs, dist=dist, tmp_path=tmp_path)


@pytest.fixture
def client(env: Env):
    from fastapi.testclient import TestClient

    with TestClient(env.app) as test_client:
        yield test_client
