"""HTTP 响应体装配：把领域对象变成页面/API 的 payload。

这里不碰 FastAPI（除了在路由层被调用），只做纯变换；测试可以脱离 TestClient 直接断言。
"""

from __future__ import annotations

from pathlib import Path

from transcript_reimagined.config import Config, mask_preview
from transcript_reimagined.engines import engine_catalog, online_ready, spec_for
from transcript_reimagined.orchestrate import JobManager
from transcript_reimagined.state import Store, TaskRecord, task_flags
from transcript_reimagined.summarize import (
    DEFAULT_SUMMARY_PROMPT,
    MAX_HOT_WORD_CHARS,
    MAX_HOT_WORDS,
    MAX_PROMPT_CHARS,
    hot_word_list,
)

CONSOLE_DEFAULTS = {"mode": "offline", "artifact": "srt", "language": "zh", "online_engine": "auto"}

#: 凭据字段的中文标签；字段集合本身从引擎注册表派生，不另写第二份。
_KEY_LABELS = {
    "dashscope_api_key": "百炼 DashScope",
    "openrouter_api_key": "OpenRouter",
}


def key_fields(config: Config) -> list[dict]:
    """页面要填的凭据字段。集合来自 `SPECS.required_keys`。"""
    seen: list[str] = []
    for spec_id in ("dashscope", "openrouter"):
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


def status_payload(config: Config, store: Store) -> dict:
    return {
        "online_ready": online_ready(config),
        "online_engines": engine_catalog(config),
        "credentials": config.credential_status(),
        "key_fields": key_fields(config),
        "defaults": CONSOLE_DEFAULTS,
        "stats": store.stats(),
        # C8：分离开关只对离线路径生效，页面要明确标注。
        "diar_enabled": config.enable_diar,
        "diar_available": True,
    }


def task_payload(config: Config, store: Store, jobs: JobManager, task: TaskRecord) -> dict:
    """任务 payload。

    Q10：`running` / `interrupted` / `cancelling` / `resumable` 全部由
    `state.task_flags(task, jobs.live_task_ids())` 单点给出，前端不再自行推断。
    """
    del config  # 保留参数形状，便于后续加按配置变化的字段
    flags = task_flags(task, jobs.live_task_ids())
    content = store.get_summary(task.id).get("content") or {}
    title = (content.get("title") or "").strip() or Path(task.source_path).name
    return {
        "id": task.id,
        "name": task.name,
        "title": title,
        "source_name": Path(task.source_path).name,
        "source_path": task.source_path,
        "mode": task.mode,
        "artifact": task.artifact,
        "status": task.status,
        "progress": task.progress,
        "engine": task.engine,
        "duration_s": task.duration_s,
        "audio_seconds": task.audio_seconds,
        "cost_usd": task.cost_usd,
        "chars": task.chars,
        "out_dir": task.out_dir,
        "txt_path": task.txt_path,
        "srt_path": task.srt_path,
        "raw_path": task.raw_path,
        "error": task.error,
        "created_at": task.created_at,
        "is_terminal": task.is_terminal,
        **flags,
        "txt_exists": bool(task.txt_path) and Path(task.txt_path).is_file(),
        "srt_exists": bool(task.srt_path) and Path(task.srt_path).is_file(),
        "src_exists": Path(task.source_path).is_file(),
    }


def detail_payload(
    config: Config, store: Store, jobs: JobManager, task_id: int
) -> dict | None:
    task = store.get_task(task_id)
    if not task:
        return None
    payload = task_payload(config, store, jobs, task)
    return {
        "task": payload,
        "chunks": [c.as_payload() for c in store.chunks_for(task_id)],
        "running": payload["running"],
        "interrupted": payload["interrupted"],
        "cancelling": payload["cancelling"],
        "resumable": payload["resumable"],
    }


def task_list(config: Config, store: Store, jobs: JobManager, limit: int = 50) -> list[dict]:
    return [task_payload(config, store, jobs, t) for t in store.list_tasks(limit=limit)]


def summary_settings_payload(config: Config) -> dict:
    from transcript_reimagined.config import DEFAULT_SUMMARY_MODEL, OPENROUTER_BASE_DEFAULT

    return {
        "model": config.summary_model,
        "default_model": DEFAULT_SUMMARY_MODEL,
        "base_url": config.openrouter_base,
        "default_base_url": OPENROUTER_BASE_DEFAULT,
        "api_key_configured": bool(config.openrouter_api_key),
        "api_key_masked": mask_preview(config.openrouter_api_key),
        "prompt": config.summary_prompt.strip() or DEFAULT_SUMMARY_PROMPT,
        "default_prompt": DEFAULT_SUMMARY_PROMPT,
        "custom_prompt": bool(config.summary_prompt.strip()),
        "max_prompt_chars": MAX_PROMPT_CHARS,
        "config_path": str(config.config_path),
        "prompt_path": str(config.summary_prompt_path),
        "hot_words": hot_word_list(config),
        "max_hot_words": MAX_HOT_WORDS,
        "max_hot_word_chars": MAX_HOT_WORD_CHARS,
        "glossary_path": str(config.glossary_path),
    }
