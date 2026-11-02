"""P0-2：任一分片失败 → 任务 failed、`.txt`/`.srt` 都不写、已完成分片留在库里。

判据用 `AI_NATIVE_SPEC.md` §5.4 的修正值：6 分片任务的失败场景写作
「分片 0-2 与 4-5 成功、分片 3 失败」；这里用 2 分片的最小等价场景。
"""

from __future__ import annotations

import pytest

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401 - 夹具由 pytest 注入
from transcript_reimagined.orchestrate import RunResult


@pytest.mark.rule("RULE-072")
def test_failed_chunk_leaves_no_partial_products(env):  # noqa: F811
    config, store, source, out_dir = env
    engine = FakeEngine(fail_indexes={1})
    result = make_pipeline(config, store, engine).run(
        source, mode="offline", artifact="txt"
    )

    assert isinstance(result, RunResult)
    assert result.status == "failed"
    assert not list(out_dir.glob("*.txt"))
    assert not list(out_dir.glob("*.srt"))
    assert not list(out_dir.glob("*.raw.json"))
    assert store.get_task(result.task_id).status == "failed"
    assert store.done_chunk_indices(result.task_id) == {0}
    assert store.get_chunk(result.task_id, 1).status == "failed"
    assert "失败" in (store.get_task(result.task_id).error or "")


@pytest.mark.rule("RULE-072")
def test_successful_chunks_are_checkpointed_before_the_failure(env):  # noqa: F811
    config, store, source, _out = env
    engine = FakeEngine(fail_indexes={1})
    result = make_pipeline(config, store, engine).run(source, artifact="txt")
    chunk = store.get_chunk(result.task_id, 0)
    assert chunk is not None
    assert chunk.status == "done"
    assert chunk.text  # 已完成分片的正文必须留下，续跑不再花钱


@pytest.mark.rule("RULE-072")
def test_six_chunk_failure_scenario_from_the_corrected_example(long_env):  # noqa: F811
    """修正后的判据：分片 0-2 与 4-5 成功、分片 3 失败。"""
    config, store, source, out_dir = long_env
    engine = FakeEngine(fail_indexes={3})
    result = make_pipeline(config, store, engine, span_end=29.4).run(
        source, artifact="txt"
    )
    assert result.status == "failed"
    assert store.done_chunk_indices(result.task_id) == {0, 1, 2, 4, 5}
    assert store.get_chunk(result.task_id, 3).status == "failed"
    assert not list(out_dir.glob("*.txt"))
    assert not list(out_dir.glob("*.srt"))


@pytest.mark.rule("RULE-072")
def test_all_chunks_succeed_means_done(env):  # noqa: F811
    config, store, source, _out = env
    result = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
    assert result.status == "done"
    assert store.get_task(result.task_id).status == "done"
    assert len(store.done_chunk_indices(result.task_id)) == 2
