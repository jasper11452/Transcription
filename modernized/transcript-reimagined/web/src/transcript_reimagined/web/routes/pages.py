"""页面路由：构建产物 + 内联启动状态。

首屏不等 `/api/status`：状态、任务列表、当前任务详情随 HTML 一起到。
`__BOOT__` 的 JSON 必须转义 `< > &` 与行分隔符，杜绝 `</script>` 提前闭合（RULE-067）。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..dependencies import AppContext, get_context
from ..payloads import detail_payload, status_payload, task_list

router = APIRouter()


def inline_json(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def serve_page(dist_dir: Path, entry: str, boot: dict) -> Response:
    html = (dist_dir / entry).read_text(encoding="utf-8")
    snippet = f"<script>window.__BOOT__={inline_json(boot)};</script>"
    html = (
        html.replace("</head>", snippet + "</head>", 1)
        if "</head>" in html
        else snippet + html  # pragma: no cover - 构建产物一定有 </head>
    )
    return Response(content=html, media_type="text/html")


def _boot(ctx: AppContext, *, task: dict | None) -> dict:
    return {
        "status": status_payload(ctx.config, ctx.store),
        "task": task,
        "tasks": task_list(ctx.config, ctx.store, ctx.jobs),
    }


@router.get("/")
def index(ctx: AppContext = Depends(get_context)):
    return serve_page(ctx.dist_dir, "index.html", _boot(ctx, task=None))


@router.get("/t/{task_id}")
def task_page(task_id: str, ctx: AppContext = Depends(get_context)):
    """号码不合法或任务不存在时也回页面（boot.task=null），由前端提示。"""
    task = None
    if task_id.isdigit():
        task = detail_payload(ctx.config, ctx.store, ctx.jobs, int(task_id))
    return serve_page(ctx.dist_dir, "task.html", _boot(ctx, task=task))
