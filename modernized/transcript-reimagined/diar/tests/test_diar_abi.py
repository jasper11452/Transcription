"""ctypes ABI 验证：结构体布局、预设字符串、调用序列与真实库 smoke。

**这是 Q8 的第三项前置工作**：diar 是 ctypes 绑定到带构建哈希的第三方 dylib，
在此之前没有任何测试能真正执行它。这里用一个**编译出来的 stub dylib** 执行
真实的 ctypes 调用（不是只 import 模块），并用常量把构建哈希钉住；真实库与
模型存在时再跑一条 smoke。
"""

from __future__ import annotations

import ctypes as C
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest
from transcript_reimagined.domain import Segment

from transcript_reimagined.diar import (
    DEFAULT_DIAR_LIB,
    DEFAULT_DIAR_MODEL,
    DIAR_ABI_VERSION,
    assign_speaker,
    diarize,
    ffi,
)

STUB_C = r"""
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    size_t size;
    const char *model_path;
    int32_t gpu;
    const char *preset;
    int32_t chunk_frames;
    int32_t right_context_frames;
    int32_t left_context_frames;
    int32_t fifo_frames;
    int32_t spkcache_frames;
    int32_t update_period_frames;
} ModelCfg;

typedef struct {
    double start_time;
    double end_time;
    int32_t speaker;
} DiarSeg;

typedef struct { int magic; } Handle;

size_t stub_model_cfg_size(void) { return sizeof(ModelCfg); }
size_t stub_model_cfg_preset_offset(void) { return offsetof(ModelCfg, preset); }
size_t stub_diar_seg_size(void) { return sizeof(DiarSeg); }

const char *nemo_speech_asr_last_error(void) { return NULL; }
double nemo_speech_diar_seconds_per_frame(void) { return 0.01; }
int64_t nemo_speech_diar_frame_count(void *h) { (void)h; return 0; }

int nemo_speech_diar_create(const ModelCfg *cfg, void **out) {
    if (!cfg || !out) return 1;
    if (cfg->size != sizeof(ModelCfg)) return 2;
    if (!cfg->preset || strcmp(cfg->preset, "v3-offline") != 0) return 3;
    *out = calloc(1, sizeof(Handle));
    return *out ? 0 : 4;
}
void nemo_speech_diar_destroy(void *h) { free(h); }

int nemo_speech_diar_stream_open(void *model, void **out) {
    if (!model || !out) return 5;
    *out = calloc(1, sizeof(Handle));
    return *out ? 0 : 4;
}
int nemo_speech_diar_stream_push_f32(void *st, const float *pcm, size_t n, int32_t sr) {
    if (!st || (!pcm && n)) return 6;
    if (sr != 16000) return 7;
    return 0;
}
int nemo_speech_diar_stream_finish(void *st) { return st ? 0 : 6; }
int nemo_speech_diar_segments(void *st, void *unused, DiarSeg *buf, size_t cap, size_t *n) {
    (void)unused;
    if (!st || !n) return 6;
    if (!buf) { *n = 1; return 0; }
    if (cap < 1) { *n = 0; return 0; }
    buf[0].start_time = 0.0;
    buf[0].end_time = 1.0;
    buf[0].speaker = 1;
    *n = 1;
    return 0;
}
int nemo_speech_diar_stream_close(void *st) { free(st); return 0; }
"""


@pytest.fixture(scope="module")
def stub_lib(tmp_path_factory) -> Path:
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("没有 C 编译器，无法构建 ABI stub")
    work = tmp_path_factory.mktemp("diar-abi")
    source = work / "stub.c"
    source.write_text(STUB_C, encoding="utf-8")
    lib = work / "libstub_diar.dylib"
    proc = subprocess.run(
        [cc, "-shared", "-fPIC", "-O0", "-o", str(lib), str(source)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:  # pragma: no cover - 环境问题
        pytest.skip(f"stub 编译失败：{proc.stderr[-500:]}")
    return lib


def make_wav(path: Path, seconds: float = 0.5, rate: int = 16_000) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = b"".join(struct.pack("<h", 0) for _ in range(int(seconds * rate)))
        handle.writeframes(frames)
    return path


@pytest.mark.rule("RULE-013")
def test_abi_build_hash_is_pinned():
    """第三方 dylib 的构建哈希是硬编码耦合；升级 NeMoSpeech 必须同时改这里。"""
    assert DIAR_ABI_VERSION == "main-97a15af"
    # 哈希在 dylib 的安装目录里；模型目录是 NeMoSpeech/models（不带哈希）。
    assert DIAR_ABI_VERSION in DEFAULT_DIAR_LIB
    assert Path(DEFAULT_DIAR_LIB).name == "libnemo_speech_asr_c.dylib"
    assert Path(DEFAULT_DIAR_MODEL).name == "Nemotron-3-Diarization.q8_0.gguf"


@pytest.mark.rule("RULE-013")
def test_python_structs_match_the_c_layout(stub_lib: Path):
    lib = C.CDLL(str(stub_lib))
    lib.stub_model_cfg_size.restype = C.c_size_t
    lib.stub_model_cfg_preset_offset.restype = C.c_size_t
    lib.stub_diar_seg_size.restype = C.c_size_t

    assert C.sizeof(ffi._ModelCfg) == lib.stub_model_cfg_size()
    assert ffi._ModelCfg.preset.offset == lib.stub_model_cfg_preset_offset()
    assert C.sizeof(ffi._DiarSeg) == lib.stub_diar_seg_size()


@pytest.mark.rule("RULE-013")
def test_stub_library_runs_the_full_ctypes_path(stub_lib: Path, tmp_path: Path):
    """真正执行 ctypes：create → stream_open → push → finish → segments → close。"""
    wav = make_wav(tmp_path / "one.wav")
    segments = diarize(wav, lib_path=str(stub_lib), model_path="stub-model.gguf")
    assert segments == [(0.0, 1.0, 1)]


@pytest.mark.rule("RULE-013")
def test_the_preset_string_is_part_of_the_abi(stub_lib: Path):
    """预设字符串不是普通参数：stub 用 strcmp 校验它，证明它与库版本静默耦合。"""
    lib = C.CDLL(str(stub_lib))
    cfg = ffi._ModelCfg(
        C.sizeof(ffi._ModelCfg), b"model.gguf", 0, b"v2-online", 0, 0, 0, 0, 0, 0
    )
    handle = C.c_void_p()
    assert lib.nemo_speech_diar_create(C.byref(cfg), C.byref(handle)) != 0

    good = ffi._ModelCfg(
        C.sizeof(ffi._ModelCfg), b"model.gguf", 0, b"v3-offline", 0, 0, 0, 0, 0, 0
    )
    assert lib.nemo_speech_diar_create(C.byref(good), C.byref(handle)) == 0
    lib.nemo_speech_diar_destroy(handle)


@pytest.mark.rule("RULE-013")
def test_real_library_smoke_when_installed(tmp_path: Path):
    """真实 dylib 与模型存在时跑一次；不存在则跳过（不伪造通过）。"""
    lib_path, model_path = Path(DEFAULT_DIAR_LIB), Path(DEFAULT_DIAR_MODEL)
    if not lib_path.is_file() or not model_path.is_file():
        pytest.skip("本机未安装 NeMoSpeech dylib/模型")
    wav = make_wav(tmp_path / "real.wav", seconds=1.0)
    segments = diarize(wav, lib_path=str(lib_path), model_path=str(model_path))
    assert isinstance(segments, list)
    assert all(len(seg) == 3 for seg in segments)


@pytest.mark.rule("RULE-013")
def test_speaker_assignment_votes_by_longest_overlap():
    segments = [
        Segment(0.0, 2.0, "甲"),
        Segment(2.0, 4.0, "乙"),
        Segment(4.0, 6.0, "丙"),
    ]
    diar = [(0.0, 1.9, 1), (1.9, 3.8, 2), (3.8, 6.0, 1)]
    assign_speaker(segments, diar)
    assert [s.speaker for s in segments] == ["speaker_1", "speaker_2", "speaker_1"]


@pytest.mark.rule("RULE-013")
def test_speaker_assignment_leaves_uncovered_segments_none():
    segments = [Segment(10.0, 12.0, "旁白")]
    assign_speaker(segments, [(0.0, 1.0, 1)])
    assert segments[0].speaker is None
