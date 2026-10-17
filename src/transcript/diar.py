"""说话人分离：ctypes 调 libnemo_speech_asr_c.dylib，文件模式。

用 v3-offline 预设（流式状态机，无 6.6 分钟上限），以 1s 块推送全文件，
比直接调 CLI 省去子进程和临时文件的开销。

模型和库在进程内缓存（配置相同则不重载），FastAPI 单进程下安全。
"""

from __future__ import annotations

import atexit as _atexit
import contextlib
import ctypes as C
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# 默认安装路径（cmake --install 产物）
_BASE = Path.home() / "Library" / "Application Support" / "NeMoSpeech" / "main-97a15af"
DEFAULT_DIAR_LIB = str(_BASE / "lib" / "libnemo_speech_asr_c.dylib")
DEFAULT_DIAR_MODEL = str(
    Path.home()
    / "Library"
    / "Application Support"
    / "NeMoSpeech"
    / "models"
    / "Nemotron-3-Diarization.q8_0.gguf"
)

# 1-based speaker int, 泛型编号（同一文件内稳定，不代表身份）
DiarSegment = tuple[float, float, int]


# ---------- C 结构体 ----------


class _ModelCfg(C.Structure):
    _fields_ = [
        ("size", C.c_size_t),
        ("model_path", C.c_char_p),
        ("gpu", C.c_int32),
        ("preset", C.c_char_p),
        ("chunk_frames", C.c_int32),
        ("right_context_frames", C.c_int32),
        ("left_context_frames", C.c_int32),
        ("fifo_frames", C.c_int32),
        ("spkcache_frames", C.c_int32),
        ("update_period_frames", C.c_int32),
    ]


class _DiarSeg(C.Structure):
    _fields_ = [
        ("start_time", C.c_double),
        ("end_time", C.c_double),
        ("speaker", C.c_int32),
    ]


# ---------- 进程级缓存 ----------

_lib: C.CDLL | None = None
_lib_path_cached: str | None = None
_model_handle: C.c_void_p | None = None
_model_key: tuple[str, str] | None = None


def _cleanup() -> None:
    global _model_handle, _lib
    if _model_handle is not None and _lib is not None:
        with contextlib.suppress(Exception):
            _lib.nemo_speech_diar_destroy(_model_handle)
        _model_handle = None


_atexit.register(_cleanup)


def _load_lib(lib_path: str) -> C.CDLL:
    global _lib, _lib_path_cached
    if _lib is None or _lib_path_cached != lib_path:
        lib = C.CDLL(lib_path)
        lib.nemo_speech_asr_last_error.restype = C.c_char_p
        lib.nemo_speech_diar_seconds_per_frame.restype = C.c_double
        lib.nemo_speech_diar_frame_count.restype = C.c_int64
        lib.nemo_speech_diar_frame_count.argtypes = [C.c_void_p]
        lib.nemo_speech_diar_stream_push_f32.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_float),
            C.c_size_t,
            C.c_int32,
        ]
        lib.nemo_speech_diar_segments.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_void_p,
            C.c_size_t,
            C.POINTER(C.c_size_t),
        ]
        _lib = lib
        _lib_path_cached = lib_path
    return _lib


def _ok(lib: C.CDLL, rc: int) -> None:
    if rc != 0:
        raw = lib.nemo_speech_asr_last_error()
        raise RuntimeError(raw.decode() if raw else f"nemo_speech error {rc}")


def _get_model(lib: C.CDLL, model_path: str, lib_path: str) -> C.c_void_p:
    global _model_handle, _model_key
    key = (lib_path, model_path)
    if _model_handle is not None and _model_key == key:
        return _model_handle
    if _model_handle is not None:
        lib.nemo_speech_diar_destroy(_model_handle)
        _model_handle = None
    cfg = _ModelCfg(
        C.sizeof(_ModelCfg),
        model_path.encode(),
        0,  # gpu=0 → Metal
        b"v3-offline",
        0,
        0,
        0,
        0,
        0,
        0,  # 用预设默认值
    )
    handle = C.c_void_p()
    _ok(lib, lib.nemo_speech_diar_create(C.byref(cfg), C.byref(handle)))
    _model_handle = handle
    _model_key = key
    return handle


def _pull_segments(lib: C.CDLL, st: C.c_void_p) -> list[DiarSegment]:
    n = C.c_size_t(0)
    _ok(lib, lib.nemo_speech_diar_segments(st, None, None, 0, C.byref(n)))
    if n.value == 0:
        return []
    buf = (_DiarSeg * n.value)()
    _ok(lib, lib.nemo_speech_diar_segments(st, None, buf, n.value, C.byref(n)))
    return [(buf[i].start_time, buf[i].end_time, buf[i].speaker) for i in range(n.value)]


# ---------- 公开接口 ----------


def diarize(
    wav_path: Path | str,
    *,
    lib_path: str = DEFAULT_DIAR_LIB,
    model_path: str = DEFAULT_DIAR_MODEL,
) -> list[DiarSegment]:
    """对 16kHz 单声道 wav 做说话人分离，返回 (start_s, end_s, speaker_int) 列表。

    使用 v3-offline 流式预设（无长度限制），以 1s 块推入；模型进程内缓存。
    调用方负责传入已归一化为 16kHz 单声道的 wav（pipeline.py 里的 work.wav）。
    """
    import numpy as np
    import soundfile as sf

    lib = _load_lib(lib_path)
    model = _get_model(lib, model_path, lib_path)

    y, native_sr = sf.read(str(wav_path), dtype="float32")

    st = C.c_void_p()
    _ok(lib, lib.nemo_speech_diar_stream_open(model, C.byref(st)))
    try:
        blk = native_sr  # 1 s 块
        for i in range(0, len(y), blk):
            chunk = np.ascontiguousarray(y[i : i + blk])
            _ok(
                lib,
                lib.nemo_speech_diar_stream_push_f32(
                    st,
                    chunk.ctypes.data_as(C.POINTER(C.c_float)),
                    len(chunk),
                    native_sr,
                ),
            )
        _ok(lib, lib.nemo_speech_diar_stream_finish(st))
        return _pull_segments(lib, st)
    finally:
        lib.nemo_speech_diar_stream_close(st)


def assign_speaker(
    segments: list,
    diar_segs: list[DiarSegment],
) -> list:
    """按时间重叠给转写段落打说话人标签（就地修改 segment.speaker）。

    投票规则：覆盖时长最长的说话人获胜；无重叠则保持 None。
    """
    import collections

    for seg in segments:
        votes: collections.Counter = collections.Counter()
        for ds, de, dk in diar_segs:
            overlap = min(seg.end, de) - max(seg.start, ds)
            if overlap > 0:
                votes[dk] += overlap
        if votes:
            seg.speaker = f"speaker_{votes.most_common(1)[0][0]}"
    return segments
