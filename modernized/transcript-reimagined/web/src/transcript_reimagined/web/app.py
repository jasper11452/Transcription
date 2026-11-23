"""FastAPI 应用：本机网页入口。

只绑 127.0.0.1、无鉴权（刻意选择），但**必须有来源校验**（NFR-6）。
页面骨架是构建产物（React + Vite），后端只多做三件事：把启动状态/任务详情内联进
HTML、提供 JSON 接口、转发 SSE。

旧层是单个 635 行闭包；新层的每个资源是一个独立 router（`routes/`），依赖通过
`AppContext` 显式注入。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from transcript_reimagined.config import Config
from transcript_reimagined.orchestrate import JobManager
from transcript_reimagined.state import Store

from .dependencies import AppContext
from .frontend import DIST_DIR, validate_dist
from .logging import configure_logging, log_failure, request_id_var
from .routes import events, outputs, pages, settings, status, summaries, tasks

DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _host_name(value: str) -> str:
    """`127.0.0.1:8765` → `127.0.0.1`（不处理 IPv6，本工具只绑本机）。"""
    return value.rsplit(":", 1)[0].strip().lower() if value.count(":") == 1 else value.strip().lower()


def create_app(
    config: Config,
    store: Store,
    jobs: JobManager | None = None,
    *,
    dist_dir: Path | None = None,
    allowed_hosts: frozenset[str] | None = None,
    validate_frontend: bool = True,
) -> FastAPI:
    configure_logging()
    manager = jobs or JobManager(config, store)
    dist = Path(dist_dir) if dist_dir else DIST_DIR
    hosts = frozenset(allowed_hosts or DEFAULT_ALLOWED_HOSTS)
    if validate_frontend:
        validate_dist(dist)

    app = FastAPI(title="Transcript", version="0.1.0")
    app.state.ctx = AppContext(
        config=config, store=store, jobs=manager, dist_dir=dist, allowed_hosts=hosts
    )
    app.state.dist_dir = dist

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        """Host 白名单 + 非 GET 请求的同源校验（NFR-6）。

        浏览器跨站 POST 一定会带 `Origin` 或 `Sec-Fetch-Site`；两者都缺失的请求
        来自非浏览器客户端（curl/脚本），放行不会留下 CSRF 缺口。
        """
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        request_id_var.set(request_id)

        host_header = request.headers.get("host", "")
        if _host_name(host_header) not in hosts:
            log_failure(
                f"拒绝 Host={host_header!r}", code="host_rejected", level=logging.WARNING
            )
            return JSONResponse(
                status_code=400,
                content={"error": f"Host 不在白名单：{host_header}"},
                headers={"X-Request-ID": request_id},
            )

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            site = request.headers.get("sec-fetch-site")
            if site is not None and site not in {"same-origin", "none"}:
                log_failure(f"拒绝 Sec-Fetch-Site={site}", code="origin_rejected")
                return JSONResponse(
                    status_code=403,
                    content={"error": "跨站请求被拒绝"},
                    headers={"X-Request-ID": request_id},
                )
            origin = request.headers.get("origin")
            if origin is not None:
                parsed = urlsplit(origin)
                same_host = parsed.hostname is not None and parsed.hostname.lower() == _host_name(
                    host_header
                )
                if parsed.scheme not in {"http", "https"} or not same_host:
                    log_failure(f"拒绝 Origin={origin!r}", code="origin_rejected")
                    return JSONResponse(
                        status_code=403,
                        content={"error": "跨站请求被拒绝"},
                        headers={"X-Request-ID": request_id},
                    )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        """统一错误格式 {"error": ...}，并把失败写进结构化日志。"""
        log_failure(str(exc.detail), code=f"http_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail)},
            headers={"X-Request-ID": getattr(request.state, "request_id", "-")},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        log_failure(str(exc), code="request_validation", level=logging.WARNING)
        return JSONResponse(
            status_code=400,
            content={"error": "请求参数不合法"},
            headers={"X-Request-ID": getattr(request.state, "request_id", "-")},
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        log_failure(
            f"{type(exc).__name__}: {exc}", code="internal_error", level=logging.ERROR
        )
        return JSONResponse(
            status_code=500,
            content={"error": "内部错误"},
            headers={"X-Request-ID": getattr(request.state, "request_id", "-")},
        )

    for module in (pages, status, tasks, outputs, settings, summaries, events):
        app.include_router(module.router)

    app.mount("/static/dist", StaticFiles(directory=dist), name="static")
    return app
