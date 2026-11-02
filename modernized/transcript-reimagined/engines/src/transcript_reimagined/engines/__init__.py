"""`transcript_reimagined.engines` —— Engine 协议 + SPECS 注册表 + 4 个适配器。

公开面见 README.md。适配器模块按需导入（`build_engine` 用 `import_module`），
所以只 import 本包不会拉起 httpx / MLX。
"""

from __future__ import annotations

from .base import (
    AUTO_BY_ARTIFACT,
    ONLINE_ENGINES,
    SPECS,
    Engine,
    EngineSpec,
    build_engine,
    chunk_max_for,
    engine_catalog,
    engine_kind_from_name,
    online_ready,
    required_key_attrs,
    resolve_kind,
    spec_for,
)

__all__ = [
    "AUTO_BY_ARTIFACT",
    "ONLINE_ENGINES",
    "SPECS",
    "Engine",
    "EngineSpec",
    "build_engine",
    "chunk_max_for",
    "engine_catalog",
    "engine_kind_from_name",
    "online_ready",
    "required_key_attrs",
    "resolve_kind",
    "spec_for",
]
