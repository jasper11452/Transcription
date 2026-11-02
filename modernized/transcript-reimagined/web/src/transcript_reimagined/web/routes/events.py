"""SSE：把 scheduler 的事件流原样转发给浏览器。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..dependencies import AppContext, get_context

router = APIRouter(prefix="/api/tasks")


@router.get("/{task_id}/events")
def task_events(task_id: int, ctx: AppContext = Depends(get_context)):
    if not ctx.store.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    return StreamingResponse(
        ctx.jobs.stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
