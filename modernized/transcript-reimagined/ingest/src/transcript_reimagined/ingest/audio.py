"""音频前置：探测、归一化、切片。

契约（来自 `qwen3-asr-audio-input.md`）：
- 离线工作副本必须 **16 kHz / 单声道 / pcm_s16le**；
- 在线工作副本走 **mp3 64k 单声道**（mai-transcribe-2 会直接拒 m4a；mp3 体积小到能整段送）；
- **原文件永不改动**，工作副本是临时品（NFR-2）。

任何一步失败都必须抛 InputError，不许返回空结果冒充成功。

重建自 ``legacy/transcript/src/transcript/audio.py``。规则：
`RULE-049`（工作副本契约与校验）、`RULE-050`（输入资格检查）。
**安全加固（已署名）**：位置参数前加 ``--``（CWE-88），并给外部命令加超时（NFR-9）。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from transcript_reimagined.domain import AudioInfo, InputError

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


def _run(cmd: Sequence[str], *, what: str, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise InputError(f"缺少外部命令：{cmd[0]}（{what}）") from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError(f"{what}超时（>{timeout:.0f}s）") from exc
    if proc.returncode != 0:
        tail = " / ".join(proc.stderr.strip().splitlines()[-3:])[:400]
        raise InputError(f"{what}失败：{tail or f'退出码 {proc.returncode}'}")
    return proc


def require_ffmpeg() -> None:
    """缺少 ffmpeg/ffprobe 时**在开工之前**报错（`RULE-050` 的边界情形）。

    抛 ``InputError``（致命、不重试）—— 重试不会让一个没装的二进制出现。
    """
    for tool in FFMPEG_BINARIES:
        if not shutil.which(tool):
            raise InputError(f"缺少 {tool}，请先安装 ffmpeg")


def probe(path: Path | str) -> AudioInfo:
    """用 ffprobe 读事实：时长、音轨、编码、采样率、声道（`RULE-050`）。

    不变量：
    - 时长取 format 级与 stream 级的**最大值**；
    - ``has_audio`` = 存在 ``codec_type == "audio"`` 的流；
    - 文件不存在 / 空文件 / 无音轨 / 时长不可判定或为 0 → 抛 ``InputError``，
      **不调用任何引擎、不花钱**；
    - 原文件只读（NFR-2）：本函数只读不写。
    """
    src = Path(path)
    if not src.exists():
        raise InputError(f"文件不存在：{src}")
    if src.stat().st_size == 0:
        raise InputError(f"文件为空：{src}")

    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "--",
            str(src),
        ],
        what=f"探测 {src.name}",
        timeout=PROBE_TIMEOUT_S,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise InputError(f"ffprobe 输出无法解析：{src.name}") from exc

    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = 0.0
    for source in (data.get("format") or {}, audio or {}):
        for key in ("duration", "Duration"):
            with contextlib.suppress(TypeError, ValueError):
                duration = max(duration, float(source.get(key) or 0))

    info = AudioInfo(
        path=src,
        duration=duration,
        size_bytes=src.stat().st_size,
        codec=(audio or {}).get("codec_name"),
        sample_rate=int((audio or {}).get("sample_rate") or 0) or None,
        channels=(audio or {}).get("channels"),
        has_audio=audio is not None,
    )
    if not info.has_audio:
        raise InputError(f"没有音频轨：{src.name}（只有视频或空容器都算不合格输入）")
    if info.duration <= 0:
        raise InputError(f"时长无法确定或为零：{src.name}")
    return info


def _normalize(src: Path, dst: Path, codec_args: Sequence[str], *, what: str) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-vn",
            *codec_args,
            "--",
            str(dst),
        ],
        what=what,
        timeout=NORMALIZE_TIMEOUT_S,
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise InputError(f"{what}产出空文件：{dst.name}")
    return dst


def to_wav16k(src: Path | str, dst: Path | str) -> Path:
    """离线工作副本。"""
    return _normalize(
        Path(src), Path(dst), WAV_ARGS, what=f"归一化为 16k wav（{Path(src).name}）"
    )


def to_mp3_64k(src: Path | str, dst: Path | str) -> Path:
    """在线工作副本。"""
    return _normalize(
        Path(src), Path(dst), MP3_ARGS, what=f"归一化为 64k mp3（{Path(src).name}）"
    )


def cut(
    src: Path | str,
    dst: Path | str,
    start: float | None = None,
    end: float | None = None,
    *,
    kind: str = "wav16k",
    codec_args: Sequence[str] | None = None,
) -> Path:
    """从已归一化的文件上切一段（切片单位）。重编码以保证边界精确。

    同时接受两种调用形态：
    - 遗留形态 ``cut(src, dst, start, end, kind="wav16k")``；
    - 脚手架形态 ``cut(src, dst, start=..., end=..., codec_args=WAV_ARGS)``。
    """
    if start is None or end is None:
        raise InputError("切片区间非法：start/end 不能为空")
    if end <= start:
        raise InputError(f"切片区间非法：{start}–{end}")
    if codec_args is None:
        codec_args = {"wav16k": WAV_ARGS, "mp3_64k": MP3_ARGS}.get(kind)
        if codec_args is None:
            raise InputError(f"未知的切片类型：{kind}")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            *codec_args,
            "--",
            str(dst),
        ],
        what=f"切片 {start:.1f}–{end:.1f}s",
        timeout=CUT_TIMEOUT_S,
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise InputError(f"切片产出空文件：{dst.name}")
    return dst


def verify(path: Path | str, kind: str) -> AudioInfo:
    """校验工作副本是否真的符合契约（`RULE-049`）。

    「ffmpeg 没报错」**不是**证据：以**重新探测**产物为准，codec / 采样率 / 声道
    三者逐个比对，任一不符（例如 ``channels=2!=1``）就抛 ``InputError``；
    产物为空或不存在同样抛错。``kind`` 未知时抛错而不是跳过校验。
    """
    expect = EXPECTED_CODEC_BY_KIND.get(kind)
    if expect is None:
        raise InputError(f"未知的校验类型：{kind}")
    info = probe(path)
    codec, rate, channels = expect
    problems = []
    if info.codec != codec:
        problems.append(f"codec={info.codec}≠{codec}")
    if info.sample_rate != rate:
        problems.append(f"sample_rate={info.sample_rate}≠{rate}")
    if info.channels != channels:
        problems.append(f"channels={info.channels}≠{channels}")
    if problems:
        raise InputError(f"{Path(path).name} 不符合 {kind} 契约：" + "，".join(problems))
    return info
