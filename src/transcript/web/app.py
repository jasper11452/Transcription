"""FastAPI 应用：本机网页入口。

只绑 127.0.0.1、无鉴权（这是刻意选择，见 PRODUCT.md）。
页面骨架是构建产物（React + Vite），后端只做三件额外的事：
把启动状态/任务详情内联进 HTML（首屏不等 /api/status）、提供 JSON 接口、转发 SSE。

密钥铁律：任何响应里都不出现明文——只给掩码尾号（`config.mask` / `mask_preview`）。
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.requests import Request

from .. import audio as audio_mod
from ..config import DEFAULT_SUMMARY_MODEL, OPENROUTER_BASE_DEFAULT, Config, mask_preview
from ..engines.base import (
    ONLINE_ENGINES,
    chunk_max_for,
    engine_catalog,
    engine_kind_from_name,
    online_ready,
    required_key_attrs,
    spec_for,
)
from ..errors import TranscriptError
from ..glossary import (
    is_hot_word_group_line,
    is_hot_word_line,
    parse_glossary,
    parse_glossary_report,
    parse_hot_word_groups,
)
from ..models import Segment
from ..pipeline import estimate_cost
from ..render import parse_srt, to_srt
from ..store import Store, TaskRecord
from ..summary import (
    DEFAULT_SUMMARY_PROMPT,
    MAX_HOT_WORD_CHARS,
    MAX_HOT_WORD_GROUP_CHARS,
    MAX_HOT_WORD_GROUPS,
    MAX_HOT_WORDS,
    MAX_PROMPT_CHARS,
    hot_word_list,
)
from .frontend import DIST_DIR, validate_dist
from .jobs import JobManager

MAX_UPLOAD_BYTES = 2 * 1024**3
OUTPUT_PREVIEW_CHARS = 200_000
_AUDIO_MIME = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}
# 凭据字段 presentation 元数据（字段集合本身从引擎表派生，这里只管中文标签）
_KEY_LABELS = {
    "dashscope_api_key": "百炼 DashScope",
    "openrouter_api_key": "OpenRouter",
}
CONSOLE_DEFAULTS = {"mode": "offline", "artifact": "srt", "language": "zh", "online_engine": "auto"}
MODEL_CACHE_TTL_S = 600
# 本工具写进词表的热词表头（历史版本两种写法）；重写时只清这两行，用户注释不动。
_HOT_WORD_HEADER = (
    "# 热词：直接写正确写法（如 小新）；分组用 `## 组名`。"
    "Agent 总结会按它统一写法，转录时也作为热词提示。"
)
_HOT_WORD_HEADERS = {
    _HOT_WORD_HEADER,
    "# 热词：直接写正确写法（如 小新）。Agent 总结会按它统一写法，转录时也作为热词提示。",
}
_SUMMARY_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}")


def _inline_json(payload: dict) -> str:
    """内联进 <script> 的 JSON：转义 < > & 和行分隔符，杜绝 "</script>" 提前闭合。"""
    raw = json.dumps(payload, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _key_fields(config: Config) -> list[dict]:
    """页面要填的凭据字段。集合来自引擎注册表的 required_keys，不另写第二份。"""
    seen: list[str] = []
    for spec_id in ("dashscope", "openrouter"):  # 展示顺序
        for attr in spec_for(spec_id).required_keys:
            if attr not in seen:
                seen.append(attr)
    fields = []
    for attr in seen:
        value = getattr(config, attr, "")
        fields.append(
            {
                "attr": attr,
                "env": attr.upper(),
                "label": _KEY_LABELS.get(attr, attr),
                "status": config.credential_status().get(attr, ""),
                "masked": mask_preview(value),
                "configured": bool(value),
            }
        )
    return fields


class _HashedStaticFiles(StaticFiles):
    """只有 assets/ 下的文件名带内容哈希，可以 immutable 长缓存。

    dist 根目录的 theme.js / favicon.svg 名字固定，跟着同一个挂载点走，不能一起长缓存，
    否则改一次主题脚本就得让使用者手动清缓存。
    """

    async def get_response(self, path: str, scope):  # noqa: ANN001 - Starlette 签名
        response = await super().get_response(path, scope)
        if response.status_code == 200 and path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


class ArtifactPayload(BaseModel):
    """在线校对提交的字幕全文。时间轴由客户端原样带回，服务端只认正文改动。"""

    srt: str


class TranscriptPayload(BaseModel):
    """文稿全文编辑：文字是唯一真相，时间轴由旧字幕对齐得出。"""

    text: str


MAX_ARTIFACT_CHARS = 5_000_000


_CUE_TERMINATORS = "。！？!?；;"
_MAX_CUE_CHARS = 60


def _split_cues(text: str) -> list[str]:
    """把全文切成字幕句：先按用户换行，再按句末标点，超长的再按标点/中点硬切。"""
    cues: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts: list[str] = []
        buffer = ""
        for index, char in enumerate(line):
            buffer += char
            # 英文句点只在词尾（后接空白或行末）才当句末，避免把 3.5 / v1.2 切开
            english_stop = char == "." and (index + 1 == len(line) or line[index + 1].isspace())
            if char in _CUE_TERMINATORS or english_stop:
                parts.append(buffer.strip())
                buffer = ""
        if buffer.strip():
            parts.append(buffer.strip())
        for part in parts:
            while len(part) > _MAX_CUE_CHARS:
                cut = max(
                    (part.rfind(mark, 0, _MAX_CUE_CHARS) for mark in "，,、：: "),
                    default=-1,
                )
                cut = cut + 1 if cut > 0 else _MAX_CUE_CHARS
                cues.append(part[:cut].strip())
                part = part[cut:].strip()
            if part:
                cues.append(part)
    return cues


def _time_at(segments: list[Segment], offsets: list[int], position: int) -> float:
    """把旧文本里的字符位置换算成时间：落在哪句里就按字符比例在那一句内插值。"""
    for segment, begin, end in zip(segments, offsets, offsets[1:], strict=False):
        if position <= begin:
            return segment.start
        if position < end:
            width = max(1, end - begin)
            return segment.start + (segment.end - segment.start) * (position - begin) / width
    return segments[-1].end


def _boundary_map(source: str, target: str) -> list[int]:
    """source 的每个字符边界 → target 中的位置；用于把文字改动映射回时间轴。"""
    boundary = [0] * (len(source) + 1)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, source, target, autojunk=False
    ).get_opcodes():
        span = max(1, i2 - i1)
        for k in range(i2 - i1 + 1):
            if tag == "equal":
                boundary[i1 + k] = j1 + k
            elif tag == "replace":
                boundary[i1 + k] = j1 + round((j2 - j1) * k / span)
            elif tag == "delete":
                boundary[i1 + k] = j1
        if tag == "insert":
            boundary[i1] = j2
    boundary[len(source)] = len(target)
    for index in range(1, len(boundary)):
        boundary[index] = max(boundary[index], boundary[index - 1])
    return boundary


def _segments_by_old_cues(old: list[Segment], new_text: str) -> list[Segment]:
    """小改动走这里：句子边界沿用原字幕，时间码一格不动。"""
    old_text = "".join(segment.text for segment in old)
    boundary = _boundary_map(old_text, new_text)
    result: list[Segment] = []
    cursor = 0
    for segment in old:
        end = cursor + len(segment.text)
        body = new_text[boundary[cursor]:boundary[end]].replace("\n", "").strip()
        cursor = end
        if not body:
            return []  # 整句被删了，交给按句重切
        result.append(Segment(segment.start, segment.end, body, speaker=segment.speaker))
    tail = new_text[boundary[len(old_text)]:].replace("\n", "").strip()
    if tail:
        last = result[-1]
        result[-1] = Segment(last.start, last.end, last.text + tail, speaker=last.speaker)
    return result


def _segments_by_sentences(old: list[Segment], new_text: str) -> list[Segment]:
    """大改写/删句走这里：先按标点切句，再把每句的起止映射回旧时间轴。"""
    cues = _split_cues(new_text)
    if not cues:
        return []
    old_text = "".join(segment.text for segment in old)
    offsets = [0]
    for segment in old:
        offsets.append(offsets[-1] + len(segment.text))
    boundary = _boundary_map(new_text, old_text)

    result: list[Segment] = []
    position = 0
    last_end = 0.0
    for cue in cues:
        at = new_text.find(cue, position)
        if at < 0:
            at = position
        finish = at + len(cue)
        position = finish
        start = max(last_end, _time_at(old, offsets, boundary[at]))
        end = max(start + 0.2, _time_at(old, offsets, boundary[finish]))
        result.append(Segment(start, end, cue))
        last_end = end
    return result


def _realign_segments(old: list[Segment], new_text: str) -> list[Segment]:
    """全文编辑后的重新对齐。

    改动小（错字、专名）时沿用原字幕句和时间码；改动大到有整句被删或重写时，
    才按标点重新切句，时间落在旧区间内按字符插值，不会整体挪动或压缩。
    """
    old_text = "".join(segment.text for segment in old)
    similarity = difflib.SequenceMatcher(None, old_text, new_text, autojunk=False).ratio()
    if similarity >= 0.85:
        kept = _segments_by_old_cues(old, new_text)
        if kept:
            return kept
    return _segments_by_sentences(old, new_text)


def _write_pair(srt_path: Path, srt_text: str, txt_path: Path, txt_text: str) -> None:
    """两个产物一起落盘：先把两份临时文件都写好，再各自原子替换。

    跨文件做不到真原子；这样把失败窗口压到两次 rename 之间，任何一次写入失败时磁盘完全不动。
    """
    srt_tmp = srt_path.with_name(srt_path.name + ".tmp")
    txt_tmp = txt_path.with_name(txt_path.name + ".tmp")
    srt_tmp.write_text(srt_text, encoding="utf-8")
    txt_tmp.write_text(txt_text, encoding="utf-8")
    srt_tmp.replace(srt_path)
    txt_tmp.replace(txt_path)


def _sync_txt(old_txt: str, old: list, new: list) -> str:
    """把改动按顺序替换进 txt，保住引擎的段落结构。

    用游标而不是 str.replace：两句正文完全一样时，replace 会把改动落到前一句上。
    替换不上（原文被别的工具改过、或含说话人合并块）就按行重建：内容优先，
    两个产物仍然逐字一致——这是硬要求。
    """
    # 注释块在最前面；游标从正文开始，免得把改动落进 # 留痕里
    lines = old_txt.splitlines(keepends=True)
    head = 0
    while head < len(lines) and lines[head].startswith("# "):
        head += 1
    prefix = "".join(lines[:head])
    text = "".join(lines[head:])
    cursor = 0
    for before, after in zip(old, new, strict=True):
        index = text.find(before.text, cursor)
        if index < 0:
            comments = [line for line in old_txt.splitlines() if line.startswith("# ")]
            return "\n".join(comments + [segment.text for segment in new]) + "\n"
        if before.text != after.text:
            text = text[:index] + after.text + text[index + len(before.text):]
        cursor = index + len(after.text)
    return prefix + text


def create_app(config: Config, store: Store, jobs: JobManager | None = None) -> FastAPI:
    manager = jobs or JobManager(config, store)
    app = FastAPI(title="Transcript", version="0.1.0")
    app.state.config = config
    app.state.store = store
    app.state.jobs = manager

    validate_dist(DIST_DIR)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        """统一错误格式 {"error": ...}——前端只认这个字段。"""
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    # ---------- 页面：构建产物 + 内联启动状态 ----------

    def _serve_page(entry: str, boot: dict) -> FileResponse:
        html = (DIST_DIR / entry).read_text(encoding="utf-8")
        snippet = f"<script>window.__BOOT__={_inline_json(boot)};</script>"
        if "</head>" in html:
            html = html.replace("</head>", snippet + "</head>", 1)
        else:  # pragma: no cover - 构建产物一定有 </head>
            html = snippet + html
        return Response(content=html, media_type="text/html")

    def _status_payload() -> dict:
        return {
            "online_ready": online_ready(config),
            "online_engines": engine_catalog(config),
            "credentials": config.credential_status(),
            "key_fields": _key_fields(config),
            "defaults": CONSOLE_DEFAULTS,
            "stats": store.stats(),
        }

    def _task_payload(t: TaskRecord) -> dict:
        running = manager.is_running(t.id)
        content = store.get_summary(t.id).get("content") or {}
        title = (content.get("title") or "").strip() or Path(t.source_path).name
        return {
            "id": t.id,
            "name": t.name,
            "title": title,
            "source_name": Path(t.source_path).name,
            "source_path": t.source_path,
            "mode": t.mode,
            "artifact": t.artifact,
            "status": t.status,
            "progress": t.progress,
            "engine": t.engine,
            "duration_s": t.duration_s,
            "audio_seconds": t.audio_seconds,
            "cost_usd": t.cost_usd,
            "chars": t.chars,
            "out_dir": t.out_dir,
            "txt_path": t.txt_path,
            "srt_path": t.srt_path,
            "raw_path": t.raw_path,
            "error": t.error,
            "started_at": t.started_at,
            "created_at": t.created_at,
            "is_terminal": t.is_terminal,
            "running": running,
            "cancelling": manager.is_cancelling(t.id),
            "resumable": (not running) and t.status in {"pending", "running", "failed"},
            "txt_exists": bool(t.txt_path) and Path(t.txt_path).is_file(),
            "srt_exists": bool(t.srt_path) and Path(t.srt_path).is_file(),
            "src_exists": Path(t.source_path).is_file(),
        }

    def _detail_payload(task_id: int) -> dict | None:
        t = store.get_task(task_id)
        if not t:
            return None
        chunks = [c.as_payload() for c in store.chunks_for(task_id)]
        tp = _task_payload(t)
        return {
            "task": tp,
            "chunks": chunks,
            "running": tp["running"],
            "cancelling": tp["cancelling"],
            "resumable": tp["resumable"],
        }

    def _task_list(limit: int = 50) -> list[dict]:
        return [_task_payload(t) for t in store.list_tasks(limit=limit)]

    @app.get("/")
    def index():
        # 侧栏任务表跟着 HTML 一起到：否则进页后要等一次 /api/tasks 往返，
        # 期间侧栏是「加载中…」，列表一到整栏换掉。
        return _serve_page(
            "index.html",
            {"status": _status_payload(), "task": None, "tasks": _task_list()},
        )

    @app.get("/t/{task_id}")
    def task_page(task_id: str):
        """任务页。号码不合法或任务不存在时也回页面（boot.task=null），由前端提示。"""
        boot_task = None
        if task_id.isdigit():
            boot_task = _detail_payload(int(task_id))
        return _serve_page(
            "task.html",
            {"status": _status_payload(), "task": boot_task, "tasks": _task_list()},
        )

    @app.get("/settings")
    def settings_page():
        """全局设置页：与控制台同一套外壳，复用详情页的静态产物。"""
        return _serve_page(
            "task.html",
            {"status": _status_payload(), "task": None, "tasks": _task_list()},
        )

    app.mount("/static/dist", _HashedStaticFiles(directory=DIST_DIR), name="static")

    # ---------- 状态与预估 ----------

    @app.get("/api/status")
    def status() -> dict:
        return _status_payload()

    @app.post("/api/estimate")
    def estimate(
        source_path: str = Form(""),
        mode: str = Form("online"),
        artifact: str = Form("srt"),
        online_engine: str = Form("auto"),
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
                config, mode=mode, artifact=artifact, online_engine=online_engine
            ),
        }

    # ---------- 建任务 ----------

    @app.post("/api/tasks")
    async def create_task(
        source_path: str = Form(""),
        file: UploadFile = File(None),
        mode: str = Form("offline"),
        artifact: str = Form("srt"),
        language: str = Form("zh"),
        online_engine: str = Form("auto"),
    ) -> dict:
        if mode not in ("offline", "online"):
            raise HTTPException(400, f"mode 只能是 offline / online，收到：{mode}")
        if artifact not in ("txt", "srt"):
            raise HTTPException(400, f"artifact 只能是 txt / srt，收到：{artifact}")
        if online_engine not in ONLINE_ENGINES:
            raise HTTPException(
                400, f"online_engine 只能是 {', '.join(ONLINE_ENGINES)}，收到：{online_engine}"
            )

        if file:
            upload_dir = config.state_db.parent / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            safe_name = Path(file.filename or "audio").name
            target = upload_dir / f"{uuid.uuid4().hex[:8]}-{safe_name}"
            size = 0
            try:
                with target.open("wb") as f:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(400, "文件超过 2GB 上限")
                        f.write(chunk)
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
                config, mode=mode, artifact=artifact, online_engine=online_engine
            )
            if not getattr(config, attr, "")
        ]
        if missing:
            envs = "、".join(a.upper() for a in missing)
            raise HTTPException(
                400,
                f"在线模式缺少凭据：{envs}。可在页面「在线密钥」里填写，"
                f"或写入 {config.config_path}",
            )

        task_id = store.create_task(
            name=source.name,
            source_path=str(source),
            mode=mode,
            artifact=artifact,
            engine=online_engine if mode == "online" else None,
        )
        manager.submit(
            source=source,
            mode=mode,
            artifact=artifact,
            language=language,
            task_id=task_id,
            online_engine=online_engine if mode == "online" else None,
        )
        return {"task_id": task_id, "status": "pending"}

    # ---------- 任务列表 / 详情 / 生命周期 ----------

    @app.get("/api/tasks")
    def list_tasks(limit: int = 50) -> dict:
        limit = max(1, min(200, limit))
        return {"tasks": _task_list(limit)}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int) -> dict:
        detail = _detail_payload(task_id)
        if not detail:
            raise HTTPException(404, "任务不存在")
        return detail

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel_task(task_id: int) -> dict:
        if not store.get_task(task_id):
            raise HTTPException(404, "任务不存在")
        if not manager.is_running(task_id):
            raise HTTPException(409, "任务不在运行中，无需停止")
        found = manager.cancel(task_id)
        if not found:
            raise HTTPException(409, "任务不在运行中，无需停止")
        return {"task_id": task_id, "status": "cancelling"}

    @app.post("/api/tasks/{task_id}/resume")
    def resume_task(task_id: int) -> dict:
        t = store.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        if manager.is_running(task_id):
            raise HTTPException(409, "任务正在运行，不能续跑")
        store.update_task(task_id, status="pending", progress=0, error=None)
        manager.submit(
            source=Path(t.source_path),
            mode=t.mode,
            artifact=t.artifact,
            task_id=task_id,
            # 续跑沿用同一引擎，不重新解释 auto（engine_kind_from_name 注释）
            online_engine=engine_kind_from_name(t.engine) if t.mode == "online" else None,
        )
        return {"task_id": task_id, "status": "pending"}

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: int) -> dict:
        if not store.get_task(task_id):
            raise HTTPException(404, "任务不存在")
        if manager.is_running(task_id):
            raise HTTPException(409, "正在运行的任务不能删除，先停止再删")
        store.delete_task(task_id)
        return {"deleted": task_id}

    def _hot_word_groups_payload() -> list[dict]:
        path = config.glossary_path
        if not path.is_file():
            return []
        return [
            {"name": group.name, "words": list(group.words)}
            for group in parse_hot_word_groups(path.read_text(encoding="utf-8"))
        ]

    def _summary_settings_payload() -> dict:
        return {
            "model": config.summary_model,
            "default_model": DEFAULT_SUMMARY_MODEL,
            "base_url": config.openrouter_base,
            "default_base_url": OPENROUTER_BASE_DEFAULT,
            "prompt": config.summary_prompt.strip() or DEFAULT_SUMMARY_PROMPT,
            "default_prompt": DEFAULT_SUMMARY_PROMPT,
            "custom_prompt": bool(config.summary_prompt.strip()),
            "max_prompt_chars": MAX_PROMPT_CHARS,
            "config_path": str(config.config_path),
            "prompt_path": str(config.summary_prompt_path),
            "hot_words": hot_word_list(config),
            "hot_word_groups": _hot_word_groups_payload(),
            "max_hot_words": MAX_HOT_WORDS,
            "max_hot_word_chars": MAX_HOT_WORD_CHARS,
            "max_hot_word_groups": MAX_HOT_WORD_GROUPS,
            "max_hot_word_group_chars": MAX_HOT_WORD_GROUP_CHARS,
            "glossary_path": str(config.glossary_path),
        }

    def _write_summary_prompt(prompt: str) -> None:
        path = config.summary_prompt_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(prompt, encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def _write_hot_word_groups(groups: list[dict]) -> None:
        """只改热词块：`错词 -> 正确词` 规则与用户注释原样保留。"""
        path = config.glossary_path
        existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        kept = [
            line
            for line in existing
            if not is_hot_word_line(line)
            and not is_hot_word_group_line(line)
            # 只清掉本工具写过的那几行表头；用户自己写的“# 热词：…”是注释，不能吃。
            and line.strip() not in _HOT_WORD_HEADERS
        ]
        while kept and not kept[-1].strip():
            kept.pop()
        block: list[str] = []
        # 未分组词条必须写在所有 `## 组名` 之前；否则解析时会被算进最后一组。
        ordered = [group for group in groups if not group["name"]] + [
            group for group in groups if group["name"]
        ]
        for group in ordered:
            name, words = group["name"], group["words"]
            if not name and not words:
                continue
            if block:
                block.append("")
            if name:
                block.append(f"## {name}")
            else:
                block.append(_HOT_WORD_HEADER)
            block.extend(words)
        lines = kept + ([""] if kept and block else []) + block
        text = ("\n".join(lines).rstrip("\n") + "\n") if lines else ""
        # 词表里有用户手写的替换规则：写一半崩掉会把规则全弄丢，跟 config.env 一样原子替换。
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def _clean_hot_word_groups(raw: object) -> list[dict]:
        if not isinstance(raw, list):
            raise HTTPException(400, "热词分组必须是列表")
        cleaned: list[dict] = []
        group_names: set[str] = set()
        seen_words: set[str] = set()
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"name", "words"}:
                raise HTTPException(400, "每个热词分组都需要 name 和 words")
            name, words = item["name"], item["words"]
            if not isinstance(name, str):
                raise HTTPException(400, "热词分组名必须是字符串")
            if not isinstance(words, list):
                raise HTTPException(400, "热词分组的 words 必须是列表")
            name = name.strip()
            # 设置页默认带一个「未分组」空行：它不携带任何内容，不该占用分组名额。
            if not name and not words:
                continue
            if len(name) > MAX_HOT_WORD_GROUP_CHARS:
                raise HTTPException(400, f"热词分组名不能超过 {MAX_HOT_WORD_GROUP_CHARS} 个字")
            if any(ch == "#" or ord(ch) < 32 for ch in name):
                raise HTTPException(400, "热词分组名不能包含 # 或控制字符")
            if name in group_names:
                raise HTTPException(400, f"热词分组“{name}”重复")
            clean_words: list[str] = []
            for word in words:
                if not isinstance(word, str):
                    raise HTTPException(400, "热词必须是字符串")
                value = word.strip()
                if not value or value in seen_words:
                    continue
                if (
                    len(value) > MAX_HOT_WORD_CHARS
                    or any(ch.isspace() for ch in value)
                    or "=" in value
                ):
                    raise HTTPException(
                        400, f"热词“{value}”无效：不能含空白或 =，最多 {MAX_HOT_WORD_CHARS} 字"
                    )
                seen_words.add(value)
                clean_words.append(value)
            group_names.add(name)
            cleaned.append({"name": name, "words": clean_words})
        if len(cleaned) > MAX_HOT_WORD_GROUPS:
            raise HTTPException(400, f"热词分组最多 {MAX_HOT_WORD_GROUPS} 个")
        if len(seen_words) > MAX_HOT_WORDS:
            raise HTTPException(400, f"热词最多 {MAX_HOT_WORDS} 个")
        return cleaned

    @app.get("/api/summary-settings")
    def get_summary_settings() -> dict:
        return _summary_settings_payload()

    @app.put("/api/summary-settings")
    async def put_summary_settings(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "请求体必须是 JSON") from exc
        required = {"model", "base_url", "prompt"}
        allowed = required | {"hot_words", "hot_word_groups"}
        if not isinstance(body, dict) or not required <= set(body) or set(body) - allowed:
            raise HTTPException(
                400, "需要提供 model、base_url、prompt，可选 hot_words、hot_word_groups"
            )

        model, base_url, prompt = body["model"], body["base_url"], body["prompt"]
        hot_words = body.get("hot_words")
        raw_groups = body.get("hot_word_groups")
        if hot_words is not None and raw_groups is not None:
            raise HTTPException(400, "hot_words 与 hot_word_groups 只能提供一个")
        # 密钥只走 POST /api/credentials：两个写入口必然会在某天分叉。
        if not isinstance(model, str):
            raise HTTPException(400, "模型 ID 必须是字符串")
        model = model.strip()
        if not _SUMMARY_MODEL_RE.fullmatch(model):
            raise HTTPException(400, "模型 ID 格式无效，请填写服务提供的模型 ID（不含空白）")
        if not isinstance(base_url, str):
            raise HTTPException(400, "Base URL 必须是字符串")
        base_url = base_url.strip().rstrip("/")
        if any(ch.isspace() for ch in base_url) or len(base_url) > 500:
            raise HTTPException(400, "Base URL 格式无效")
        try:
            parsed_base_url = urlsplit(base_url)
            port = parsed_base_url.port
            valid_base_url = (
                parsed_base_url.scheme in {"http", "https"}
                and bool(parsed_base_url.hostname)
                and (port is None or 1 <= port <= 65535)
                and not parsed_base_url.username
                and not parsed_base_url.password
                and not parsed_base_url.query
                and not parsed_base_url.fragment
            )
        except ValueError:
            valid_base_url = False
        if not valid_base_url:
            raise HTTPException(400, "Base URL 必须是无凭据、无查询参数的 HTTP(S) 地址")
        if not isinstance(prompt, str):
            raise HTTPException(400, "提示词必须是字符串")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise HTTPException(400, f"提示词不能超过 {MAX_PROMPT_CHARS} 个字符")
        if "\x00" in prompt:
            raise HTTPException(400, "提示词包含不支持的空字符")

        groups: list[dict] | None = None
        if raw_groups is not None:
            groups = _clean_hot_word_groups(raw_groups)
        elif hot_words is not None:
            if not isinstance(hot_words, list) or len(hot_words) > MAX_HOT_WORDS:
                raise HTTPException(400, f"热词必须是最多 {MAX_HOT_WORDS} 个的列表")
            cleaned: list[str] = []
            for word in hot_words:
                if not isinstance(word, str):
                    raise HTTPException(400, "热词必须是字符串")
                value = word.strip()
                if not value:
                    continue
                if (
                    len(value) > MAX_HOT_WORD_CHARS
                    or any(ch.isspace() for ch in value)
                    or "=" in value
                ):
                    raise HTTPException(
                        400, f"热词“{value}”无效：不能含空白或 =，最多 {MAX_HOT_WORD_CHARS} 字"
                    )
                if value not in cleaned:
                    cleaned.append(value)
            groups = [{"name": "", "words": cleaned}]

        updates = {"SUMMARY_MODEL": model, "OPENROUTER_BASE": base_url}
        try:
            _write_config_file(updates)
            _write_summary_prompt(prompt)
            if groups is not None:
                _write_hot_word_groups(groups)
        except OSError as exc:
            raise HTTPException(500, "本机设置保存失败，请检查配置目录权限。") from exc
        config.summary_model = model
        config.openrouter_base = base_url
        config.summary_prompt = prompt
        model_cache.clear()
        return _summary_settings_payload()

    # 模型清单按 Base URL 缓存，避免每次打开设置都打上游接口。
    model_cache: dict[str, tuple[float, list[dict], str | None]] = {}

    @app.get("/api/summary-models")
    def list_summary_models(refresh: bool = False) -> dict:
        """OpenRouter 模型清单，供设置页挑选。只请求已配置的 Base URL。"""
        if not config.openrouter_api_key:
            return {
                "models": [],
                "error": "尚未配置 API Key 密钥，请先保存连接设置。",
                "cached": False,
            }
        cached = model_cache.get(config.openrouter_base)
        if not refresh and cached and time.monotonic() - cached[0] < MODEL_CACHE_TTL_S:
            return {"models": cached[1], "error": cached[2], "cached": True}
        try:
            response = httpx.get(
                f"{config.openrouter_base}/models",
                headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json().get("data")
        except (httpx.HTTPError, ValueError):
            # 拉不到不阻断手填：页面照常可以输入模型 ID。
            message = "模型清单获取失败，仍可手动填写模型 ID。"
            model_cache[config.openrouter_base] = (time.monotonic(), [], message)
            return {"models": [], "error": message, "cached": False}
        models = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            pricing = item.get("pricing") or {}
            try:
                price = float(pricing.get("prompt")) * 1_000_000
            except (TypeError, ValueError):
                price = None
            models.append(
                {
                    "id": str(item["id"]),
                    "name": str(item.get("name") or item["id"]),
                    "context_length": item.get("context_length"),
                    "reasoning": "reasoning" in (item.get("supported_parameters") or []),
                    "price_per_million_prompt": price,
                }
            )
        models.sort(key=lambda m: m["id"])
        model_cache[config.openrouter_base] = (time.monotonic(), models, None)
        return {"models": models, "error": None, "cached": False}

    # ---------- Agent 总结：每个任务显式授权，独立于转录状态 ----------

    @app.get("/api/tasks/{task_id}/summary")
    def get_summary(task_id: int, since: int = 0, reasoning_since: int = 0) -> dict:
        if not store.get_task(task_id):
            raise HTTPException(404, "任务不存在")
        return manager.summaries.payload(task_id, since=since, reasoning_since=reasoning_since)

    @app.post("/api/tasks/{task_id}/summary")
    def enable_summary(task_id: int) -> dict:
        if not store.get_task(task_id):
            raise HTTPException(404, "任务不存在")
        try:
            return manager.summaries.enable(task_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ---------- 产物与音频 ----------

    def output_path(task_id: int, kind: str) -> Path:
        t = store.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        attr = "txt_path" if kind == "txt" else "srt_path"
        path = getattr(t, attr, None)
        if kind not in ("txt", "srt") or not path:
            raise HTTPException(404, f"这个任务没有 {kind} 产物")
        p = Path(path)
        if not p.is_file():
            raise HTTPException(404, f"{kind} 产物已被移动或删除：{path}")
        return p

    @app.get("/api/tasks/{task_id}/output")
    def get_output(task_id: int, kind: str = "txt") -> dict:
        p = output_path(task_id, kind)
        with p.open(encoding="utf-8", errors="replace") as f:
            content = f.read(OUTPUT_PREVIEW_CHARS + 1)
        truncated = len(content) > OUTPUT_PREVIEW_CHARS
        return {"content": content[:OUTPUT_PREVIEW_CHARS], "path": str(p), "truncated": truncated}

    @app.put("/api/tasks/{task_id}/artifacts")
    def put_artifacts(task_id: int, payload: ArtifactPayload) -> dict:
        """保存校对结果：同时重写 .srt 与 .txt，两者保持一致。"""
        t = store.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        if not (t.srt_path and t.txt_path):
            raise HTTPException(400, "这个任务没有成对的字幕与文稿")
        srt_path, txt_path = Path(t.srt_path), Path(t.txt_path)
        if not srt_path.is_file() or not txt_path.is_file():
            raise HTTPException(404, "产物已被移动或删除，请重新转录或手动放回")
        if len(payload.srt) > MAX_ARTIFACT_CHARS:
            raise HTTPException(400, "字幕内容过大")
        old_srt = srt_path.read_text(encoding="utf-8")
        old_txt = txt_path.read_text(encoding="utf-8")
        old_segments = parse_srt(old_srt)
        new_segments = parse_srt(payload.srt)
        if not new_segments:
            raise HTTPException(400, "没有可保存的字幕行，请检查格式")
        if len(new_segments) != len(old_segments):
            raise HTTPException(400, "字幕行数与磁盘上的不一致，请刷新页面后重试")
        for old, new in zip(old_segments, new_segments, strict=True):
            if not new.text.strip():
                raise HTTPException(400, "字幕正文不能为空")
            if abs(old.start - new.start) > 0.001 or abs(old.end - new.end) > 0.001:
                raise HTTPException(400, "时间轴不能在页面里修改")
        comments = [line[2:].strip() for line in old_srt.splitlines() if line.startswith("# ")]
        srt_text = to_srt(new_segments, comment_lines=comments or None)
        txt_text = _sync_txt(old_txt, old_segments, new_segments)
        _write_pair(srt_path, srt_text, txt_path, txt_text)
        store.update_task(task_id, chars=sum(len(segment.text.strip()) for segment in new_segments))
        return {"srt": srt_text, "txt": txt_text, "lines": len(new_segments)}

    @app.put("/api/tasks/{task_id}/transcript")
    def put_transcript(task_id: int, payload: TranscriptPayload) -> dict:
        """保存全文编辑的文稿：txt 原样落盘，srt 按字符对齐回原时间轴。"""
        t = store.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        if not (t.srt_path and t.txt_path):
            raise HTTPException(400, "这个任务没有成对的字幕与文稿")
        srt_path, txt_path = Path(t.srt_path), Path(t.txt_path)
        if not srt_path.is_file() or not txt_path.is_file():
            raise HTTPException(404, "产物已被移动或删除，请重新转录或手动放回")
        text = payload.text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise HTTPException(400, "文稿不能为空")
        if len(text) > MAX_ARTIFACT_CHARS:
            raise HTTPException(400, "文稿内容过大")
        old_srt = srt_path.read_text(encoding="utf-8")
        old_segments = parse_srt(old_srt)
        if not old_segments:
            raise HTTPException(400, "字幕文件无法解析，请先在字幕视图里保存一次")
        new_segments = _realign_segments(old_segments, text.strip())
        if not new_segments:
            raise HTTPException(400, "改后的文稿没有可对齐的文字，请检查内容")
        comments = [line[2:].strip() for line in old_srt.splitlines() if line.startswith("# ")]
        srt_text = to_srt(new_segments, comment_lines=comments or None)
        txt_text = text.strip() + "\n"
        _write_pair(srt_path, srt_text, txt_path, txt_text)
        store.update_task(task_id, chars=sum(len(segment.text.strip()) for segment in new_segments))
        return {"srt": srt_text, "txt": txt_text, "lines": len(new_segments)}

    @app.get("/api/tasks/{task_id}/output/file")
    def get_output_file(task_id: int, kind: str = "txt", download: bool = False):
        """完整产物；与受限 JSON 预览分离，下载保持原文件字节。"""
        p = output_path(task_id, kind)
        return FileResponse(
            p,
            media_type="text/plain; charset=utf-8",
            filename=p.name if download else None,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/tasks/{task_id}/audio")
    def get_audio(task_id: int):
        t = store.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        src = Path(t.source_path)
        if not src.is_file():
            raise HTTPException(404, f"原文件已被移动或删除：{t.source_path}")
        return FileResponse(
            src, media_type=_AUDIO_MIME.get(src.suffix.lower(), "application/octet-stream")
        )

    @app.post("/api/reveal")
    def reveal(path: str = Form(...)) -> dict:
        target = Path(path).expanduser()
        if not target.exists():
            raise HTTPException(404, f"路径不存在：{path}")
        subprocess.run(["open", "-R", str(target)], check=False)
        return {"ok": True}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)) -> dict:
        upload_dir = config.state_db.parent / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "audio").name
        target = upload_dir / f"{uuid.uuid4().hex[:8]}-{safe_name}"
        size = 0
        with target.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                f.write(chunk)
        return {"path": str(target), "bytes": size}

    # ---------- 热词词表 ----------

    @app.get("/api/glossary")
    def get_glossary() -> dict:
        text = ""
        if config.glossary_path.is_file():
            text = config.glossary_path.read_text(encoding="utf-8")
        rules = [{"wrong": r.wrong, "right": r.right} for r in parse_glossary(text)]
        return {"text": text, "rules": rules}

    @app.put("/api/glossary")
    def put_glossary(text: str = Form("")) -> dict:
        rules, issues = parse_glossary_report(text)
        if issues:
            raise HTTPException(400, "；".join(i.describe() for i in issues))
        config.glossary_path.parent.mkdir(parents=True, exist_ok=True)
        config.glossary_path.write_text(text, encoding="utf-8")
        return {"rule_count": len(rules)}

    # ---------- 凭据 ----------

    def _write_config_file(updates: dict[str, str]) -> None:
        """把 ENV=值 写进配置文件。保留用户自己的行与注释；600 权限；原子替换。"""
        cfg_path = config.config_path
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        lines = cfg_path.read_text(encoding="utf-8").splitlines() if cfg_path.exists() else []
        for env, value in updates.items():
            prefix = f"{env}="
            for i, line in enumerate(lines):
                if line.strip().startswith(prefix):
                    lines[i] = f"{prefix}{value}"
                    break
            else:
                lines.append(f"{prefix}{value}")
        tmp = cfg_path.with_name(cfg_path.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, cfg_path)
        os.chmod(cfg_path, 0o600)

    @app.post("/api/credentials")
    async def save_credentials(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "请求体必须是 JSON") from exc
        # 这是密钥唯一的写入口：形状不对就报 400，不能让它走到 .strip() 变成 500。
        if not isinstance(body, dict):
            raise HTTPException(400, "请求体必须是 JSON 对象")
        keys = body.get("keys") or {}
        clear = body.get("clear") or []
        if not isinstance(keys, dict) or not isinstance(clear, list):
            raise HTTPException(400, "keys 必须是对象，clear 必须是数组")

        allowed = {f["attr"] for f in _key_fields(config)}
        if any(not isinstance(attr, str) for attr in clear):
            raise HTTPException(400, "clear 里只能放字段名")
        unknown = (set(keys) | set(clear)) - allowed
        if unknown:
            raise HTTPException(400, f"未知的凭据字段：{', '.join(sorted(unknown))}")

        updates: dict[str, str] = {}
        for attr, value in keys.items():
            if not isinstance(value, str):
                raise HTTPException(400, f"{attr} 的值必须是字符串")
            value = value.strip()
            if not value:
                continue  # 留空 = 保持现状，避免"点一下保存就把密钥清了"
            if any(ch.isspace() for ch in value) or "=" in value or len(value) > 512:
                raise HTTPException(400, f"{attr} 的值含有非法字符（空格、换行或 =）")
            updates[attr.upper()] = value
        for attr in clear:
            updates[attr.upper()] = ""

        # 全部校验通过才落盘
        if updates:
            _write_config_file(updates)
        for attr, value in keys.items():
            value = value.strip()
            if value:
                setattr(config, attr, value)
        for attr in clear:
            setattr(config, attr, "")

        # 模型清单缓存是按 Base URL 存的：换了 OpenRouter 密钥就得作废，否则
        # 旧密钥拉到的清单（包括失败结果）会继续挂 10 分钟。
        if updates.keys() & {"OPENROUTER_API_KEY"}:
            model_cache.clear()

        return {
            "credentials": config.credential_status(),
            "key_fields": _key_fields(config),
            "online_engines": engine_catalog(config),
        }

    @app.get("/api/tasks/{task_id}/events")
    def task_events(task_id: int):
        return StreamingResponse(manager.stream(task_id), media_type="text/event-stream")

    return app
