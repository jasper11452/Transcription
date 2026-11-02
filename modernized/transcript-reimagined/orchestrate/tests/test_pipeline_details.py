"""编排细节：模式校验、临时目录、在线/离线工作副本、取消、原始 JSON 与重试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from transcript_reimagined.domain import FatalError, InputError, RecoverableError

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401
from transcript_reimagined.orchestrate import Pipeline, estimate_cost, with_retries
from transcript_reimagined.orchestrate import pipeline as pipeline_mod


@pytest.mark.rule("RULE-063")
def test_invalid_mode_or_artifact_is_rejected_before_any_work(env, tmp_path):  # noqa: F811
    config, store, source, _out = env
    pipeline = make_pipeline(config, store, FakeEngine())
    with pytest.raises(FatalError, match="模式"):
        pipeline.run(source, mode="stream")
    with pytest.raises(FatalError, match="产物"):
        pipeline.run(source, artifact="docx")


def test_auto_language_is_treated_as_auto_detect(env):  # noqa: F811
    """页面「自动」发送的是 "auto"；模型不认识它，编排层必须还原成 None。

    UAT 实测：语言选「自动」时离线任务直接失败（`Unsupported language: auto`）。
    """
    config, store, source, _out = env

    auto_engine = FakeEngine()
    result = make_pipeline(config, store, auto_engine).run(
        source, artifact="txt", language="auto"
    )
    assert result.status == "done"
    assert auto_engine.languages and set(auto_engine.languages) == {None}

    zh_engine = FakeEngine()
    make_pipeline(config, store, zh_engine).run(source, artifact="txt", language="zh")
    assert zh_engine.languages and set(zh_engine.languages) == {"zh"}


def test_missing_input_fails_without_products(env, monkeypatch):  # noqa: F811
    config, store, source, out_dir = env

    def missing(_path):
        raise InputError("文件不存在：meeting.wav")

    monkeypatch.setattr(pipeline_mod.audio_mod, "probe", missing)
    result = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
    assert result.status == "failed"
    assert "文件不存在" in (result.error or "")
    assert not list(out_dir.glob("*.txt"))
    assert not list(out_dir.glob("*.srt"))
    assert not list(out_dir.glob("*.raw.json"))


def test_workdir_is_cleaned_up(env, tmp_path):  # noqa: F811
    config, store, source, _out = env
    root = tmp_path / "work"
    root.mkdir()
    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda _kind, _cfg, artifact=None: FakeEngine(),
        vad_fn=lambda _wav: [(0.0, 6.0)],
        sleep=lambda _s: None,
        workdir_root=root,
    )
    assert pipeline.run(source, artifact="txt").status == "done"
    assert list(root.iterdir()) == [], "临时工作目录必须在 finally 里删掉"


def _recording_pipeline(config, store):
    return Pipeline(
        config,
        store,
        engine_factory=lambda _kind, _cfg, artifact=None: FakeEngine(),
        vad_fn=lambda _wav: [(0.0, 6.0)],
        sleep=lambda _s: None,
    )


def test_offline_mode_cuts_wav(env, monkeypatch):  # noqa: F811
    config, store, source, _out = env
    kinds: list[str] = []

    def cut(_src, dst, _start, _end, *, kind="wav16k"):
        kinds.append(kind)
        Path(dst).write_bytes(b"chunk")
        return Path(dst)

    monkeypatch.setattr(pipeline_mod.audio_mod, "cut", cut)
    assert _recording_pipeline(config, store).run(source, artifact="txt").status == "done"
    assert set(kinds) == {"wav16k"}


def test_online_mode_cuts_mp3(env, monkeypatch):  # noqa: F811
    config, store, source, _out = env
    config.online_concurrency = 1
    kinds: list[str] = []

    def cut(_src, dst, _start, _end, *, kind="wav16k"):
        kinds.append(kind)
        Path(dst).write_bytes(b"chunk")
        return Path(dst)

    monkeypatch.setattr(pipeline_mod.audio_mod, "cut", cut)
    result = _recording_pipeline(config, store).run(source, mode="online", artifact="txt")
    assert result.status == "done"
    assert set(kinds) == {"mp3_64k"}


@pytest.mark.rule("RULE-089")
def test_cancel_between_chunks_keeps_done_chunks_and_writes_nothing(env):  # noqa: F811
    config, store, source, out_dir = env
    holder: dict = {}

    def on_event(progress):
        if progress.stage == "chunk" and progress.current >= 1:
            holder["pipeline"].cancel()

    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda _kind, _cfg, artifact=None: FakeEngine(),
        vad_fn=lambda _wav: [(0.0, 6.0)],
        sleep=lambda _s: None,
        on_event=on_event,
    )
    holder["pipeline"] = pipeline
    result = pipeline.run(source, artifact="txt")
    assert result.status == "failed"
    assert store.done_chunk_indices(result.task_id) == {0}
    assert not list(out_dir.glob("*.txt"))


@pytest.mark.rule("RULE-132")
def test_raw_json_records_glossary_trace(env, tmp_path):  # noqa: F811
    config, store, source, out_dir = env
    config.glossary_path.write_text("第0片 -> 第零片\n", encoding="utf-8")
    result = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
    assert result.status == "done"
    raw = json.loads((out_dir / "meeting.raw.json").read_text(encoding="utf-8"))
    assert "第0片" in raw["merged_text_before_glossary"]
    assert "第零片" in raw["final_text"]
    assert raw["glossary_changes"] == [{"wrong": "第0片", "right": "第零片", "count": 1}]


@pytest.mark.rule("RULE-086")
def test_source_duration_survives_resume(env):  # noqa: F811
    config, store, source, _out = env
    first = make_pipeline(config, store, FakeEngine(fail_indexes={1})).run(
        source, artifact="txt"
    )
    second = make_pipeline(config, store, FakeEngine()).run(
        source, artifact="txt", task_id=first.task_id
    )
    assert second.status == "done"
    assert store.get_task(first.task_id).duration_s == 6.0


@pytest.mark.rule("RULE-026")
def test_estimate_cost_only_prices_what_we_know():
    assert estimate_cost("offline", "txt", 3600) == 0.0
    assert estimate_cost("online", "txt", 3600, online_engine="bcut") == 0.0
    assert estimate_cost("online", "txt", 3600, online_engine="dashscope") is None
    assert estimate_cost("online", "txt", 3600, online_engine="auto") is None
    assert estimate_cost("online", "srt", 3600, online_engine="auto") == pytest.approx(0.1)


@pytest.mark.rule("RULE-059")
def test_with_retries_reraises_the_last_error_after_exhaustion():
    sleeps: list[float] = []

    def always(_attempt: int):
        raise RecoverableError("还不行")

    with pytest.raises(RecoverableError, match="还不行"):
        with_retries(always, attempts=2, backoff=1.0, sleep=sleeps.append)
    assert sleeps == [1.0]
