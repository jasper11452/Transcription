"""产物选择：`artifact=txt` 只写 `.txt`，`artifact=srt` 才写 `.srt`（Q9 / RULE-061）。"""

from __future__ import annotations

import pytest

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401


@pytest.mark.rule("RULE-061")
def test_txt_artifact_writes_only_txt_and_raw(env):  # noqa: F811
    config, store, source, out_dir = env
    result = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")

    assert result.status == "done"
    assert (out_dir / "meeting.txt").is_file()
    assert not (out_dir / "meeting.srt").exists(), "Q9：artifact=txt 不得写 .srt"
    assert (out_dir / "meeting.raw.json").is_file()
    assert result.srt_path is None
    assert store.get_task(result.task_id).srt_path is None


@pytest.mark.rule("RULE-061")
def test_srt_artifact_writes_both(env):  # noqa: F811
    config, store, source, out_dir = env
    result = make_pipeline(config, store, FakeEngine()).run(source, artifact="srt")

    assert result.status == "done"
    assert (out_dir / "meeting.txt").is_file()
    assert (out_dir / "meeting.srt").is_file()
    assert result.srt_path is not None
    assert "00:00" in (out_dir / "meeting.srt").read_text(encoding="utf-8")


@pytest.mark.rule("RULE-061")
def test_srt_task_on_an_engine_without_timestamps_fails_without_products(env):  # noqa: F811
    config, store, source, out_dir = env
    engine = FakeEngine(has_timestamps=False)
    result = make_pipeline(config, store, engine).run(source, artifact="srt")

    assert result.status == "failed"
    assert "时间戳" in (result.error or "")
    assert not list(out_dir.glob("*.txt"))
    assert not list(out_dir.glob("*.srt"))
    assert not list(out_dir.glob("*.raw.json"))
    assert store.done_chunk_indices(result.task_id) == set(), "失败时不得留下“已完成”的假象"
