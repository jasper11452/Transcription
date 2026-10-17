"""Agent 总结资源：读取状态、显式开启。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import AppContext, get_context

router = APIRouter(prefix="/api/tasks")


@router.get("/{task_id}/summary")
def get_summary(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    if not ctx.store.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    return ctx.jobs.summaries.payload(task_id)


@router.post("/{task_id}/summary")
def enable_summary(task_id: int, ctx: AppContext = Depends(get_context)) -> dict:
    if not ctx.store.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    try:
        return ctx.jobs.summaries.enable(task_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
