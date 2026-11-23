"""状态与费用预估。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form
from transcript_reimagined.domain import TranscriptError
from transcript_reimagined.engines import chunk_max_for
from transcript_reimagined.ingest import audio as audio_mod
from transcript_reimagined.orchestrate import estimate_cost

from ..dependencies import AppContext, get_context
from ..payloads import status_payload

router = APIRouter(prefix="/api")


@router.get("/status")
def status(ctx: AppContext = Depends(get_context)) -> dict:
    return status_payload(ctx.config, ctx.store)


@router.post("/estimate")
def estimate(
    source_path: str = Form(""),
    mode: str = Form("online"),
    artifact: str = Form("srt"),
    online_engine: str = Form("auto"),
    ctx: AppContext = Depends(get_context),
) -> dict:
    """提交前的费用/时长预估。读不了文件就给 ok=False + 原因，绝不崩。"""
    try:
        info = audio_mod.probe(Path(source_path).expanduser())
    except (TranscriptError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "duration_s": info.duration,
        "estimated_cost_usd": estimate_cost(
            mode, artifact, info.duration, online_engine=online_engine
        ),
        "chunk_max_s": chunk_max_for(
            ctx.config, mode=mode, artifact=artifact, online_engine=online_engine
        ),
    }
