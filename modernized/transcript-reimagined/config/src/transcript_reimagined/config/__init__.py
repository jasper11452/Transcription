"""`transcript_reimagined.config` —— 配置与用户文件。

公开面见 README.md。本包在依赖图中位于 `domain` 之上、所有业务包之下。
"""

from __future__ import annotations

from .settings import (
    BCUT_BASE_DEFAULT,
    DASHSCOPE_BASE_DEFAULT,
    DASHSCOPE_MAX_CHUNK_S,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DASHSCOPE_MODEL,
    DEFAULT_DIAR_LIB,
    DEFAULT_DIAR_MODEL,
    DEFAULT_OFFLINE_MODEL,
    DEFAULT_ONLINE_ENGINE,
    DEFAULT_OPENROUTER_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATE_DB,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_TIMING_MODEL,
    DEFAULT_VAD_MODEL,
    MAX_CREDENTIAL_CHARS,
    OPENROUTER_BASE_DEFAULT,
    Config,
    ConfigError,
    atomic_write,
    mask,
    mask_preview,
    save_credentials,
    write_config_template,
)

__all__ = [
    "BCUT_BASE_DEFAULT",
    "DASHSCOPE_BASE_DEFAULT",
    "DASHSCOPE_MAX_CHUNK_S",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_DASHSCOPE_MODEL",
    "DEFAULT_DIAR_LIB",
    "DEFAULT_DIAR_MODEL",
    "DEFAULT_OFFLINE_MODEL",
    "DEFAULT_ONLINE_ENGINE",
    "DEFAULT_OPENROUTER_MODEL",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_STATE_DB",
    "DEFAULT_SUMMARY_MODEL",
    "DEFAULT_TIMING_MODEL",
    "DEFAULT_VAD_MODEL",
    "MAX_CREDENTIAL_CHARS",
    "OPENROUTER_BASE_DEFAULT",
    "Config",
    "ConfigError",
    "atomic_write",
    "mask",
    "mask_preview",
    "save_credentials",
    "write_config_template",
]
