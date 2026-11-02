"""配置与凭据。

铁律（见 AGENTS.md "边界"）：
- 密钥、总结模型名和 OpenRouter Base URL 保存在 `~/.config/transcript/config.env`；密钥不读 shell 环境里的同名变量。
- Agent 总结提示词保存在同目录 `summary-prompt.txt`。
- 任何日志、页面、SQLite、产物里都不出现明文密钥；只显示掩码尾号。
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "transcript" / "config.env"
DEFAULT_STATE_DB = Path.home() / "Documents" / "Transcript" / "state.db"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Transcript" / "output"

# 已实测的默认引擎（证据见 docs/spec.md 与 spikes/）
# qwen-audio-3.1-asr-flash：多模态实时接口，字级时间戳，txt/srt 都能出；300s/次上限
# 注意：带 -filetrans 后缀的同名模型走异步文件转写接口，与本代码的 multimodal-generation
# 调用形状不兼容，会返回 HTTP 400 InvalidParameter，不要使用。
DEFAULT_DASHSCOPE_MODEL = "qwen-audio-3.1-asr-flash"
DEFAULT_OPENROUTER_MODEL = "microsoft/mai-transcribe-2"
DEFAULT_OFFLINE_MODEL = "mlx-community/Qwen3-ASR-1.7B-8bit"
DEFAULT_TIMING_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_VAD_MODEL = "mlx-community/silero-vad-v6"
DEFAULT_SUMMARY_MODEL = "z-ai/glm-5.3-flash"

_BASE_NEMO = Path.home() / "Library" / "Application Support" / "NeMoSpeech" / "main-97a15af"
DEFAULT_DIAR_LIB = str(_BASE_NEMO / "lib" / "libnemo_speech_asr_c.dylib")
DEFAULT_DIAR_MODEL = str(
    Path.home()
    / "Library"
    / "Application Support"
    / "NeMoSpeech"
    / "models"
    / "Nemotron-3-Diarization.q8_0.gguf"
)

# 在线引擎：默认走百炼 qwen-audio-3.1-asr-flash（字级时间戳）；
# 设成 auto 则按产物选（txt→百炼，srt→OpenRouter），也可显式指定 openrouter/bcut
DEFAULT_ONLINE_ENGINE = "auto"

DASHSCOPE_BASE_DEFAULT = "https://dashscope.aliyuncs.com"
OPENROUTER_BASE_DEFAULT = "https://openrouter.ai/api/v1"
BCUT_BASE_DEFAULT = "https://member.bilibili.com/x/bcut/rubick-interface"

# qwen-audio-3.1-asr-flash 的服务端硬上限（实测：330s → AUDIO_DURATION_TOO_LONG）
DASHSCOPE_MAX_CHUNK_S = 300.0


def mask(secret: str | None) -> str:
    """只暴露尾号，长度也只给粗粒度信息。"""
    if not secret:
        return "未配置"
    return f"已配置（尾号 {secret[-4:]}）"


def mask_preview(secret: str | None) -> str:
    """输入框占位符用的掩码：固定长度的点 + 尾号，中间一律掩盖。

    和 `mask` 的区别：`mask` 是"配没配"的状态文案（未配置时返回中文），这里是
    回填到输入框里的视觉占位符（未配置时返回空串）。两者都只暴露尾号 4 位。
    """
    if not secret:
        return ""
    return f"{'•' * 8}{secret[-4:]}"


@dataclass
class Config:
    """运行配置。所有值都有默认，缺文件也能跑（离线路径不需要任何密钥）。"""

    config_path: Path = DEFAULT_CONFIG_PATH
    dashscope_api_key: str = ""
    openrouter_api_key: str = ""
    dashscope_base: str = DASHSCOPE_BASE_DEFAULT
    openrouter_base: str = OPENROUTER_BASE_DEFAULT
    bcut_base: str = BCUT_BASE_DEFAULT
    online_engine: str = DEFAULT_ONLINE_ENGINE
    dashscope_model: str = DEFAULT_DASHSCOPE_MODEL
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL
    summary_model: str = DEFAULT_SUMMARY_MODEL
    summary_prompt: str = ""
    offline_model: str = DEFAULT_OFFLINE_MODEL
    timing_model: str = DEFAULT_TIMING_MODEL
    vad_model: str = DEFAULT_VAD_MODEL
    # 说话人分离。enable_diar=False 时完全跳过，不加载库和模型
    enable_diar: bool = False
    diar_lib: str = DEFAULT_DIAR_LIB
    diar_model: str = DEFAULT_DIAR_MODEL
    state_db: Path = DEFAULT_STATE_DB
    output_dir: Path = DEFAULT_OUTPUT_DIR
    glossary_path: Path = field(
        default_factory=lambda: Path.home() / ".config" / "transcript" / "glossary.txt"
    )
    # 离线串行、在线并行（spec 第 5 节 Q2）
    online_concurrency: int = 4
    max_attempts: int = 3
    backoff_base: float = 1.0
    # 切片：目标 30–120s，静音边界留 0.3–1s 重叠。
    # 实际切片上限还会被引擎的 max_chunk_s 收紧（百炼原生 300s）。
    chunk_min_s: float = 30.0
    chunk_max_s: float = 120.0
    chunk_overlap_s: float = 0.5

    @property
    def summary_prompt_path(self) -> Path:
        """Agent 总结提示词的本机持久化文件。"""
        return self.config_path.with_name("summary-prompt.txt")

    def credential_status(self) -> dict[str, str]:
        """给页面用的状态，永远不含明文。"""
        return {
            "dashscope_api_key": mask(self.dashscope_api_key),
            "openrouter_api_key": mask(self.openrouter_api_key),
            "config_path": str(self.config_path),
            "online_engine": self.online_engine,
            "dashscope_model": self.dashscope_model,
            "openrouter_model": self.openrouter_model,
            "offline_model": self.offline_model,
            "bcut_needs_key": "否（必剪匿名接口）",
        }

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """读主配置文件和可选的总结设置；缺失时使用默认值。"""
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        values: dict[str, str] = {}
        if cfg_path.exists():
            values = {k: v for k, v in dotenv_values(cfg_path).items() if v is not None}

        def get(name: str, default: str) -> str:
            return (values.get(name) or default).strip()

        has_summary_model = "SUMMARY_MODEL" in values
        cfg = cls(
            config_path=cfg_path,
            dashscope_api_key=get("DASHSCOPE_API_KEY", ""),
            openrouter_api_key=get("OPENROUTER_API_KEY", ""),
            dashscope_base=get("DASHSCOPE_BASE", DASHSCOPE_BASE_DEFAULT).rstrip("/"),
            openrouter_base=get("OPENROUTER_BASE", OPENROUTER_BASE_DEFAULT).rstrip("/"),
            bcut_base=get("BCUT_BASE", BCUT_BASE_DEFAULT).rstrip("/"),
            online_engine=get("ONLINE_ENGINE", DEFAULT_ONLINE_ENGINE),
            dashscope_model=get("DASHSCOPE_MODEL", DEFAULT_DASHSCOPE_MODEL),
            openrouter_model=get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
            summary_model=get("SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL),
            offline_model=get("OFFLINE_MODEL", DEFAULT_OFFLINE_MODEL),
            timing_model=get("TIMING_MODEL", DEFAULT_TIMING_MODEL),
            vad_model=get("VAD_MODEL", DEFAULT_VAD_MODEL),
            enable_diar=get("ENABLE_DIAR", "false").lower() in ("1", "true", "yes"),
            diar_lib=get("DIAR_LIB", DEFAULT_DIAR_LIB),
            diar_model=get("DIAR_MODEL", DEFAULT_DIAR_MODEL),
            state_db=Path(get("STATE_DB", str(DEFAULT_STATE_DB))).expanduser(),
            output_dir=Path(get("OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))).expanduser(),
            glossary_path=Path(
                get("GLOSSARY_PATH", str(Path.home() / ".config/transcript/glossary.txt"))
            ).expanduser(),
        )
        prompt_path = cfg.summary_prompt_path
        if prompt_path.is_file():
            cfg.summary_prompt = prompt_path.read_text(encoding="utf-8")

        # 兼容上一版界面写入的模型和提示词，当前配置优先使用 config.env 与 summary-prompt.txt。
        legacy_path = cfg.config_path.with_name("summary-settings.json")
        if legacy_path.is_file() and (not has_summary_model or not prompt_path.is_file()):
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"旧版 Agent 总结设置无法读取：{legacy_path}") from exc
            if not isinstance(legacy, dict):
                raise ValueError(f"旧版 Agent 总结设置格式不正确：{legacy_path}")
            legacy_model, legacy_prompt = legacy.get("model"), legacy.get("prompt", "")
            if not has_summary_model and legacy_model is not None:
                if not isinstance(legacy_model, str) or not legacy_model.strip():
                    raise ValueError("Agent 总结模型配置无效")
                cfg.summary_model = legacy_model.strip()
            if not prompt_path.is_file():
                if not isinstance(legacy_prompt, str):
                    raise ValueError("Agent 总结提示词配置无效")
                cfg.summary_prompt = legacy_prompt

        for name, attr, conv in (
            ("ONLINE_CONCURRENCY", "online_concurrency", int),
            ("MAX_ATTEMPTS", "max_attempts", int),
            ("BACKOFF_BASE", "backoff_base", float),
            ("CHUNK_MIN_S", "chunk_min_s", float),
            ("CHUNK_MAX_S", "chunk_max_s", float),
            ("CHUNK_OVERLAP_S", "chunk_overlap_s", float),
        ):
            raw = values.get(name)
            if raw:
                with contextlib.suppress(ValueError):
                    setattr(cfg, attr, conv(raw))
        return cfg

    def warn_if_world_readable(self) -> str | None:
        """凭证文件权限不对时给出提示（不打印内容）。"""
        if not self.config_path.exists():
            return None
        mode = self.config_path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return f"{self.config_path} 权限过宽，建议 chmod 600（当前 {oct(mode & 0o777)}）"
        return None


def save_credentials(path: Path, updates: dict[str, str | None]) -> Path:
    """把页面输入的密钥写进 config.env。

    安全约束（AGENTS.md 密钥铁律）：
    - **值只从内存到磁盘**：不落日志、不进 SQLite、不进产物，本函数不打印任何东西。
    - 保留文件里的其他行与注释（用户手写的覆盖项不能被吃掉）。
    - 先写临时文件再 `os.replace` 原子替换，且全程 600：中途失败不会留下半个文件，
      也不会出现"短暂可被同机其他用户读到"的窗口。
    - 值里有空白/换行/等号直接拒绝：这类字符会破坏 .env 的行结构，也会把密钥截断成
      另一个值（宁可报错，不要写坏用户的配置）。空串 = 清掉这一项的值。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []

    for env_name, value in updates.items():
        clean = "" if value is None else str(value).strip()
        if any(ch.isspace() or ch == "=" for ch in clean):
            raise ValueError(f"{env_name} 不允许空白或等号")
        for i, line in enumerate(lines):
            bare = line.strip()
            if bare.startswith("#") or "=" not in bare:
                continue
            if bare.split("=", 1)[0].strip() == env_name:
                lines[i] = f"{env_name}={clean}"
                break
        else:
            lines.append(f"{env_name}={clean}")

    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target


def write_config_template(path: Path | None = None) -> Path:
    """生成配置模板并设 600。已存在则不覆盖（避免把用户的密钥清掉）。"""
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(
            "# Transcript 配置。只被本工具读取；不要提交到任何仓库。\n"
            "DASHSCOPE_API_KEY=\n"
            "OPENROUTER_API_KEY=\n"
            "# 可选覆盖（默认值见 docs/spec.md）\n"
            "# ONLINE_ENGINE=auto        # auto | dashscope | openrouter | bcut\n"
            "# DASHSCOPE_MODEL=qwen-audio-3.1-asr-flash\n"
            "# OPENROUTER_MODEL=microsoft/mai-transcribe-2\n"
            "# OPENROUTER_BASE=https://openrouter.ai/api/v1\n"
            "# SUMMARY_MODEL=z-ai/glm-5.3-flash\n"
            "# Agent 总结提示词保存在同目录 summary-prompt.txt，可在任务详情的总结标签中编辑。\n"
            "# OFFLINE_MODEL=mlx-community/Qwen3-ASR-1.7B-8bit\n"
            "# OUTPUT_DIR=~/Documents/Transcript/output\n",
            encoding="utf-8",
        )
    os.chmod(target, 0o600)
    return target
