"""断点续跑：已完成分片不重跑；只有两种特例退回重跑（RULE-086）。"""

from __future__ import annotations

import pytest
from transcript_reimagined.domain import RecoverableError, Word

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401


@pytest.mark.rule("RULE-086")
def test_resume_reuses_completed_chunks(env):  # noqa: F811
    config, store, source, _out = env
    first = make_pipeline(config, store, FakeEngine(fail_indexes={1})).run(
        source, artifact="txt"
    )
    assert first.status == "failed"

    second_engine = FakeEngine()
    second = make_pipeline(config, store, second_engine).run(
        source, artifact="txt", task_id=first.task_id
    )
    assert second.status == "done"
    assert second_engine.calls == [1], "分片 0 已完成，续跑不得再调用引擎"
    assert store.done_chunk_indices(first.task_id) == {0, 1}


@pytest.mark.rule("RULE-086")
def test_empty_cached_text_is_rerun(env):  # noqa: F811
    config, store, source, _out = env
    first = make_pipeline(
        config, store, FakeEngine(fail_indexes={1}, empty_text_indexes={0})
    ).run(source, artifact="txt")
    assert first.status == "failed"

    second_engine = FakeEngine()
    second = make_pipeline(config, store, second_engine).run(
        source, artifact="txt", task_id=first.task_id
    )
    assert second.status == "done"
    assert second_engine.calls == [0, 1], "空文本的已完成分片必须重跑"


@pytest.mark.rule("RULE-086")
def test_missing_timeline_is_rerun_for_srt(env):  # noqa: F811
    config, store, source, _out = env
    # 第一次跑 txt：不取时间轴，所以缓存里没有 words/segments。
    first = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
    assert first.status == "done"
    assert store.done_chunk_indices(first.task_id) == {0, 1}

    second_engine = FakeEngine()
    second = make_pipeline(config, store, second_engine).run(
        source, artifact="srt", task_id=first.task_id
    )
    assert second.status == "done"
    assert second_engine.calls == [0, 1], "srt 需要时间轴，缓存里没有就必须重跑"


@pytest.mark.rule("RULE-086")
def test_words_without_segments_are_rebuilt_locally_without_another_call(env):  # noqa: F811
    config, store, source, _out = env
    first = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
    tid = first.task_id

    # 模拟“上一轮存了 words 但没存 segments”的缓存（旧库/迁移场景）。
    store.upsert_chunk(
        tid,
        idx=0,
        start=0.0,
        end=3.0,
        status="done",
        text="第0片正文。",
        words=[Word("第", 0.0, 0.2), Word("片", 0.2, 0.4)],
        segments=[],
    )
    # 分片 1 仍是 txt 缓存（无 words），srt 任务必须重跑它。
    second_engine = FakeEngine()
    second = make_pipeline(config, store, second_engine).run(
        source, artifact="srt", task_id=tid
    )
    assert second.status == "done"
    assert second_engine.calls == [1], "有 words 的分片应在本地重建段落，不重新付费"
    chunk0 = store.get_chunk(tid, 0)
    assert chunk0 is not None and chunk0.segments, "重建后的段落必须落回缓存"


@pytest.mark.rule("RULE-086")
def test_recoverable_error_is_retried_and_fatal_is_not(env):  # noqa: F811
    config, store, source, _out = env
    engine = FakeEngine(recoverable_once_indexes={0})
    result = make_pipeline(config, store, engine).run(source, artifact="txt")
    assert result.status == "done"
    assert engine.calls.count(0) == 2, "可恢复错误应重试一次"
    assert engine.calls.count(1) == 1

    fatal_engine = FakeEngine(fail_indexes={0})
    fatal = make_pipeline(config, store, fatal_engine).run(source, artifact="txt")
    assert fatal.status == "failed"
    assert fatal_engine.calls.count(0) == 1, "不可恢复错误不得重试"


@pytest.mark.rule("RULE-059")
def test_with_retries_only_retries_recoverable_errors():
    from transcript_reimagined.domain import FatalError

    from transcript_reimagined.orchestrate import with_retries

    sleeps: list[float] = []
    attempts = {"n": 0}

    def flaky(_attempt: int) -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RecoverableError("抖一下")
        return "ok"

    assert with_retries(flaky, attempts=3, backoff=1.0, sleep=sleeps.append) == "ok"
    assert sleeps == [1.0, 2.0]

    fatal_calls = {"n": 0}

    def fatal(_attempt: int) -> str:
        fatal_calls["n"] += 1
        raise FatalError("参数错误")

    with pytest.raises(FatalError):
        with_retries(fatal, attempts=3, backoff=1.0, sleep=sleeps.append)
    assert fatal_calls["n"] == 1
