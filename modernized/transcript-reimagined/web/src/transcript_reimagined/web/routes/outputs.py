"""产物、原音频与本机「在访达中显示」。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse
from transcript_reimagined.post.contracts import output_preview

from ..dependencies import AppContext, get_context

router = APIRouter(prefix="/api")

_AUDIO_MIME = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}


def _output_path(ctx: AppContext, task_id: int, kind: str) -> Path:
    task = ctx.store.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if kind not in ("txt", "srt"):
        raise HTTPException(404, f"这个任务没有 {kind} 产物")
    value = task.txt_path if kind == "txt" else task.srt_path
    if not value:
        raise HTTPException(404, f"这个任务没有 {kind} 产物")
    path = Path(value)
    if not path.is_file():
        raise HTTPException(404, f"{kind} 产物已被移动或删除：{value}")
    return path


@router.get("/tasks/{task_id}/output")
def get_output(task_id: int, kind: str = "txt", ctx: AppContext = Depends(get_context)) -> dict:
    path = _output_path(ctx, task_id, kind)
    content = path.read_text(encoding="utf-8", errors="replace")
    preview = output_preview(content, path, kind=kind)
    return {
        "content": preview.content,
        "path": preview.path,
        "truncated": preview.truncated,
    }


@router.get("/tasks/{task_id}/output/file")
def get_output_file(
    task_id: int,
    kind: str = "txt",
    download: bool = False,
    ctx: AppContext = Depends(get_context),
):
    """完整产物；与受限 JSON 预览分离，下载保持原文件字节。"""
    path = _output_path(ctx, task_id, kind)
    return FileResponse(
        path,
        media_type="text/plain; charset=utf-8",
        filename=path.name if download else None,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/tasks/{task_id}/audio")
def get_audio(task_id: int, ctx: AppContext = Depends(get_context)):
    task = ctx.store.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    source = Path(task.source_path)
    if not source.is_file():
        raise HTTPException(404, f"原文件已被移动或删除：{task.source_path}")
    return FileResponse(
        source, media_type=_AUDIO_MIME.get(source.suffix.lower(), "application/octet-stream")
    )


@router.post("/reveal")
def reveal(path: str = Form(...)) -> dict:
    """OS 副作用：在访达里选中路径。来源校验由 app 的中间件统一负责。"""
    target = Path(path).expanduser()
    if not target.exists():
        raise HTTPException(404, f"路径不存在：{path}")
    subprocess.run(["open", "-R", str(target)], check=False)
    return {"ok": True}
