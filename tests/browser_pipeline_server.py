"""Safe browser regression server: fake pipeline, synthetic audio, retained artifacts.

Run with `.venv/bin/python -m tests.browser_pipeline_server` (127.0.0.1:8877).
The original readonly fixture remains unchanged. No engines, keys or Finder calls.
Test files and SQLite are retained for evidence; this script never deletes them.
"""

from __future__ import annotations

import tempfile
import threading
import wave
from pathlib import Path

import uvicorn
from fastapi.responses import JSONResponse

from transcript.config import Config
from transcript.pipeline import Progress, RunResult
from transcript.store import Store
from transcript.web.app import create_app
from transcript.web.jobs import JobManager

TEXT = "第一句话。第二句话。\n" * 20_000 + "全文末尾✓\n"
SUBTITLES = (
    "1\n00:00:00,000 --> 00:00:06,000\n第一句话。\n\n2\n00:00:06,000 --> 00:00:12,000\n第二句话。\n"
)


def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="transcript-browser-pipeline-"))
    for name in ("success.wav", "fail-once.wav", "slow.wav"):
        with wave.open(str(folder / name), "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * 16000 * 12)
    config = Config(
        config_path=folder / "config.env",
        state_db=folder / "state.db",
        output_dir=folder / "output",
        glossary_path=folder / "words.txt",
    )
    store = Store(config.state_db)

    class BrowserPipeline:
        def __init__(self, state: Store, on_event):
            self.store = state
            self.on_event = on_event
            self.stop = threading.Event()

        def cancel(self):
            self.stop.set()

        def fail(self, task_id: int, message: str) -> RunResult:
            self.store.update_task(task_id, status="failed", error=message)
            return RunResult(
                task_id=task_id, status="failed", engine="browser-fixture", error=message
            )

        def run(self, source, *, task_id, mode, artifact, **_):
            if mode != "offline":
                return self.fail(task_id, "浏览器夹具只接受离线模拟，不调用在线引擎。")
            self.store.update_task(
                task_id, status="running", duration_s=12, engine="browser-fixture", error=None
            )
            for idx in range(2):
                self.store.ensure_chunk(task_id, idx=idx, start=idx * 6, end=(idx + 1) * 6)
            self.on_event(Progress("probe", "合成音频，仅模拟转录", current=0, total=2))
            for chunk in self.store.chunks_for(task_id):
                if self.stop.is_set():
                    return self.fail(task_id, "已停止；已完成分段保留，可续跑。")
                if chunk.done:
                    self.on_event(
                        Progress("transcribe", "复用已完成分段", current=chunk.idx + 1, total=2)
                    )
                    continue
                # Wait at a chunk boundary so browser cancellation can be observed.
                threading.Event().wait(6 if "slow" in Path(source).name else 2)
                if chunk.idx == 1 and "fail-once" in Path(source).name and chunk.attempts == 0:
                    message = "模拟分段失败；已完成分段保留，点击续跑。"
                    self.store.upsert_chunk(
                        task_id,
                        idx=chunk.idx,
                        start=chunk.start,
                        end=chunk.end,
                        status="failed",
                        attempts=1,
                        error=message,
                    )
                    return self.fail(task_id, message)
                self.store.upsert_chunk(
                    task_id,
                    idx=chunk.idx,
                    start=chunk.start,
                    end=chunk.end,
                    status="done",
                    text="第一句话。" if chunk.idx == 0 else "第二句话。",
                    attempts=chunk.attempts + 1,
                )
                self.on_event(
                    Progress("transcribe", "完成模拟分段", current=chunk.idx + 1, total=2)
                )
            if self.stop.is_set():
                return self.fail(task_id, "已停止；已完成分段保留，可续跑。")
            output = config.output_dir / str(task_id)
            output.mkdir(parents=True, exist_ok=True)
            txt = output / "会议文稿.txt"
            txt.write_text(TEXT, encoding="utf-8")
            srt = output / "会议文稿.srt" if artifact == "srt" else None
            if srt:
                srt.write_text(SUBTITLES, encoding="utf-8")
            self.store.update_task(
                task_id,
                status="done",
                progress=100,
                txt_path=str(txt),
                srt_path=str(srt) if srt else None,
                out_dir=str(output),
                chars=len(TEXT),
                audio_seconds=12,
                error=None,
            )
            return RunResult(
                task_id=task_id, status="done", engine="browser-fixture", txt_path=txt, srt_path=srt
            )

    def factory(state, on_event):
        return BrowserPipeline(state, on_event)

    manager = JobManager(config, store, pipeline_factory=factory)
    app = create_app(config, store, manager)

    @app.middleware("http")
    async def readonly_engines(request, call_next):
        # Fail closed if the injected seam is ever replaced. Keep destructive and
        # native/credential operations blocked, even in this disposable database.
        if (
            manager._pipeline_factory is not factory
            or request.method == "DELETE"
            or (
                request.method != "GET"
                and request.url.path in ("/api/reveal", "/api/credentials", "/api/upload")
            )
        ):
            return JSONResponse(
                {"error": "fixture blocks engines, Finder, keys and deletion"}, status_code=403
            )
        return await call_next(request)

    print(f"BROWSER_FIXTURE_ROOT={folder}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8877, log_level="warning")


if __name__ == "__main__":
    main()
