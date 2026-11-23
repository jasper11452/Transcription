"""任务资源：创建、列表、详情、取消、续跑、删除。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from transcript_reimagined.domain import TranscriptError
from transcript_reimagined.engines import engine_kind_from_name, required_key_attrs
from transcript_reimagined.ingest import audio as audio_mod

from ..dependencies import AppContext, get_context
from ..payloads import detail_payload, task_list
from ..validation import validate_task_request

router = APIRouter(prefix="/api/tasks")
MAX_UPLOAD_BYTES = 2 * 1024**3


@router.post("")
async def create_task(
    source_path: str = Form(""),
    file: UploadFile = File(None),
    mode: str = Form("offline"),
    artifact: str = Form("srt"),
    language: str = Form("zh"),
    online_engine: str = Form("auto"),
    ctx: AppContext = Depends(get_context),
) -> dict:
    try:
        validate_task_request(mode=mode, artifact=artifact, online_engine=online_engine)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if file:
        upload_dir = ctx.config.state_db.parent / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "audio").name
        target = upload_dir / f"{uuid.uuid4().hex[:8]}-{safe_name}"
        size = 0
        try:
            with target.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(400, "文件超过 2GB 上限")
                    handle.write(chunk)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        source = target
    elif source_path.strip():
        source = Path(source_path.strip()).expanduser()
    else:
        raise HTTPException(400, "请提供文件或路径")

    if not source.exists():
        raise HTTPException(400, f"文件不存在：{source}")
    try:
        audio_mod.probe(source)
    except TranscriptError as exc:
        raise HTTPException(400, str(exc)) from exc

    missing = [
        attr
        for attr in required_key_attrs(
            ctx.config, mode=mode, artifact=artifact, online_engine=online_engine
        )
        if not getattr(ctx.config, attr, "")
    ]
    if missing:
        envs = "、".join(a.upper() for a in missing)
        raise HTTPException(
            400,
            f"在线模式缺少凭据：{envs}。可在页面「在线密钥」里填写，"
            f"或写入 {ctx.config.config_path}",
        )

    task_id = ctx.store.create_task(
        name=source.name,
        source_path=str(source),
        mode=mode,
        artifact=artifact,
        engine=online_engine if mode == "online" else None,
    )
    ctx.jobs.submit(
        source=source,
        mode=mode,
        artifact=artifact,
        language=language,
        task_id=task_id,
        online_engine=online_engine if mode == "online" else None,
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("")
def list_tasks(limit: int = 50, ctx: AppContext = Depends(get_context)) -> dict:
    limit = max(1, min(200, limit))
    return {"tasks": task_list(ctx.config, ctx.store, ctx.jobs, limit)}


@router.get("/{task_id}")
def get_task(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    detail = detail_payload(ctx.config, ctx.store, ctx.jobs, task_id)
    if not detail:
        raise HTTPException(404, "任务不存在")
    return detail


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    if not ctx.store.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    if not ctx.jobs.is_running(task_id):
        raise HTTPException(409, "任务不在运行中，无需停止")
    if not ctx.jobs.cancel(task_id):
        raise HTTPException(409, "任务不在运行中，无需停止")
    return {"task_id": task_id, "status": "cancelling"}


@router.post("/{task_id}/resume")
def resume_task(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    task = ctx.store.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if ctx.jobs.is_running(task_id):
        raise HTTPException(409, "任务正在运行，不能续跑")
    ctx.store.update_task(task_id, status="pending", progress=0, error=None)
    ctx.jobs.submit(
        source=Path(task.source_path),
        mode=task.mode,
        artifact=task.artifact,
        task_id=task_id,
        # 续跑沿用同一引擎，不重新解释 auto（RULE-082）
        online_engine=engine_kind_from_name(task.engine) if task.mode == "online" else None,
    )
    return {"task_id": task_id, "status": "pending"}


@router.delete("/{task_id}")
def delete_task(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    if not ctx.store.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    if ctx.jobs.is_running(task_id):
        raise HTTPException(409, "正在运行的任务不能删除，先停止再删")
    ctx.store.delete_task(task_id)
    return {"deleted": task_id}
