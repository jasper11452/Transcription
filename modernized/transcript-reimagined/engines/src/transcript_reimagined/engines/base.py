"""引擎接口与注册表。

一个引擎只负责一件事：把一段**已经是 16k 单声道 / 64k mp3 的音频文件**变成文本
（可选带时间戳）。切分、并发、重试、合并都由 orchestrate 负责——新增引擎只需要
写一个适配器 + 在这里加一条注册。

**注册表是引擎元数据的唯一来源**：可选清单、所需凭据、单次上限、费用说明都从它派生。
之前在 5 个地方分别描述同一组引擎（名字元组、凭据表、上限表、清单、构建分支），
加一个引擎要改 5 处且容易漂移——那正是本指南反对的"两份可推导清单"。

重建自 ``legacy/transcript/src/transcript/engines/base.py``。架构 v2 的两条边：
``engines`` 不依赖 ``post``（引擎只交原始 words）与 ``ingest``（时长由调用方传入）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, runtime_checkable

from transcript_reimagined.config import DASHSCOPE_MAX_CHUNK_S, Config
from transcript_reimagined.domain import TranscriptResult


@runtime_checkable
class Engine(Protocol):
    """所有离线/在线引擎的公共形状。"""

    name: str
    has_timestamps: bool
    # 单次调用能吃的最大音频秒数；None 表示没有已知上限。
    # 实测依据：qwen-audio-3.1-asr-flash 超过 300s 会报 AUDIO_DURATION_TOO_LONG。
    max_chunk_s: float | None

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        hotwords: list[str] | None = None,
        want_timestamps: bool = False,
        duration_s: float | None = None,
    ) -> TranscriptResult:
        """转写一个音频文件（分片）。失败必须抛 TranscriptError 的子类。

        ``duration_s`` 是调用方已经探测好的时长（架构 v2：引擎不再自己 probe）。
        引擎在自己的单次上限上做本地拦截，超限直接抛致命错误、不花钱。
        """
        ...


def _offline(config: Config, _model: str | None) -> Engine:  # pyright: ignore[reportUnusedParameter]
    return import_module(".offline", __package__).OfflineEngine(config)


def _dashscope(config: Config, model: str | None) -> Engine:
    module = import_module(".dashscope", __package__)
    return module.DashScopeEngine(config, model or config.dashscope_model)


def _openrouter(config: Config, model: str | None) -> Engine:
    module = import_module(".openrouter", __package__)
    return module.OpenRouterEngine(config, model or config.openrouter_model)


def _bcut(config: Config, model: str | None) -> Engine:
    return import_module(".bcut", __package__).BcutEngine(config, model or None)


@dataclass(frozen=True)
class EngineSpec:
    """一个引擎的全部元数据。加引擎时只改这里 + 写一个适配器文件。"""

    id: str
    label: str
    build: Callable[[Config, str | None], Engine]
    required_keys: tuple[str, ...] = ()
    max_chunk_s: float | None = None
    cost_note: str = ""
    online: bool = True


SPECS: tuple[EngineSpec, ...] = (
    EngineSpec(
        id="offline",
        label="离线（Qwen3-ASR + whisper 对齐）",
        build=_offline,
        online=False,
    ),
    EngineSpec(
        id="dashscope",
        label="百炼 qwen-audio-3.1-asr（字级时间戳，多语种/方言，热词，说话人分离）",
        build=_dashscope,
        required_keys=("dashscope_api_key",),
        max_chunk_s=DASHSCOPE_MAX_CHUNK_S,
        cost_note="按 token 计费（输入 ¥0.8/M，输出 ¥2.7/M）",
    ),
    EngineSpec(
        id="openrouter",
        label="OpenRouter microsoft/mai-transcribe-2（段级时间戳）",
        build=_openrouter,
        required_keys=("openrouter_api_key",),
        cost_note="≈$0.1/小时音频",
    ),
    EngineSpec(
        id="bcut",
        label="必剪（匿名免费，句级时间戳，偶有音近错字）",
        build=_bcut,
        cost_note="免费（音频会上传到 B 站存储）",
    ),
)

_BY_ID = {spec.id: spec for spec in SPECS}

# `auto` 不是引擎，是"按产物选"的策略。txt 与 srt 各落一个具体引擎。
AUTO_BY_ARTIFACT = {"txt": "dashscope", "srt": "openrouter"}

# 页面/CLI 的可选值：auto + 所有在线引擎
ONLINE_ENGINES: tuple[str, ...] = ("auto", *(s.id for s in SPECS if s.online))


def spec_for(kind: str) -> EngineSpec:
    spec = _BY_ID.get(kind)
    if spec is None:
        raise ValueError(f"未知引擎：{kind}")
    return spec


def build_engine(kind: str, config: Config, *, artifact: str) -> Engine:  # noqa: ARG001
    """按 `kind` 造引擎。`kind` 可以是 `dashscope`，也可以是 `dashscope:<model>`。"""
    family, _, model = kind.partition(":")
    return spec_for(family).build(config, model or None)


def resolve_kind(
    config: Config, *, mode: str, artifact: str, online_engine: str | None = None
) -> str:
    """把一个"用户意图"解析成具体引擎 id。

    离线只有一个选择。在线：`auto`（默认）按产物选——txt→百炼，srt→OpenRouter，
    这是最初定下的分工；显式指定时用指定引擎（bcut 同时能做 txt 与 srt）。
    `online_engine` 是**单任务级**覆盖（页面上的选择），留空则用配置里的值。
    """
    if mode == "offline":
        return "offline"
    chosen = (online_engine or config.online_engine or "auto").strip().lower()
    if chosen == "auto":
        return AUTO_BY_ARTIFACT.get(artifact, "dashscope")
    if chosen not in ONLINE_ENGINES:
        raise ValueError(f"未知的在线引擎：{chosen}（可选 {', '.join(ONLINE_ENGINES)}）")
    return chosen


def engine_kind_from_name(name: str | None) -> str | None:
    """从已落库的引擎名反推引擎族（续跑时用同一个引擎，不重新解释 auto）。"""
    if not name:
        return None
    family = name.split(":", 1)[0]
    return family if family in _BY_ID else None


def required_key_attrs(
    config: Config, *, mode: str, artifact: str, online_engine: str | None = None
) -> tuple[str, ...]:
    """这个任务实际会需要哪些凭据。本地能判定的缺失不应该拖到发请求时才报。"""
    kind = resolve_kind(config, mode=mode, artifact=artifact, online_engine=online_engine)
    return _BY_ID[kind].required_keys


def chunk_max_for(
    config: Config, *, mode: str, artifact: str, online_engine: str | None = None
) -> float:
    """实际会被用到的切片上限（配置值与引擎上限的较小值）。"""
    kind = resolve_kind(config, mode=mode, artifact=artifact, online_engine=online_engine)
    engine_max = _BY_ID[kind].max_chunk_s
    if engine_max is None:
        return config.chunk_max_s
    return min(config.chunk_max_s, engine_max)


def engine_catalog(config: Config) -> list[dict]:
    """给页面/CLI 用的可选引擎清单（含各自限制、费用与凭据就绪状态）。"""
    online = [s for s in SPECS if s.online]
    entries = [
        {
            "id": "auto",
            "label": "auto（按产物：{}）".format(
                "、".join(f"{k}→{v}" for k, v in AUTO_BY_ARTIFACT.items())
            ),
            "needs_key": sorted({k for s in online for k in s.required_keys}),
            "max_chunk_s": None,
            "has_timestamps": True,
            "cost": "按所选引擎",
            "ready": all(getattr(config, k, "") for s in online for k in s.required_keys),
        }
    ]
    for spec in online:
        missing = [k for k in spec.required_keys if not getattr(config, k, "")]
        entries.append(
            {
                "id": spec.id,
                "label": spec.label,
                "needs_key": list(spec.required_keys),
                "max_chunk_s": spec.max_chunk_s,
                "has_timestamps": True,
                "cost": spec.cost_note,
                "ready": not missing,
            }
        )
    return entries


def online_ready(config: Config) -> bool:
    """至少有一个在线引擎可用就算就绪——必剪不需要任何凭据。"""
    return any(
        not [k for k in s.required_keys if not getattr(config, k, "")] for s in SPECS if s.online
    )


__all__ = [
    "AUTO_BY_ARTIFACT",
    "ONLINE_ENGINES",
    "Engine",
    "EngineSpec",
    "SPECS",
    "build_engine",
    "chunk_max_for",
    "engine_catalog",
    "engine_kind_from_name",
    "online_ready",
    "required_key_attrs",
    "resolve_kind",
    "spec_for",
]
