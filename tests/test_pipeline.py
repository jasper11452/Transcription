"""Pipeline 集成测试。

用假引擎/假 VAD 跑真实文件与真实 ffmpeg，验证的是**编排正确性**：
重试边界、增量落盘、续跑不重跑、失败不写产物、词表替换、产物落点。
真模型的正确性由 tests/test_smoke.py（-m smoke）负责。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from transcript.config import Config
from transcript.errors import FatalError, RecoverableError
from transcript.models import Segment, TranscriptResult
from transcript.pipeline import Pipeline, estimate_cost, with_retries
from transcript.store import Store

DATA = Path(__file__).parent / "data"


def make_wav(tmp_path: Path, seconds: float = 5.0) -> Path:
    """造一个真实 wav（用 ffmpeg 生成静音+正弦，避免依赖 say）。"""
    out = tmp_path / "input.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
    )
    return out


def make_config(tmp_path: Path, **kwargs) -> Config:
    cfg = Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "state.db",
        output_dir=tmp_path / "output",
        glossary_path=tmp_path / "glossary.txt",
    )
    for key, value in kwargs.items():
        setattr(cfg, key, value)
    return cfg


class FakeEngine:
    """按被调次数给出确定性结果，并能被指定"前 N 次失败"。"""

    has_timestamps = True

    def __init__(
        self,
        *,
        fail_times: int = 0,
        recoverable: bool = True,
        timestamps: bool = True,
        name: str = "fake",
        text_prefix: str = "第",
        with_segments: bool = True,
    ):
        self.name = name
        self.calls: list[Path] = []
        self._fail_times = fail_times
        self._recoverable = recoverable
        self.has_timestamps = timestamps
        self._text_prefix = text_prefix
        self._with_segments = with_segments

    def transcribe(
        self, audio_path: Path, *, language=None, hotwords=None, want_timestamps: bool = False
    ) -> TranscriptResult:
        self.calls.append(Path(audio_path))
        if len(self.calls) <= self._fail_times:
            message = f"第 {len(self.calls)} 次故意失败"
            raise RecoverableError(message) if self._recoverable else FatalError(message)
        idx = len(self.calls)
        text = f"{self._text_prefix}{idx}段内容{self._text_prefix}二次确认。"
        segments = (
            [Segment(0.0, 1.0, text), Segment(1.0, 2.0, "第二句。")] if self._with_segments else []
        )
        return TranscriptResult(
            text=text,
            segments=segments,
            engine=self.name,
            audio_seconds=2.0,
            cost_usd=0.001,
            has_timestamps=bool(segments),
        )


def run_pipeline(
    tmp_path: Path,
    *,
    engine: FakeEngine,
    source: Path | None = None,
    artifact: str = "txt",
    mode: str = "offline",
    config: Config | None = None,
    events: list | None = None,
    task_id: int | None = None,
    spans: list[tuple[float, float]] | None = None,
    **cfg_kwargs,
):
    config = config or make_config(tmp_path, **cfg_kwargs)
    store = Store(config.state_db)
    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda kind, cfg, artifact: engine,
        vad_fn=lambda path: spans if spans is not None else [(0.0, 5.0)],
        sleep=lambda seconds: None,
        on_event=(events.append if events is not None else None),
    )
    src = source or make_wav(tmp_path)
    result = pipeline.run(src, mode=mode, artifact=artifact, task_id=task_id)
    return result, store, config, src


# ---------- 基本流程 ----------


def test_offline_txt_end_to_end(tmp_path: Path):
    engine = FakeEngine()
    result, store, config, src = run_pipeline(tmp_path, engine=engine)

    assert result.status == "done"
    assert result.txt_path is not None and result.txt_path.exists()
    assert result.txt_path.parent == src.parent
    assert result.chars > 0
    assert engine.calls, "必须真的调用引擎"

    task = store.get_task(result.task_id)
    assert task is not None and task.status == "done"
    assert task.txt_path == str(result.txt_path)
    assert task.chars == result.chars


def test_srt_run_also_writes_txt_for_free(tmp_path: Path):
    engine = FakeEngine()
    result, _, _, _ = run_pipeline(tmp_path, engine=engine, artifact="srt")

    assert result.srt_path is not None and result.srt_path.exists()
    assert result.txt_path is not None and result.txt_path.exists()
    srt = result.srt_path.read_text(encoding="utf-8")
    assert "-->" in srt
    assert srt.strip().splitlines()[0] == "1"


def test_txt_run_does_not_emit_srt(tmp_path: Path):
    """txt 任务不该产出半成品 srt（没有时间戳就没资格给 srt）。"""
    result, _, _, src = run_pipeline(
        tmp_path, engine=FakeEngine(timestamps=False, with_segments=False), artifact="txt"
    )
    assert result.status == "done"
    assert result.srt_path is None
    assert not (src.parent / f"{src.stem}.srt").exists()


def test_srt_requested_but_engine_has_no_timestamps_fails_clearly(tmp_path: Path):
    result, store, _, _ = run_pipeline(
        tmp_path, engine=FakeEngine(timestamps=False, with_segments=False), artifact="srt"
    )
    assert result.status == "failed"
    assert "时间戳" in (result.error or "")
    task = store.get_task(result.task_id)
    assert task is not None and task.status == "failed"


def test_raw_json_records_chunks_and_glossary(tmp_path: Path):
    glossary = tmp_path / "glossary.txt"
    glossary.write_text("第1段 -> 第一段\n", encoding="utf-8")
    engine = FakeEngine(text_prefix="第")
    result, _, _, _ = run_pipeline(tmp_path, engine=engine)

    assert result.raw_path is not None
    raw = json.loads(result.raw_path.read_text(encoding="utf-8"))
    assert raw["chunks"] and raw["chunks"][0]["status"] == "done"
    assert "merged_text_before_glossary" in raw
    assert raw["final_text"] != raw["merged_text_before_glossary"]
    assert raw["glossary_changes"][0]["right"] == "第一段"
    # 原始转写保持不动，替换只作用于产物
    assert "第1段" in raw["merged_text_before_glossary"]
    assert "第1段" not in raw["final_text"]
    assert "词表替换" in result.txt_path.read_text(encoding="utf-8")


def test_audio_never_modified(tmp_path: Path):
    src = make_wav(tmp_path)
    before = src.read_bytes()
    run_pipeline(tmp_path, engine=FakeEngine(), source=src)
    assert src.read_bytes() == before


def test_workdir_is_cleaned_up(tmp_path: Path):
    """16k wav 是工作副本，任务结束必须清掉（大文件会撑爆磁盘）。"""
    before = {p for p in Path("/tmp").glob("transcript-*")}
    run_pipeline(tmp_path, engine=FakeEngine())
    after = {p for p in Path("/tmp").glob("transcript-*")}
    assert after - before == set(), f"工作目录没清掉：{after - before}"


# ---------- 切片与并发 ----------


def test_multiple_chunks_are_transcribed_in_order(tmp_path: Path):
    spans = [(0.0, 40.0), (41.0, 100.0), (101.0, 150.0)]
    engine = FakeEngine()
    src = make_wav(tmp_path, seconds=150.0)
    result, store, _, _ = run_pipeline(
        tmp_path, engine=engine, source=src, spans=spans, artifact="srt"
    )

    assert result.status == "done"
    assert len(engine.calls) >= 2, "长音频必须切片调用"
    chunks = store.chunks_for(result.task_id)
    assert len(chunks) >= 2
    assert [c.idx for c in chunks] == sorted(c.idx for c in chunks)
    texts = [c.text for c in chunks]
    assert all(t for t in texts), "每一片都必须有文本"


def test_online_mode_uses_mp3_chunks_and_parallelism(tmp_path: Path):
    spans = [(0.0, 40.0), (41.0, 80.0), (81.0, 120.0)]
    engine = FakeEngine()
    src = make_wav(tmp_path, seconds=125.0)
    result, _, _, _ = run_pipeline(
        tmp_path,
        engine=engine,
        source=src,
        mode="online",
        spans=spans,
        artifact="srt",
        online_concurrency=3,
    )
    assert result.status == "done"
    assert result.cost_usd and result.cost_usd > 0
    # 在线分片传进去的是 mp3 工作副本（m4a 会被上游拒）
    assert all(call.suffix == ".mp3" for call in engine.calls)


def test_offline_mode_uses_wav_chunks(tmp_path: Path):
    spans = [(0.0, 40.0), (41.0, 80.0)]
    engine = FakeEngine()
    src = make_wav(tmp_path, seconds=85.0)
    run_pipeline(tmp_path, engine=engine, source=src, mode="offline", spans=spans, artifact="srt")
    assert all(call.suffix == ".wav" for call in engine.calls)


# ---------- 重试 / 失败 / 续跑 ----------


def test_recoverable_failure_is_retried_then_succeeds(tmp_path: Path):
    engine = FakeEngine(fail_times=2)
    events: list = []
    result, _, _, _ = run_pipeline(tmp_path, engine=engine, events=events)
    assert result.status == "done"
    assert len(engine.calls) == 3
    assert any(e.stage == "retry" for e in events)


def test_fatal_failure_is_not_retried(tmp_path: Path):
    engine = FakeEngine(fail_times=99, recoverable=False)
    result, store, _, _ = run_pipeline(tmp_path, engine=engine)
    assert result.status == "failed"
    assert len(engine.calls) == 1, "参数/格式类错误重试只是把同一笔失败重复三遍"


def test_exhausted_retries_mark_task_failed_and_write_no_output(tmp_path: Path):
    engine = FakeEngine(fail_times=99, recoverable=True)
    result, store, _, src = run_pipeline(tmp_path, engine=engine, **{"max_attempts": 3})
    assert result.status == "failed"
    assert len(engine.calls) == 3
    assert result.txt_path is None
    assert not (src.parent / f"{src.stem}.txt").exists(), "失败时不得留下看似完整的产物"
    chunk = store.chunks_for(result.task_id)[0]
    assert chunk.status == "failed"
    assert chunk.error


def test_resume_skips_done_chunks_and_does_not_repay(tmp_path: Path):
    """续跑的关键不变式：已完成分片不重跑、不重新付费。"""
    spans = [(0.0, 40.0), (41.0, 80.0), (81.0, 120.0)]
    src = make_wav(tmp_path, seconds=125.0)
    config = make_config(tmp_path)

    # 第一次：第 1 片成功，第 2 片之后持续失败 → 任务失败但第一片已落库
    class FirstRunEngine(FakeEngine):
        def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False):
            self.calls.append(Path(audio_path))
            if len(self.calls) >= 2:
                raise RecoverableError("上游 503")
            return TranscriptResult(
                text="第一片内容。",
                engine=self.name,
                audio_seconds=40.0,
                segments=[Segment(0.0, 40.0, "第一片内容。")],
                has_timestamps=True,
            )

    first = FirstRunEngine()
    first_run, store, config, _ = run_pipeline(
        tmp_path,
        engine=first,
        source=src,
        spans=spans,
        config=config,
        artifact="srt",
        **{"max_attempts": 1},
    )

    assert first_run.status == "failed"
    assert store.done_chunk_indices(first_run.task_id) == {0}

    # 第二次：带着同一个 task_id 续跑，只应补跑未完成的分片
    second = FakeEngine()
    resumed, store2, _, _ = run_pipeline(
        tmp_path,
        engine=second,
        source=src,
        spans=spans,
        config=config,
        task_id=first_run.task_id,
        artifact="srt",
    )

    assert resumed.status == "done"
    assert resumed.task_id == first_run.task_id
    assert len(second.calls) < len(spans), "已完成的分片被重跑了（白花时间和钱）"
    chunks = store2.chunks_for(resumed.task_id)
    assert all(c.status == "done" for c in chunks)
    assert chunks[0].text == "第一片内容。"
    # 续跑恢复的分片必须带着时间轴，否则 srt 会散架
    assert resumed.srt_path is not None
    assert "-->" in resumed.srt_path.read_text(encoding="utf-8")


def test_resume_reruns_done_chunk_with_empty_text(tmp_path: Path):
    """空文本的 done 分片在续跑时必须重跑，不能从产物里静默消失。"""
    spans = [(0.0, 40.0), (41.0, 80.0), (81.0, 120.0)]
    src = make_wav(tmp_path, seconds=125.0)

    # 第一次：第 2 片返回空文本（例如 VAD 误检出的噪音段）
    class EmptyTextEngine(FakeEngine):
        def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False):
            result = super().transcribe(
                audio_path, language=language, hotwords=hotwords, want_timestamps=want_timestamps
            )
            if len(self.calls) == 2:
                return TranscriptResult(
                    text="", segments=[], engine=self.name, audio_seconds=2.0, has_timestamps=False
                )
            return result

    first = EmptyTextEngine()
    first_run, store, config, _ = run_pipeline(
        tmp_path, engine=first, source=src, spans=spans, artifact="txt"
    )
    assert first_run.status == "done"
    chunks = store.chunks_for(first_run.task_id)
    assert chunks[1].status == "done" and chunks[1].text == ""

    # 续跑：空文本的那片必须退回重跑，而不是被静默跳过
    second = FakeEngine(text_prefix="补")
    resumed, store2, _, _ = run_pipeline(
        tmp_path,
        engine=second,
        source=src,
        spans=spans,
        config=config,
        task_id=first_run.task_id,
        artifact="txt",
    )
    assert resumed.status == "done"
    assert len(second.calls) == 1, "空文本的已完成分片没有退回重跑"
    texts = [c.text for c in store2.chunks_for(resumed.task_id)]
    assert all(texts), f"产物会静默缺字：{texts}"


def test_cancel_stops_between_chunks_and_keeps_done(tmp_path: Path):
    """用户停止：已完成分片保留、不写 txt/srt、状态可续跑。"""
    spans = [(0.0, 40.0), (41.0, 80.0), (81.0, 120.0)]
    src = make_wav(tmp_path, seconds=125.0)
    config = make_config(tmp_path)
    store = Store(config.state_db)

    class CancelAfterFirst(FakeEngine):
        def __init__(self, pipeline_box):
            super().__init__()
            self.pipeline_box = pipeline_box

        def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False):
            self.calls.append(Path(audio_path))
            if len(self.calls) == 1:
                return TranscriptResult(
                    text="第一片内容。",
                    engine=self.name,
                    audio_seconds=40.0,
                    segments=[Segment(0.0, 40.0, "第一片内容。")],
                    has_timestamps=True,
                )
            raise AssertionError("取消后不应再调用引擎")

    pipeline_holder: dict = {}
    engine = CancelAfterFirst(pipeline_holder)
    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda kind, cfg, artifact: engine,
        vad_fn=lambda path: spans,
        sleep=lambda seconds: None,
    )
    pipeline_holder["p"] = pipeline

    # 第一片成功后立刻请求停止
    original_transcribe = engine.transcribe

    def transcribe_then_cancel(audio_path, **kwargs):
        out = original_transcribe(audio_path, **kwargs)
        pipeline.cancel()
        return out

    engine.transcribe = transcribe_then_cancel  # type: ignore[method-assign]

    result = pipeline.run(src, mode="offline", artifact="srt")
    assert result.status == "failed"
    assert "停止" in (result.error or "")
    assert result.txt_path is None and result.srt_path is None
    assert store.done_chunk_indices(result.task_id) == {0}
    task = store.get_task(result.task_id)
    assert task is not None and task.status == "failed"


def test_chunk_state_survives_process_restart(tmp_path: Path):
    """换一个 Pipeline/Store 实例（模拟重启）也能读到已完成分片。"""
    src = make_wav(tmp_path)
    config = make_config(tmp_path)
    result, store, _, _ = run_pipeline(tmp_path, engine=FakeEngine(), source=src, config=config)
    fresh_store = Store(config.state_db)
    chunks = fresh_store.chunks_for(result.task_id)
    assert chunks and chunks[0].segments, "分段时间轴必须持久化"


# ---------- 落点与预估 ----------


def test_output_falls_back_when_source_dir_is_readonly(tmp_path: Path):
    src_dir = tmp_path / "readonly"
    src_dir.mkdir()
    src = make_wav(src_dir)
    src_dir.chmod(0o500)
    try:
        result, _, config, _ = run_pipeline(tmp_path, engine=FakeEngine(), source=src)
        assert result.status == "done"
        assert result.out_dir == config.output_dir / src.stem
        assert result.txt_path.exists()
    finally:
        src_dir.chmod(0o700)


def test_estimate_cost_only_prices_what_we_know():
    assert estimate_cost("offline", "txt", 3600) == 0.0
    assert estimate_cost("online", "srt", 3600) == pytest.approx(0.1)
    assert estimate_cost("online", "txt", 3600) is None  # 百炼单价不猜


def test_invalid_mode_or_artifact_is_rejected_before_work(tmp_path: Path):
    engine = FakeEngine()
    config = make_config(tmp_path)
    store = Store(config.state_db)
    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda *a, **k: engine,
        vad_fn=lambda p: [],
        sleep=lambda s: None,
    )
    src = make_wav(tmp_path)
    with pytest.raises(FatalError):
        pipeline.run(src, mode="auto", artifact="txt")
    with pytest.raises(FatalError):
        pipeline.run(src, mode="offline", artifact="both")
    assert engine.calls == []


def test_missing_input_fails_without_creating_outputs(tmp_path: Path):
    engine = FakeEngine()
    config = make_config(tmp_path)
    store = Store(config.state_db)
    pipeline = Pipeline(
        config,
        store,
        engine_factory=lambda *a, **k: engine,
        vad_fn=lambda p: [],
        sleep=lambda s: None,
    )
    result = pipeline.run(tmp_path / "nope.m4a", mode="offline", artifact="txt")
    assert result.status == "failed"
    assert "不存在" in (result.error or "")
    assert engine.calls == []


# ---------- 重试辅助函数 ----------


def test_with_retries_uses_exponential_backoff():
    delays: list[float] = []
    attempts: list[int] = []

    def flaky(attempt: int):
        attempts.append(attempt)
        if attempt < 3:
            raise RecoverableError("boom")
        return "ok"

    assert with_retries(flaky, attempts=3, backoff=1.0, sleep=delays.append) == "ok"
    assert attempts == [1, 2, 3]
    assert delays == [1.0, 2.0]


def test_with_retries_reraises_last_recoverable_error():
    calls = []

    def always_fail(attempt: int):
        calls.append(attempt)
        raise RecoverableError(f"第 {attempt} 次")

    with pytest.raises(RecoverableError, match="第 2 次"):
        with_retries(always_fail, attempts=2, backoff=0.1, sleep=lambda s: None)
    assert calls == [1, 2]


def test_with_retries_succeeds_first_try_without_sleeping():
    delays: list[float] = []
    assert with_retries(lambda attempt: 42, attempts=3, backoff=1.0, sleep=delays.append) == 42
    assert delays == []


@pytest.fixture(autouse=True)
def _cleanup_tmp_workdirs():
    yield
    for path in Path("/tmp").glob("transcript-*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def test_source_duration_is_recorded_even_after_resume(tmp_path: Path):
    """任务时长取源文件时长，不能是"已完成分片时长之和"。

    实测 bug：87 分钟录音在续跑后只记了 1225s——因为离线分片不报时长，
    只有续跑恢复的分片带了 chunk.duration，求和就成了部分和。
    """
    src = make_wav(tmp_path, seconds=125.0)
    spans = [(0.0, 40.0), (41.0, 80.0), (81.0, 120.0)]
    config = make_config(tmp_path)

    class HalfFailing(FakeEngine):
        def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False):
            self.calls.append(Path(audio_path))
            if len(self.calls) >= 2:
                raise RecoverableError("上游 503")
            return TranscriptResult(
                text="第一片。",
                engine=self.name,
                segments=[Segment(0.0, 40.0, "第一片。")],
                has_timestamps=True,
            )

    first, store, config, _ = run_pipeline(
        tmp_path,
        engine=HalfFailing(),
        source=src,
        spans=spans,
        config=config,
        artifact="srt",
        **{"max_attempts": 1},
    )
    assert first.status == "failed"

    resumed, store2, _, _ = run_pipeline(
        tmp_path,
        engine=FakeEngine(),
        source=src,
        spans=spans,
        config=config,
        task_id=first.task_id,
        artifact="srt",
    )
    assert resumed.status == "done"
    task = store2.get_task(resumed.task_id)
    assert task is not None
    assert task.audio_seconds == pytest.approx(125.0, rel=0.02), (
        f"记成了 {task.audio_seconds}s，应该是源文件时长"
    )
