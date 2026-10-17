"""编排：入料 → 归一化 → VAD 切片 → 逐片转写 → 合并 → 词表 → 渲染 → 落盘。

这里的四条硬规则（对应 AGENTS.md 的"架构约束"）：
1. **分片是唯一的重试/落盘单位**：每片完成即写入 SQLite，进程被杀后能续跑且不重复花钱；
2. **只重试可恢复错误**：网络/超时/5xx/429 退避重试；参数、格式、额度类错误直接暴露；
3. **错误不得当结果返回**：只要还有失败分片，就**不写** txt/srt（避免看起来完整其实缺字），
   但已完成分片全部保留，页面可"续跑"；
4. **原文件只读**：一切中间产物都在临时工作目录里，结束时删掉。

重建自 ``legacy/transcript/src/transcript/pipeline.py``。Phase 5 的三处结构性修正：

- **产物选择是单点决策**（`artifact=txt` 只写 `.txt`，不写 `.srt` —— Q9）；
- **引擎只交原始 words**，对齐在这里调 ``post.align``（架构 v2 砍掉 `engines → post`）；
- **P0-2**：任一分片失败 → 任务 failed、两个产物都不写、已完成分片留在库里。
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from transcript_reimagined.config import Config
from transcript_reimagined.diar import assign_speaker, diarize
from transcript_reimagined.domain import (
    Chunk,
    FatalError,
    Segment,
    TranscriptError,
    TranscriptResult,
    Word,
    is_recoverable,
)
from transcript_reimagined.engines import Engine, build_engine, resolve_kind
from transcript_reimagined.ingest import audio as audio_mod
from transcript_reimagined.ingest import vad as vad_mod
from transcript_reimagined.ingest.chunking import plan_chunks
from transcript_reimagined.post.align import build_segments, normalize_for_compare
from transcript_reimagined.post.glossary import (
    apply_rules,
    load_glossary,
    load_hot_words,
)
from transcript_reimagined.post.glossary import hotwords as build_hotwords
from transcript_reimagined.post.merge import merge_results
from transcript_reimagined.post.products import (
    RawContext,
    render_products_for,
    write_products_for,
)
from transcript_reimagined.state import ChunkState, Store

from .progress import Progress, RunResult

# 在线单价（实测：mai-transcribe-2 ≈ $0.1/小时音频，见 docs/spec.md）
ONLINE_PRICE_PER_HOUR = 0.1


def estimate_cost(
    mode: str, artifact: str, audio_seconds: float, *, online_engine: str = "auto"
) -> float | None:
    """提交前的费用预估。只对已知单价的路径给数，其余返回 None（不编）。"""
    if mode != "online":
        return 0.0
    engine = (online_engine or "auto").strip().lower()
    if engine == "bcut":
        return 0.0  # 匿名免费接口
    if engine == "dashscope":
        return None  # 按秒计费，单价随账号/活动变化，不猜
    # auto：txt 走百炼（不猜），srt 走 OpenRouter（≈$0.1/小时，实测）
    if engine == "openrouter" or (engine == "auto" and artifact == "srt"):
        return round(ONLINE_PRICE_PER_HOUR * audio_seconds / 3600, 6)
    return None


def with_retries[T](
    fn: Callable[[int], T],
    *,
    attempts: int,
    backoff: float,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, float, Exception], None] | None = None,
) -> T:
    """指数退避重试，**只对可恢复错误**生效。

    不可恢复错误会立刻抛出——重试参数错误只是把同一笔失败重复三次。
    """
    last: TranscriptError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn(attempt)
        except TranscriptError as exc:
            if not is_recoverable(exc):
                raise
            last = exc
            if attempt >= attempts:
                break
            delay = backoff * (2 ** (attempt - 1))
            if on_retry:
                on_retry(attempt, delay, exc)
            sleep(delay)
    assert last is not None
    raise last


class PipelineCancelled(Exception):
    """用户主动停止；已完成分片保留，不写 txt/srt。"""


class Pipeline:
    """一次转写任务的完整编排。引擎与 VAD 都可注入，便于测试与替换。"""

    def __init__(
        self,
        config: Config,
        store: Store,
        *,
        engine_factory: Callable[..., Engine] = build_engine,
        vad_fn: Callable[[Path], list[tuple[float, float]]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_event: Callable[[Progress], None] | None = None,
        workdir_root: Path | None = None,
    ):
        self.config = config
        self.store = store
        self._engine_factory = engine_factory
        self._vad_fn = vad_fn or (
            lambda path: vad_mod.speech_spans(path, model_id=self.config.vad_model)
        )
        self._sleep = sleep
        self._on_event = on_event
        self._workdir_root = workdir_root
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """请求停止：分片边界生效，已完成结果保留。"""
        self._cancel.set()

    # ---------- 对外入口 ----------

    def run(
        self,
        source: Path | str,
        *,
        mode: str = "offline",
        artifact: str = "txt",
        language: str | None = None,
        task_id: int | None = None,
        online_engine: str | None = None,
    ) -> RunResult:
        if mode not in {"offline", "online"}:
            raise FatalError(f"未知模式：{mode}（只有离线/在线两个值）")
        if artifact not in {"txt", "srt"}:
            raise FatalError(f"未知产物：{artifact}（只有 txt/srt）")

        src = Path(source).expanduser()
        try:
            info = audio_mod.probe(src)
        except TranscriptError as exc:
            return self._fail(task_id, engine="-", error=str(exc))

        try:
            kind = resolve_kind(
                self.config, mode=mode, artifact=artifact, online_engine=online_engine
            )
            engine = self._engine_factory(kind, self.config, artifact=artifact)
        except (ValueError, TranscriptError) as exc:
            return self._fail(task_id, engine="-", error=str(exc))
        rules = load_glossary(self.config.glossary_path)

        tid = (
            task_id
            if task_id is not None
            else self.store.create_task(
                name=src.stem,
                source_path=str(src),
                mode=mode,
                artifact=artifact,
                engine=engine.name,
                duration_s=info.duration,
            )
        )
        self.store.update_task(
            tid, status="running", engine=engine.name, duration_s=info.duration, error=None
        )
        self._emit(
            "probe", f"{src.name}：{info.duration:.1f}s，{info.megabytes:.1f}MB", current=0, total=1
        )

        workdir = Path(tempfile.mkdtemp(prefix="transcript-", dir=self._workdir_root))
        try:
            return self._run_inner(
                tid,
                src,
                info,
                mode=mode,
                artifact=artifact,
                engine=engine,
                language=language,
                rules=rules,
                workdir=workdir,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ---------- 内部步骤 ----------

    def _run_inner(
        self,
        tid: int,
        src: Path,
        info,
        *,
        mode: str,
        artifact: str,
        engine: Engine,
        language: str | None,
        rules,
        workdir: Path,
    ) -> RunResult:
        # RULE-061：引擎没有时间戳能力时，在归一化/切片/花钱之前就失败。
        if artifact == "srt" and not getattr(engine, "has_timestamps", False):
            return self._fail(
                tid,
                engine=engine.name,
                error=f"引擎 {engine.name} 不提供时间戳，无法产出 srt（请改用离线或 mai-transcribe-2）",
            )
        try:
            wav = audio_mod.to_wav16k(src, workdir / "work.wav")
            audio_mod.verify(wav, "wav16k")
            self._emit("normalize", "已归一化为 16k 单声道 wav")

            upload_path = wav
            upload_kind = "wav16k"
            if mode == "online":
                mp3 = audio_mod.to_mp3_64k(wav, workdir / "work.mp3")
                audio_mod.verify(mp3, "mp3_64k")
                upload_path, upload_kind = mp3, "mp3_64k"
                self._emit("normalize", f"在线工作副本 {mp3.stat().st_size / 1e6:.2f}MB（mp3 64k）")

            self._emit("vad", "正在做语音活动检测")
            spans = self._vad_fn(wav)
            # 切片上限取“配置值”与“引擎单次上限”的较小值：
            # 引擎自己声明能吃多长（百炼原生实测 300s 上限），不能让配置把它撑爆。
            engine_max = getattr(engine, "max_chunk_s", None)
            chunk_max = self.config.chunk_max_s
            if engine_max and engine_max < chunk_max:
                chunk_max = float(engine_max)
                self._emit("plan", f"按引擎单次上限收紧切片到 {chunk_max:.0f}s")
            # 引擎上限可能小于用户的 chunk_min_s：取小，否则 plan_chunks 会因参数矛盾直接报错
            chunk_min = min(self.config.chunk_min_s, chunk_max)
            chunks = plan_chunks(
                spans,
                info.duration,
                min_s=chunk_min,
                max_s=chunk_max,
                overlap_s=self.config.chunk_overlap_s,
            )
            # 不变量：plan_chunks 保证片长 ≤ chunk_max（含重叠）。这里再挡一道，
            # 宁可任务失败，也不发一次注定被上游拒的请求（那笔钱和时间都白花）。
            over = [c for c in chunks if engine_max and c.duration > engine_max + 1e-6]
            if over:
                return self._fail(
                    tid,
                    engine=engine.name,
                    error=f"切片 {over[0].duration:.2f}s 超过引擎上限 {engine_max:.0f}s，已中止"
                    "（宁可失败，也不发一次注定被拒的请求）",
                )
            for chunk in chunks:
                self.store.ensure_chunk(tid, idx=chunk.index, start=chunk.start, end=chunk.end)
            self._emit(
                "plan",
                f"切成 {len(chunks)} 片（VAD 检出 {len(spans)} 段语音）",
                current=0,
                total=len(chunks),
            )
        except TranscriptError as exc:
            return self._fail(tid, engine=engine.name, error=str(exc))

        try:
            results, failed = self._transcribe_chunks(
                tid,
                chunks,
                engine=engine,
                source=upload_path,
                source_kind=upload_kind,
                workdir=workdir,
                language=language,
                rules=rules,
                mode=mode,
                artifact=artifact,
            )
        except PipelineCancelled as exc:
            # 停止：不写 txt/srt；状态 failed 以便续跑（resumable）
            return self._fail(tid, engine=engine.name, error=str(exc))

        if failed:
            message = (
                f"{len(failed)} 个分片失败（{', '.join(str(i) for i in sorted(failed))}）；"
                "已完成分片已保留，可点续跑，未写出 txt/srt"
            )
            self.store.update_task(tid, status="failed", error=message)
            self._emit("failed", message, current=len(results), total=len(chunks))
            return RunResult(task_id=tid, status="failed", engine=engine.name, error=message)

        if not results:
            return self._fail(tid, engine=engine.name, error="没有可用的转写结果")

        merged = merge_results(results)

        # 说话人分离（离线模式且已启用时）。失败不阻断正常转写（C8 的边界）。
        if self.config.enable_diar and mode == "offline" and merged.segments:
            try:
                self._emit("diar", "正在做说话人分离…")
                diar_segs = diarize(
                    workdir / "work.wav",
                    lib_path=self.config.diar_lib,
                    model_path=self.config.diar_model,
                )
                assign_speaker(merged.segments, diar_segs)
                n_spk = len({s.speaker for s in merged.segments if s.speaker})
                self._emit("diar", f"说话人分离完成，检出 {n_spk} 人")
            except Exception as exc:  # noqa: BLE001 - 分离失败不阻断正常转写
                self._emit("diar", f"说话人分离跳过（{exc}）")

        if artifact == "srt" and not merged.segments and not merged.has_timestamps:
            return self._fail(
                tid,
                engine=engine.name,
                error=f"引擎 {engine.name} 没有返回任何时间轴，无法产出 srt",
            )

        self._emit("merge", f"合并完成：{len(merged.text)} 字，{len(merged.segments)} 段")

        final_text, changes = apply_rules(merged.text, rules)
        segments = [
            Segment(s.start, s.end, apply_rules(s.text, rules)[0], s.words, s.speaker)
            for s in merged.segments
        ]

        out_dir = self._resolve_output_dir(src)
        stem = src.stem
        products = render_products_for(
            final_text,
            segments,
            changes,
            artifact=artifact,
            merged_text_before_glossary=merged.text,
            context=RawContext(
                task_id=tid,
                source=str(src),
                mode=mode,
                artifact=artifact,
                engine=engine.name,
                config=self._config_snapshot(),
                chunks=self._chunk_payloads(tid),
            ),
        )
        written = write_products_for(products, out_dir, stem, artifact=artifact)

        result = RunResult(
            task_id=tid,
            status="done",
            engine=engine.name,
            out_dir=written.out_dir,
            txt_path=written.txt_path,
            srt_path=written.srt_path,
            raw_path=written.raw_path,
            audio_seconds=info.duration,
            cost_usd=merged.cost_usd,
            chars=len(normalize_for_compare(final_text)),
            changes=changes,
        )
        self.store.update_task(
            tid,
            status="done",
            out_dir=str(result.out_dir),
            txt_path=str(result.txt_path) if result.txt_path else None,
            srt_path=str(result.srt_path) if result.srt_path else None,
            raw_path=str(result.raw_path),
            chars=result.chars,
            audio_seconds=result.audio_seconds,
            cost_usd=result.cost_usd,
            error=None,
        )
        self._emit("done", f"完成：{out_dir}", current=len(chunks), total=len(chunks))
        return result

    def _transcribe_chunks(
        self,
        tid: int,
        chunks: list[Chunk],
        *,
        engine: Engine,
        source: Path,
        source_kind: str,
        workdir: Path,
        language: str | None,
        rules,
        mode: str,
        artifact: str,
    ) -> tuple[list[TranscriptResult], list[int]]:
        """逐片转写。在线可并行、离线串行（本地模型独占）。

        返回 (按分片顺序排列的结果, 失败分片下标)。已完成的分片直接复用，
        绝不重跑（本地是时间，在线是钱）。
        """
        need_ts = artifact == "srt" or self.config.enable_diar
        done = set(self.store.done_chunk_indices(tid))
        states: dict[int, ChunkState] = {c.idx: c for c in self.store.chunks_for(tid)}
        by_index: dict[int, TranscriptResult] = {}
        failed: list[int] = []
        hotword_list = build_hotwords(rules, extra=load_hot_words(self.config.glossary_path))

        for chunk in chunks:
            state = states.get(chunk.index)
            if chunk.index in done and state is not None:
                # 缓存复用的两个例外，都要退回重跑——绝不让已完成的分片从产物里静默消失：
                # 1. 空文本：引擎对这片可能根本没出字，重跑才对得起“逐字一致”；
                # 2. 要时间轴（srt/说话人分离）但缓存里既没有 segments 也没有 words。
                if not state.text or (need_ts and not state.segments and not state.words):
                    done.discard(chunk.index)  # 退回待转写队列
                    continue
                segments = list(state.segments)
                if need_ts and not segments and state.words:
                    # 有原始 words 就能在本地重建段落，不必重新付费调用引擎。
                    segments = build_segments(state.text, state.words, offset=0.0)
                    # 把重建结果写回缓存，下一次续跑/页面读取都能直接用。
                    self.store.upsert_chunk(
                        tid,
                        idx=chunk.index,
                        start=chunk.start,
                        end=chunk.end,
                        status="done",
                        text=state.text,
                        words=list(state.words),
                        segments=segments,
                        attempts=state.attempts,
                    )
                by_index[chunk.index] = TranscriptResult(
                    text=state.text,
                    segments=segments,
                    words=list(state.words),
                    engine=engine.name,
                    has_timestamps=bool(segments or state.words),
                )
                self._emit(
                    "chunk",
                    f"分片 {chunk.index + 1}/{len(chunks)} 已有结果，跳过",
                    current=chunk.index + 1,
                    total=len(chunks),
                    chunk_index=chunk.index,
                )
        pending = [c for c in chunks if c.index not in done]

        def work(chunk: Chunk) -> TranscriptResult:
            if self._cancel.is_set():
                raise PipelineCancelled(f"分片 {chunk.index + 1} 开始前已停止")
            piece = workdir / f"chunk_{chunk.index:04d}{Path(source).suffix}"
            audio_mod.cut(source, piece, chunk.start, chunk.end, kind=source_kind)
            return engine.transcribe(
                piece,
                language=language,
                hotwords=hotword_list or None,
                # 只有字幕产物或说话人分离需要额外的时间轴；txt 任务保持原有成本。
                want_timestamps=need_ts,
                duration_s=chunk.duration,
            )

        def handle(chunk: Chunk) -> None:
            attempt_box = {"n": 0}

            def attempt(attempt_no: int) -> TranscriptResult:
                attempt_box["n"] = attempt_no
                return work(chunk)

            try:
                result = with_retries(
                    attempt,
                    attempts=self.config.max_attempts,
                    backoff=self.config.backoff_base,
                    sleep=self._sleep,
                    on_retry=lambda n, delay, exc: self._emit(
                        "retry",
                        f"分片 {chunk.index + 1} 第 {n} 次失败（{exc}），{delay:.0f}s 后重试",
                        current=chunk.index,
                        total=len(chunks),
                        chunk_index=chunk.index,
                    ),
                )
            except PipelineCancelled as exc:
                # 停止不是错误：不把错误文案当结果，已完成分片原样保留
                self._emit(
                    "failed",
                    str(exc),
                    current=chunk.index,
                    total=len(chunks),
                    chunk_index=chunk.index,
                )
                raise
            except TranscriptError as exc:
                self.store.upsert_chunk(
                    tid,
                    idx=chunk.index,
                    start=chunk.start,
                    end=chunk.end,
                    status="failed",
                    text="",
                    attempts=attempt_box["n"],
                    error=str(exc),
                )
                failed.append(chunk.index)
                self._emit(
                    "chunk_failed",
                    f"分片 {chunk.index + 1} 失败：{exc}",
                    current=chunk.index,
                    total=len(chunks),
                    chunk_index=chunk.index,
                )
                return

            text, words, segments = self._materialize(result, chunk, need_ts=need_ts)
            self.store.upsert_chunk(
                tid,
                idx=chunk.index,
                start=chunk.start,
                end=chunk.end,
                status="done",
                text=text,
                words=words,
                segments=segments,
                attempts=attempt_box["n"],
            )
            by_index[chunk.index] = TranscriptResult(
                text=text,
                segments=segments,
                words=words,
                language=result.language,
                audio_seconds=result.audio_seconds,
                cost_usd=result.cost_usd,
                engine=result.engine,
                # 这里记录的是**引擎实际给出的时间轴**，不是 align 的等比兜底；
                # “能不能出 srt”由 engine.has_timestamps 判定（RULE-061）。
                has_timestamps=bool(result.words or result.segments),
            )
            self._emit(
                "chunk",
                f"分片 {chunk.index + 1}/{len(chunks)} 完成（{len(text)} 字）",
                current=chunk.index + 1,
                total=len(chunks),
                chunk_index=chunk.index,
            )

        if mode == "online" and self.config.online_concurrency > 1 and len(pending) > 1:
            with ThreadPoolExecutor(max_workers=self.config.online_concurrency) as pool:
                try:
                    list(pool.map(handle, pending))
                except PipelineCancelled:
                    raise
        else:
            for chunk in pending:
                if self._cancel.is_set():
                    raise PipelineCancelled(f"已停止：{len(by_index)} 片已完成并保留，可续跑")
                handle(chunk)

        # 顺序由分片下标决定，不依赖完成先后（并行时尤其重要）
        results = [by_index[c.index] for c in chunks if c.index in by_index]
        return results, failed

    @staticmethod
    def _materialize(
        result: TranscriptResult, chunk: Chunk, *, need_ts: bool
    ) -> tuple[str, list[Word], list[Segment]]:
        """把引擎结果平移到整段音频的绝对时间轴，并按需补出 segments。

        引擎只交原始 words（架构 v2）；这里调 ``post.align`` 生成段落。
        原生带 segments 的引擎（OpenRouter/必剪）直接平移，不重新对齐。
        """
        words = [
            Word(w.text, w.start + chunk.start, w.end + chunk.start, w.probability)
            for w in result.words
        ]
        if result.segments:
            segments = [s.shifted(chunk.start) for s in result.segments]
        elif need_ts:
            segments = build_segments(
                result.text, result.words, offset=chunk.start, duration_s=chunk.duration
            )
        else:
            segments = []
        return result.text, words, segments

    # ---------- 落盘 ----------

    def _resolve_output_dir(self, src: Path) -> Path:
        """默认与原文件同目录；不可写时回退到配置的输出目录（并让调用方可见）。"""
        candidate = src.parent
        try:
            probe_file = candidate / f".transcript-write-test-{src.stem}"
            probe_file.touch()
            probe_file.unlink()
            return candidate
        except OSError:
            fallback = self.config.output_dir / src.stem
            fallback.mkdir(parents=True, exist_ok=True)
            self._emit("write", f"原目录不可写，产物改落到 {fallback}")
            return fallback

    def _config_snapshot(self) -> dict:
        return {
            "offline_model": self.config.offline_model,
            "timing_model": self.config.timing_model,
            "vad_model": self.config.vad_model,
            "dashscope_model": self.config.dashscope_model,
            "openrouter_model": self.config.openrouter_model,
            "online_engine": self.config.online_engine,
            "chunk_min_s": self.config.chunk_min_s,
            "chunk_max_s": self.config.chunk_max_s,
            "chunk_overlap_s": self.config.chunk_overlap_s,
        }

    def _chunk_payloads(self, tid: int) -> list[dict]:
        return [
            {
                "idx": c.idx,
                "start": c.start,
                "end": c.end,
                "status": c.status,
                "text": c.text,
                "attempts": c.attempts,
                "error": c.error,
                "words": [
                    {
                        "text": w.text,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    }
                    for w in c.words
                ],
            }
            for c in self.store.chunks_for(tid)
        ]

    # ---------- 杂项 ----------

    def _emit(
        self,
        stage: str,
        message: str,
        *,
        current: int = 0,
        total: int = 0,
        chunk_index: int | None = None,
    ) -> None:
        if self._on_event:
            self._on_event(Progress(stage, message, current, total, chunk_index))

    def _fail(self, task_id: int | None, *, engine: str, error: str) -> RunResult:
        if task_id is not None:
            self.store.update_task(task_id, status="failed", error=error)
        self._emit("failed", error)
        return RunResult(task_id=task_id or 0, status="failed", engine=engine, error=error)
