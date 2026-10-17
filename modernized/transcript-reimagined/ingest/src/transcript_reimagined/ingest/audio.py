"""audio —— 探测 · 归一化 · 切。

**Phase 3 才落地**（``REIMAGINED_ARCHITECTURE.md`` §5：``ingest/`` 在 Phase 1 只含
``chunking.py``）。本模块只固化签名、常量与不变量，不提供半成品实现 ——
调用它会得到明确的 ``NotImplementedError``，而不是一个静默出错的结果。

归属理由（§2）：``audio`` 是**唯一碰 ffmpeg 的地方**，``probe`` 的事实
（``AudioInfo``）是切片规划的输入。本包不做落盘决策（产物位置在 ``orchestrate``），
但工作副本本身是 ``ingest`` 的产物（临时目录，结束即删 —— NFR-2：原文件只读）。

Phase 3 要满足的规则（规则卡 `BUSINESS_RULES.md`）：
- ``RULE-050`` 输入文件资格检查（``probe``：存在、非空、有音轨、时长可判定且非零）
- ``RULE-049`` 工作副本契约与校验（``verify``：ffmpeg 没报错 ≠ 文件正确）

**安全前置项（架构 §6，P6 之前必须落地，此处先记）**：ffmpeg/ffprobe 的
位置参数前必须加 ``--``（评估 CWE-88）。当前不可达，但一旦 CLI 入口能传相对名就可达。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..domain.models import AudioInfo

# 归一化参数：契约来自 `qwen3-asr-audio-input.md`（legacy `audio.py:23-24`）。
# 离线工作副本必须 16 kHz / 单声道 / pcm_s16le；在线走 mp3 64k 单声道。
WAV_ARGS: tuple[str, ...] = ("-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le")
MP3_ARGS: tuple[str, ...] = ("-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k")

#: 工作副本种类 → ``verify`` 期望的 (codec, sample_rate, channels)（`RULE-049`）。
EXPECTED_CODEC_BY_KIND: dict[str, tuple[str, int, int]] = {
    "wav16k": ("pcm_s16le", 16000, 1),
    "mp3_64k": ("mp3", 16000, 1),
}

#: 外部命令与超时（NFR-9）；探测/归一化不给无限等待。
PROBE_TIMEOUT_S = 60.0
NORMALIZE_TIMEOUT_S = 1800.0
CUT_TIMEOUT_S = 300.0
FFMPEG_BINARIES: tuple[str, ...] = ("ffmpeg", "ffprobe")


def require_ffmpeg() -> None:
    """缺少 ffmpeg/ffprobe 时**在开工之前**报错（`RULE-050` 的边界情形）。

    抛 ``InputError``（致命、不重试）—— 重试不会让一个没装的二进制出现。
    """
    raise NotImplementedError(
        "audio.require_ffmpeg 属 Phase 3（RULE-050）；Phase 1 的 ingest 只含 chunking"
    )


def probe(path: Path | str) -> AudioInfo:
    """用 ffprobe 读事实：时长、音轨、编码、采样率、声道（`RULE-050`）。

    命令形态（架构 §3.5）：``ffprobe -v error -print_format json -show_format -show_streams <src>``
    （Phase 3 实现时位置参数前加 ``--``）。

    不变量：
    - 时长取 format 级与 stream 级的**最大值**；
    - ``has_audio`` = 存在 ``codec_type == "audio"`` 的流；
    - 文件不存在 / 空文件 / 无音轨 / 时长不可判定或为 0 → 抛 ``InputError``，
      **不调用任何引擎、不花钱**；
    - 原文件只读（NFR-2）：本函数只读不写。
    """
    raise NotImplementedError("audio.probe 属 Phase 3（RULE-050）；Phase 1 的 ingest 只含 chunking")


def to_wav16k(src: Path | str, dst: Path | str) -> Path:
    """归一化成离线工作副本（16 kHz / 单声道 / pcm_s16le），返回产物路径。"""
    raise NotImplementedError(
        "audio.to_wav16k 属 Phase 3（RULE-049 / RULE-050）；Phase 1 的 ingest 只含 chunking"
    )


def to_mp3_64k(src: Path | str, dst: Path | str) -> Path:
    """归一化成在线工作副本（16 kHz / 单声道 / mp3 64k），返回产物路径。"""
    raise NotImplementedError(
        "audio.to_mp3_64k 属 Phase 3（RULE-049 / RULE-050）；Phase 1 的 ingest 只含 chunking"
    )


def cut(
    src: Path | str,
    dst: Path | str,
    *,
    start: float,
    end: float,
    codec_args: Sequence[str],
) -> Path:
    """按 ``[start, end)`` 切出一片（重编码以拿到精确边界）。

    命令形态（架构 §3.5）：``ffmpeg -y -hide_banner -loglevel error -ss <start> -to <end> -i <src> <codec> <dst>``。
    调用方是 ``orchestrate``，输入是 ``chunking.plan_chunks`` 的计划 —— 这就是
    ``ingest`` 与 ``orchestrate`` 之间那条边的实体。
    """
    raise NotImplementedError(
        "audio.cut 属 Phase 3（RULE-011 的物理不变量在切片侧成立，切出精确边界在这里）"
    )


def verify(path: Path | str, kind: str) -> AudioInfo:
    """校验工作副本真的符合契约（`RULE-049`）。

    「ffmpeg 没报错」**不是**证据：以**重新探测**产物为准，codec / 采样率 / 声道
    三者逐个比对，任一不符（例如 ``channels=2!=1``）就抛 ``InputError``；
    产物为空或不存在同样抛错。``kind`` 未知时抛错而不是跳过校验。
    """
    raise NotImplementedError(
        "audio.verify 属 Phase 3（RULE-049）；Phase 1 的 ingest 只含 chunking"
    )
