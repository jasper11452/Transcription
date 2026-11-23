"""设置资源：总结设置、模型清单、词表、凭据。

写入统一走 `config.save_credentials` / `config.atomic_write`（0600、原子替换、
保留用户注释）。「空值 = 保留」在**本层**实现（RULE-040），写文件层只表达
「把这一项设成空」。
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from transcript_reimagined.config import Config, atomic_write, save_credentials
from transcript_reimagined.engines import engine_catalog
from transcript_reimagined.post.contracts import glossary_response, validate_glossary
from transcript_reimagined.post.glossary import is_hot_word_line

from ..dependencies import AppContext, get_context
from ..payloads import key_fields, summary_settings_payload
from ..validation import parse_summary_settings, validate_credential_value

router = APIRouter(prefix="/api")

MODEL_CACHE_TTL_S = 600
_model_cache: dict[str, tuple[float, list[dict], str | None]] = {}


def _write_hot_words(config: Config, words: list[str]) -> None:
    """只改热词块：`错词 -> 正确词` 规则与注释原样保留。"""
    existing = (
        config.glossary_path.read_text(encoding="utf-8").splitlines()
        if config.glossary_path.is_file()
        else []
    )
    kept = [line for line in existing if not is_hot_word_line(line)]
    while kept and not kept[-1].strip():
        kept.pop()
    block = [
        "",
        "# 热词：直接写正确写法（如 小新）。Agent 总结会按它统一写法，转录时也作为热词提示。",
        *words,
    ]
    atomic_write(config.glossary_path, "\n".join(kept + block).lstrip("\n") + "\n")


def _refresh_credentials_payload(config: Config) -> dict:
    return {
        "credentials": config.credential_status(),
        "key_fields": key_fields(config),
        "online_engines": engine_catalog(config),
    }


@router.get("/diar-settings")
def get_diar_settings(ctx: AppContext = Depends(get_context)) -> dict:
    """C8：说话人分离只对离线路径生效，页面必须明确标注。"""
    return {"enabled": ctx.config.enable_diar, "available": True, "scope": "offline"}


@router.put("/diar-settings")
async def put_diar_settings(request: Request, ctx: AppContext = Depends(get_context)) -> dict:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "请求体必须是 JSON") from exc
    enabled = body.get("enabled") if isinstance(body, dict) else None
    if not isinstance(enabled, bool):
        raise HTTPException(400, "enabled 必须是布尔值")
    try:
        save_credentials(
            ctx.config.config_path, {"ENABLE_DIAR": "true" if enabled else "false"}
        )
    except OSError as exc:
        raise HTTPException(500, "本机设置保存失败，请检查配置目录权限。") from exc
    ctx.config.enable_diar = enabled
    return {"enabled": enabled, "available": True, "scope": "offline"}


@router.get("/summary-settings")
def get_summary_settings(ctx: AppContext = Depends(get_context)) -> dict:
    return summary_settings_payload(ctx.config)


@router.put("/summary-settings")
async def put_summary_settings(request: Request, ctx: AppContext = Depends(get_context)) -> dict:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "请求体必须是 JSON") from exc
    try:
        settings = parse_summary_settings(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    updates = {
        "SUMMARY_MODEL": settings.model,
        "OPENROUTER_BASE": settings.base_url,
    }
    if settings.api_key:  # 留空保留现有密钥，绝不把掩码当作真实密钥写回。
        updates["OPENROUTER_API_KEY"] = settings.api_key
    try:
        save_credentials(ctx.config.config_path, updates)
        atomic_write(ctx.config.summary_prompt_path, settings.prompt)
        if settings.hot_words is not None:
            _write_hot_words(ctx.config, settings.hot_words)
    except OSError as exc:
        raise HTTPException(500, "本机设置保存失败，请检查配置目录权限。") from exc

    ctx.config.summary_model = settings.model
    ctx.config.openrouter_base = settings.base_url
    if settings.api_key:
        ctx.config.openrouter_api_key = settings.api_key
    ctx.config.summary_prompt = settings.prompt
    _model_cache.clear()
    return summary_settings_payload(ctx.config)


@router.get("/summary-models")
def list_summary_models(refresh: bool = False, ctx: AppContext = Depends(get_context)) -> dict:
    """OpenRouter 模型清单，供设置页挑选。只请求已配置的 Base URL。"""
    config = ctx.config
    if not config.openrouter_api_key:
        return {
            "models": [],
            "error": "尚未配置 API Key 密钥，请先保存连接设置。",
            "cached": False,
        }
    cached = _model_cache.get(config.openrouter_base)
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
        _model_cache[config.openrouter_base] = (time.monotonic(), [], message)
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
    _model_cache[config.openrouter_base] = (time.monotonic(), models, None)
    return {"models": models, "error": None, "cached": False}


@router.get("/glossary")
def get_glossary(ctx: AppContext = Depends(get_context)) -> dict:
    text = ""
    if ctx.config.glossary_path.is_file():
        text = ctx.config.glossary_path.read_text(encoding="utf-8")
    response = glossary_response(text)
    return {
        "text": response.text,
        "rules": [{"wrong": r.wrong, "right": r.right} for r in response.rules],
    }


@router.put("/glossary")
def put_glossary(text: str = Form(""), ctx: AppContext = Depends(get_context)) -> dict:
    validation = validate_glossary(text)
    if not validation.ok:
        raise HTTPException(400, validation.error_message())
    atomic_write(ctx.config.glossary_path, text)
    return {"rule_count": validation.rule_count}


@router.post("/credentials")
async def save_credentials_route(request: Request, ctx: AppContext = Depends(get_context)) -> dict:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "请求体必须是 JSON") from exc
    keys: dict = body.get("keys") or {}
    clear: list = body.get("clear") or []

    allowed = {field["attr"] for field in key_fields(ctx.config)}
    unknown = (set(keys) | set(clear)) - allowed
    if unknown:
        raise HTTPException(400, f"未知的凭据字段：{', '.join(sorted(unknown))}")

    updates: dict[str, str] = {}
    try:
        for attr, value in keys.items():
            clean = validate_credential_value(attr, value)
            if not clean:
                continue  # 留空 = 保持现状（RULE-040）
            updates[attr.upper()] = clean
        for attr in clear:
            updates[attr.upper()] = ""
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # 全部校验通过才落盘（沿用 RULE-051 的“先校验、后写入”）。
    if updates:
        save_credentials(ctx.config.config_path, updates)
    for attr in keys:
        clean = validate_credential_value(attr, keys[attr])
        if clean:
            setattr(ctx.config, attr, clean)
    for attr in clear:
        setattr(ctx.config, attr, "")
    return _refresh_credentials_payload(ctx.config)
