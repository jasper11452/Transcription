"""编排：入料 → 归一化 → VAD 切片 → 逐片转写 → 合并 → 词表 → 渲染 → 落盘。

这里的四条硬规则（对应 AGENTS.md 的"架构约束"）：
1. **分片是唯一的重试/落盘单位**：每片完成即写入 SQLite，进程被杀后能续跑且不重复花钱；
2. **只重试可恢复错误**：网络/超时/5xx/429 退避重试；参数、格式、额度类错误直接暴露；
3. **错误不得当结果返回**：只要还有失败分片，就**不写** txt/srt（避免看起来完整其实缺字），
   但已完成分片全部保留，页面可"续跑"；
4. **原文件只读**：一切中间产物都在临时工作目录里，结束时删掉。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import audio as audio_mod
from . import vad as vad_mod
from .align import normalize_for_compare
from .chunking import plan_chunks
from .config import Config
from .engines.base import Engine, build_engine, resolve_kind
from .errors import FatalError, RecoverableError, TranscriptError
from .glossary import Change, apply_rules, change_comment, load_glossary, load_hot_words
from .glossary import hotwords as build_hotwords
from .merge import merge_results
from .models import Chunk, Segment, TranscriptResult
from .render import to_srt, to_txt
from .store import ChunkState, Store

# 在线单价（实测：mai-transcribe-2 ≈ $0.1/小时音频，见 docs/spec.md）
ONLINE_PRICE_PER_HOUR = 0.1


@dataclass
class Progress:
    """给页面的进度事件。stage 是稳定枚举，message 只用于展示。"""

    stage: str
    message: str
    current: int = 0
    total: int = 0
    chunk_index: int | None = None

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "chunk_index": self.chunk_index,
        }


@dataclass
class RunResult:
    task_id: int
    status: str
    engine: str
    out_dir: Path | None = None
    txt_path: Path | None = None
    srt_path: Path | None = None
    raw_path: Path | None = None
    audio_seconds: float | None = None
    cost_usd: float | None = None
    chars: int = 0
    changes: list[Change] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "engine": self.engine,
            "out_dir": str(self.out_dir) if self.out_dir else None,
            "txt_path": str(self.txt_path) if self.txt_path else None,
            "srt_path": str(self.srt_path) if self.srt_path else None,
            "raw_path": str(self.raw_path) if self.raw_path else None,
            "audio_seconds": self.audio_seconds,
            "cost_usd": self.cost_usd,
            "chars": self.chars,
            "changes": [c.describe() for c in self.changes],
            "error": self.error,
        }


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
    last: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn(attempt)
        except RecoverableError as exc:
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

        kind = resolve_kind(self.config, mode=mode, artifact=artifact, online_engine=online_engine)
        engine = self._engine_factory(kind, self.config, artifact=artifact)
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
            # 引擎自己声明能吃多长（百炼原生实测 300s 上限），不能让配置把它撑爆
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
            # 宁可任务失败，也不发一次注定被上游拒的请求（那笔钱和时间都白花）
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

        # 说话人分离（离线模式且已启用时）
        if self.config.enable_diar and mode == "offline" and merged.segments:
            try:
                from .diar import assign_speaker, diarize

                self._emit("diar", "正在做说话人分离…")
                diar_segs = diarize(
                    workdir / "work.wav",
                    lib_path=self.config.diar_lib,
                    model_path=self.config.diar_model,
                )
                assign_speaker(merged.segments, diar_segs)
                n_spk = len({s.speaker for s in merged.segments if s.speaker})
                self._emit("diar", f"说话人分离完成，检出 {n_spk} 人")
            except Exception as exc:  # 分离失败不阻断正常转写
                self._emit("diar", f"说话人分离跳过（{exc}）")

        if artifact == "srt" and not merged.has_timestamps:
            return self._fail(
                tid,
                engine=engine.name,
                error=f"引擎 {engine.name} 不提供时间戳，无法产出 srt（请改用离线或 mai-transcribe-2）",
            )

        self._emit("merge", f"合并完成：{len(merged.text)} 字，{len(merged.segments)} 段")

        final_text, changes = apply_rules(merged.text, rules)
        comment = change_comment(changes)
        segments = [
            Segment(s.start, s.end, apply_rules(s.text, rules)[0], s.words, s.speaker)
            for s in merged.segments
        ]

        out_dir = self._resolve_output_dir(src)
        stem = src.stem
        txt_path = self._write(out_dir / f"{stem}.txt", to_txt(final_text, None, comment_lines=comment))
        srt_path = self._write(out_dir / f"{stem}.srt", to_srt(segments, comment_lines=comment))

        raw_path = self._write_raw(
            out_dir / f"{stem}.raw.json",
            tid=tid,
            src=src,
            mode=mode,
            artifact=artifact,
            engine=engine,
            chunks=chunks,
            merged=merged,
            final_text=final_text,
            changes=changes,
        )

        result = RunResult(
            task_id=tid,
            status="done",
            engine=engine.name,
            out_dir=out_dir,
            txt_path=txt_path,
            srt_path=srt_path,
            raw_path=raw_path,
            audio_seconds=info.duration,
            cost_usd=merged.cost_usd,
            chars=len(normalize_for_compare(final_text)),
            changes=changes,
        )
        self.store.update_task(
            tid,
            status="done",
            out_dir=str(out_dir),
            txt_path=str(txt_path) if txt_path else None,
            srt_path=str(srt_path) if srt_path else None,
            raw_path=str(raw_path),
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
        done = self.store.done_chunk_indices(tid)
        states: dict[int, ChunkState] = {c.idx: c for c in self.store.chunks_for(tid)}
        by_index: dict[int, TranscriptResult] = {}
        failed: list[int] = []
        hotword_list = build_hotwords(rules, extra=load_hot_words(self.config.glossary_path))

        for chunk in chunks:
            state = states.get(chunk.index)
            if chunk.index in done and state is not None:
                # 缓存复用的两个例外，都要退回重跑——绝不让已完成的分片从产物里静默消失：
                # 1. 空文本：引擎对这片可能根本没出字，重跑才对得起“逐字一致”；
                # 2. 要时间轴（srt/说话人分离）但缓存里没有 segments。
                need_ts = artifact == "srt" or self.config.enable_diar
                if not state.text or (need_ts and not state.segments):
                    done = done - {chunk.index}  # 退回待转写队列
                    continue
                by_index[chunk.index] = TranscriptResult(
                    text=state.text,
                    segments=list(state.segments),
                    engine=engine.name,
                    has_timestamps=bool(state.segments),
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
                want_timestamps=(artifact == "srt" or self.config.enable_diar),
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

            shifted = result.shifted(chunk.start)
            self.store.upsert_chunk(
                tid,
                idx=chunk.index,
                start=chunk.start,
                end=chunk.end,
                status="done",
                text=shifted.text,
                words=[w for s in shifted.segments for w in s.words],
                segments=shifted.segments,
                attempts=attempt_box["n"],
            )
            by_index[chunk.index] = shifted
            self._emit(
                "chunk",
                f"分片 {chunk.index + 1}/{len(chunks)} 完成（{len(shifted.text)} 字）",
                current=chunk.index + 1,
                total=len(chunks),
                chunk_index=chunk.index,
            )

        if mode == "online" and self.config.online_concurrency > 1 and len(pending) > 1:
            from concurrent.futures import ThreadPoolExecutor

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

    @staticmethod
    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _write_raw(
        self,
        path: Path,
        *,
        tid: int,
        src: Path,
        mode: str,
        artifact: str,
        engine: Engine,
        chunks: list[Chunk],
        merged: TranscriptResult,
        final_text: str,
        changes: list[Change],
    ) -> Path:
        payload = {
            "task_id": tid,
            "source": str(src),
            "mode": mode,
            "artifact": artifact,
            "engine": engine.name,
            "chunk_count": len(chunks),
            "config": {
                "offline_model": self.config.offline_model,
                "timing_model": self.config.timing_model,
                "vad_model": self.config.vad_model,
                "dashscope_model": self.config.dashscope_model,
                "openrouter_model": self.config.openrouter_model,
                "online_engine": self.config.online_engine,
                "chunk_min_s": self.config.chunk_min_s,
                "chunk_max_s": self.config.chunk_max_s,
                "chunk_overlap_s": self.config.chunk_overlap_s,
            },
            "chunks": [
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
            ],
            "merged_text_before_glossary": merged.text,
            "final_text": final_text,
            "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in merged.segments],
            "glossary_changes": [
                {"wrong": c.wrong, "right": c.right, "count": c.count} for c in changes
            ],
        }
        return self._write(path, json.dumps(payload, ensure_ascii=False, indent=2))

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
