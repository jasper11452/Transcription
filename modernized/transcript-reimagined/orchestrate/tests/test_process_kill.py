"""真实的进程级断点续跑：子进程在分片 0 落库后被 `os._exit(9)` 杀死。

这不是「新建一个 Pipeline 实例」的模拟 —— 子进程真的死了，SQLite 里只留下
已经提交的分片 0；父进程重新打开同一个 `state.db`，续跑时不得重跑分片 0。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from conftest_support.paths import MEMBER_SRC, ROOT

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401

SCRIPT = r'''
import os
import sys
from pathlib import Path

from transcript_reimagined.config import Config
from transcript_reimagined.domain import AudioInfo, TranscriptResult, Word
from transcript_reimagined.orchestrate import Pipeline
from transcript_reimagined.state import Store
import transcript_reimagined.orchestrate.pipeline as p

db, source, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
info = AudioInfo(source, 6.0, 1, "pcm_s16le", 16000, 1, True)

def probe(_path):
    return info

def write(dst, data):
    Path(dst).write_bytes(data)
    return Path(dst)

p.audio_mod.probe = probe
p.audio_mod.to_wav16k = lambda _s, d: write(d, b"wav")
p.audio_mod.verify = lambda _p, _k: info
p.audio_mod.cut = lambda _s, d, _a, _b, **_k: write(d, b"chunk")

class Engine:
    name = "fake:kill"
    max_chunk_s = None
    has_timestamps = True

    def transcribe(self, path, **_kwargs):
        idx = int(Path(path).stem.rsplit("_", 1)[-1])
        return TranscriptResult(
            text=f"第{idx}片正文。",
            words=[Word("第", 0.0, 0.1)],
            engine=self.name,
            has_timestamps=True,
        )

def on_event(progress):
    if progress.stage == "chunk" and progress.current >= 1:
        # 分片 0 已经 upsert 并提交；模拟 kill -9（不给 finally 清理的机会）。
        os._exit(9)

config = Config(
    state_db=db,
    glossary_path=out / "glossary.txt",
    output_dir=out / "fallback",
    chunk_min_s=3.0,
    chunk_max_s=5.0,
    chunk_overlap_s=0.1,
    max_attempts=1,
    backoff_base=0.0,
)
store = Store(db)
Pipeline(
    config,
    store,
    engine_factory=lambda *_a, **_k: Engine(),
    vad_fn=lambda _wav: [(0.0, 6.0)],
    sleep=lambda _s: None,
    on_event=on_event,
).run(source, artifact="txt")
os._exit(0)
'''


@pytest.mark.rule("RULE-086")
def test_completed_chunk_survives_a_real_process_kill(env, tmp_path):  # noqa: F811
    config, store, source, _out = env
    env_vars = dict(os.environ)
    env_vars["PYTHONPATH"] = os.pathsep.join(str(path) for path in MEMBER_SRC)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            SCRIPT,
            str(config.state_db),
            str(source),
            str(tmp_path),
        ],
        cwd=ROOT,
        env=env_vars,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 9, proc.stderr[-1000:]

    # 子进程死了：分片 0 已完成并落库，任务仍是 running（没有终态更新）。
    assert store.done_chunk_indices(1) == {0}
    assert store.get_task(1).status == "running"

    # 父进程重启：只补分片 1，不再调用分片 0。
    engine = FakeEngine()
    result = make_pipeline(config, store, engine).run(
        source, artifact="txt", task_id=1
    )
    assert result.status == "done"
    assert engine.calls == [1]
    assert store.done_chunk_indices(1) == {0, 1}
