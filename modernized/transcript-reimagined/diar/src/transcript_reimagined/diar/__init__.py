"""`transcript_reimagined.diar` —— 说话人分离（ctypes FFI，仅离线路径）。"""

from __future__ import annotations

from .ffi import (
    DEFAULT_DIAR_LIB,
    DEFAULT_DIAR_MODEL,
    DIAR_ABI_VERSION,
    DiarSegment,
    assign_speaker,
    diarize,
)

__all__ = [
    "DEFAULT_DIAR_LIB",
    "DEFAULT_DIAR_MODEL",
    "DIAR_ABI_VERSION",
    "DiarSegment",
    "assign_speaker",
    "diarize",
]
