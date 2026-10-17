"""配置与凭据。

铁律（NFR-4）：
- 密钥、总结模型名和 Base URL 保存在 ``~/.config/transcript/config.env``；
  密钥**不读** shell 环境里的同名变量。
- Agent 总结提示词保存在同目录 ``summary-prompt.txt``。
- 任何日志、页面、SQLite、产物里都不出现明文密钥；只显示掩码尾号。

重建自 ``legacy/transcript/src/transcript/config.py``。与遗留版的两处行为差异
均已署名（见 README.md 与 ``../../DEVIATIONS.md``）：

1. 数值解析不再静默吞 ``ValueError``（``RULE-105`` 的人裁定）。
2. 长度 ≤ 8 的密钥不显示尾部（遗留版会把短密钥整个打印出来）。
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from transcript_reimagined.domain import BACKOFF_BASE_S, MAX_ATTEMPTS, FatalError

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "transcript" / "config.env"
DEFAULT_STATE_DB = Path.home() / "Documents" / "Transcript" / "state.db"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Transcript" / "output"

# 已实测的默认引擎（证据见 docs/spec.md 与 spikes/）
# qwen-audio-3.1-asr-flash：多模态实时接口，字级时间戳，txt/srt 都能出；300s/次上限
# 注意：带 -filetrans 后缀的同名模型走异步文件转写接口，与本代码的
# multimodal-generation 调用形状不兼容，会返回 HTTP 400 InvalidParameter，不要使用。
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

#: 凭据值上限（RULE-040：值 ≤ 512 字符）。
MAX_CREDENTIAL_CHARS = 512

#: 掩码显示尾号所需的最小长度。短于此长度的密钥不显示尾部 —— 否则 `secret[-4:]`
#: 会把短密钥整个打印出来（遗留实现的已知边角，重建版按 NFR-4 收紧）。
MIN_MASK_LEN = 9


class ConfigError(FatalError, ValueError):
    """配置无效：文件不可读、旧版设置格式错误、数值项解析或范围不合法。

    继承 ``ValueError`` 是为了兼容遗留调用方对 ``ValueError`` 的捕获；继承
    ``FatalError`` 让它进入「不可重试」的分类 —— 配置错误重试只会浪费时间。
    """


def mask(secret: str | None) -> str:
    """只暴露尾号，长度也只给粗粒度信息。"""
    if not secret:
        return "未配置"
    if len(secret) < MIN_MASK_LEN:
        return "已配置（尾号 ****）"
    return f"已配置（尾号 {secret[-4:]}）"


def mask_preview(secret: str | None) -> str:
    """输入框占位符用的掩码：固定长度的点 + 尾号，中间一律掩盖。

    和 `mask` 的区别：`mask` 是「配没配」的状态文案（未配置时返回中文），这里是
    回填到输入框里的视觉占位符（未配置时返回空串）。两者都只暴露尾号 4 位。
    """
    if not secret:
        return ""
    if len(secret) < MIN_MASK_LEN:
        return "•" * 8
    return f"{'•' * 8}{secret[-4:]}"


def atomic_write(path: Path | str, text: str, *, mode: int = 0o600) -> Path:
    """把 ``text`` 原子写到 ``path``：同目录临时文件 → fsync → chmod → ``os.replace``。

    这是本系统**唯一**的用户文件写入通道（`config.env` / `glossary.txt` /
    `summary-prompt.txt`）。中途失败不会留下半个文件，也不会出现「临时文件可被
    同机其他用户读到」的窗口。

    ``os.replace`` 在同目录内是原子的；临时文件用 ``mkstemp`` 创建，继承 0600，
    再显式 chmod 到调用方要求的权限。
    """
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


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
    # 说话人分离。enable_diar=False 时完全跳过，不加载库和模型。
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
    max_attempts: int = MAX_ATTEMPTS
    backoff_base: float = BACKOFF_BASE_S
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
        """读主配置文件和可选的总结设置；缺失时使用默认值。

        优先级：``config.env`` > ``summary-prompt.txt`` / 旧版 ``summary-settings.json``
        > 内建默认。

        **数值项解析失败或范围不合法会抛 ``ConfigError``**，并一次列出所有问题 ——
        手误在启动时可见（`RULE-105` 的人裁定）。空值仍然回退默认值。
        """
        cfg_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
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

        # 兼容上一版界面写入的模型和提示词，当前配置优先使用 config.env 与
        # summary-prompt.txt。旧文件只在「新设置缺失」时被采纳；格式错误必须
        # 显式报错，不能悄悄回退默认值（RULE-105）。
        legacy_path = cfg.config_path.with_name("summary-settings.json")
        if legacy_path.is_file() and (not has_summary_model or not prompt_path.is_file()):
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError(f"旧版 Agent 总结设置无法读取：{legacy_path}") from exc
            if not isinstance(legacy, dict):
                raise ConfigError(f"旧版 Agent 总结设置格式不正确：{legacy_path}")
            legacy_model, legacy_prompt = legacy.get("model"), legacy.get("prompt", "")
            if not has_summary_model and legacy_model is not None:
                if not isinstance(legacy_model, str) or not legacy_model.strip():
                    raise ConfigError("Agent 总结模型配置无效")
                cfg.summary_model = legacy_model.strip()
            if not prompt_path.is_file():
                if not isinstance(legacy_prompt, str):
                    raise ConfigError("Agent 总结提示词配置无效")
                cfg.summary_prompt = legacy_prompt

        _apply_numeric_overrides(cfg, values)
        cfg._validate()
        return cfg

    def _validate(self) -> None:
        """范围校验。非法组合会让分片不变量或并发预算失效，必须在启动时拦住。"""
        problems: list[str] = []
        if self.online_concurrency < 1:
            problems.append("ONLINE_CONCURRENCY 必须 >= 1")
        if self.max_attempts < 1:
            problems.append("MAX_ATTEMPTS 必须 >= 1")
        if self.backoff_base < 0:
            problems.append("BACKOFF_BASE 必须 >= 0")
        if self.chunk_min_s <= 0 or self.chunk_max_s <= 0:
            problems.append("CHUNK_MIN_S 与 CHUNK_MAX_S 必须 > 0")
        if self.chunk_min_s > self.chunk_max_s:
            problems.append("CHUNK_MIN_S 不能大于 CHUNK_MAX_S")
        if self.chunk_overlap_s < 0:
            problems.append("CHUNK_OVERLAP_S 不能为负")
        if self.chunk_overlap_s >= self.chunk_min_s:
            problems.append("CHUNK_OVERLAP_S 必须小于 CHUNK_MIN_S")
        if problems:
            raise ConfigError("配置范围不合法：" + "；".join(problems))

    def warn_if_world_readable(self) -> str | None:
        """凭证文件权限不对时给出提示（不打印内容）。"""
        if not self.config_path.exists():
            return None
        mode = self.config_path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return f"{self.config_path} 权限过宽，建议 chmod 600（当前 {oct(mode & 0o777)}）"
        return None


_NUMERIC_OVERRIDES: tuple[tuple[str, str, type], ...] = (
    ("ONLINE_CONCURRENCY", "online_concurrency", int),
    ("MAX_ATTEMPTS", "max_attempts", int),
    ("BACKOFF_BASE", "backoff_base", float),
    ("CHUNK_MIN_S", "chunk_min_s", float),
    ("CHUNK_MAX_S", "chunk_max_s", float),
    ("CHUNK_OVERLAP_S", "chunk_overlap_s", float),
)


def _apply_numeric_overrides(cfg: Config, values: dict[str, str]) -> None:
    """应用数值覆盖；任一无效项都收集起来一次性报错。

    遗留实现把解析包在 ``contextlib.suppress(ValueError)`` 里，``CHUNK_MAX_S=12O``
    会静默回退默认值 —— 这是 `RULE-105` 判定的缺陷。重建版把问题变成启动时的
    ``ConfigError``，并列出所有手误项，而不是只报第一个。
    """
    problems: list[str] = []
    for env_name, attr, conv in _NUMERIC_OVERRIDES:
        raw = values.get(env_name)
        if raw is None or not raw.strip():
            continue
        try:
            setattr(cfg, attr, conv(raw.strip()))
        except ValueError:
            expected = "整数" if conv is int else "数字"
            problems.append(f"{env_name}={raw!r} 不是合法的{expected}")
    if problems:
        raise ConfigError("配置文件数值项无效：" + "；".join(problems))


def save_credentials(path: Path | str, updates: dict[str, str | None]) -> Path:
    """把页面输入的密钥写进 config.env。

    安全约束（NFR-4）：
    - **值只从内存到磁盘**：不落日志、不进 SQLite、不进产物，本函数不打印任何东西。
    - 保留文件里的其他行与注释（用户手写的覆盖项不能被吃掉）。
    - 先写临时文件再 ``os.replace`` 原子替换，且全程 600。
    - 值里有空白/控制字符/等号或超过 512 字符直接拒绝：这类字符会破坏 .env 的
      行结构，也会把密钥截断成另一个值（宁可报错，不要写坏用户的配置）。
      空串或 ``None`` = 清掉这一项的值（写成 ``KEY=``）。

    注意：**「空值 = 保留」是 API 层的事**。调用方必须先把空白输入过滤掉，
    才符合 `RULE-040`；本函数只忠实表达「把这一项设成空」。
    """
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []

    for env_name, value in updates.items():
        if not env_name or not all(ch.isalnum() or ch == "_" for ch in env_name):
            raise ValueError(f"非法的配置项名称：{env_name!r}")
        clean = "" if value is None else str(value).strip()
        if len(clean) > MAX_CREDENTIAL_CHARS:
            raise ValueError(f"{env_name} 超过 {MAX_CREDENTIAL_CHARS} 字符")
        if any(ch.isspace() or ch == "=" or ord(ch) < 0x20 for ch in clean):
            raise ValueError(f"{env_name} 不允许空白、控制字符或等号")
        for i, line in enumerate(lines):
            bare = line.strip()
            if bare.startswith("#") or "=" not in bare:
                continue
            if bare.split("=", 1)[0].strip() == env_name:
                lines[i] = f"{env_name}={clean}"
                break
        else:
            lines.append(f"{env_name}={clean}")

    atomic_write(target, "\n".join(lines).rstrip("\n") + "\n", mode=0o600)
    return target


def write_config_template(path: Path | None = None) -> Path:
    """生成配置模板并设 600。已存在则不覆盖（避免把用户的密钥清掉）。"""
    target = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        atomic_write(
            target,
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
            mode=0o600,
        )
    os.chmod(target, 0o600)
    return target
