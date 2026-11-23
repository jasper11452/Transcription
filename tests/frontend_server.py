"""Isolated browser fixture: temporary DB, synthetic audio, no model or engine calls."""

import tempfile
import wave
from pathlib import Path

import uvicorn

from transcript.config import Config
from transcript.store import Store
from transcript.web.app import create_app
from transcript.web.jobs import JobManager

with tempfile.TemporaryDirectory(prefix="transcript-browser-") as root:
    folder = Path(root)
    audio = folder / "fixture.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * 16000 * 12)
    txt = folder / "fixture.txt"
    txt.write_text("第一句话。第二句话。\n" * 1600)
    srt = folder / "fixture.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:06,000\n第一句话。\n\n2\n00:00:06,000 --> 00:00:12,000\n第二句话。\n"
    )
    raw = folder / "fixture.raw.json"
    raw.write_text('{"fixture":true}')
    config = Config(
        config_path=folder / "config.env",
        state_db=folder / "state.db",
        output_dir=folder / "output",
        glossary_path=folder / "words.txt",
    )
    store = Store(config.state_db)
    tid = store.create_task(
        name="浏览器回归录音", source_path=str(audio), mode="offline", artifact="srt"
    )
    store.update_task(
        tid,
        status="done",
        chars=16000,
        audio_seconds=12,
        txt_path=str(txt),
        srt_path=str(srt),
        raw_path=str(raw),
    )
    for i in range(2):
        store.upsert_chunk(
            tid, idx=i, start=i * 6, end=(i + 1) * 6, status="done", text="第一句话。"
        )
    app = create_app(config, store, JobManager(config, store))

    # Guard against any accidental transcription or Finder invocation by browser tests.
    @app.middleware("http")
    async def readonly_engines(request, call_next):
        from fastapi.responses import JSONResponse

        if request.method == "POST" and (
            request.url.path == "/api/tasks"
            or request.url.path.endswith("/resume")
            or request.url.path == "/api/reveal"
        ):
            return JSONResponse(
                {"error": "fixture server blocks engine and Finder calls"}, status_code=403
            )
        return await call_next(request)

    uvicorn.run(app, host="127.0.0.1", port=8876, log_level="warning")
