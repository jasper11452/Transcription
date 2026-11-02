"""音频前置：探测、归一化、切片。

契约（来自 `qwen3-asr-audio-input.md`）：
- 离线工作副本必须 **16 kHz / 单声道 / pcm_s16le**；
- 在线工作副本走 **mp3 64k 单声道**（mai-transcribe-2 会直接拒 m4a；mp3 体积小到能整段送）；
- **原文件永不改动**，工作副本是临时品。

任何一步失败都必须抛 InputError，不许返回空结果冒充成功。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .errors import InputError
from .models import AudioInfo

WAV_ARGS = ("-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le")
MP3_ARGS = ("-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k")


def _run(cmd: Sequence[str], *, what: str) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise InputError(f"缺少外部命令：{cmd[0]}（{what}）") from exc
    if proc.returncode != 0:
        tail = " / ".join(proc.stderr.strip().splitlines()[-3:])[:400]
        raise InputError(f"{what}失败：{tail or f'退出码 {proc.returncode}'}")
    return proc


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise InputError(f"缺少 {tool}，请先安装 ffmpeg")


def probe(path: Path | str) -> AudioInfo:
    """用 ffprobe 读事实：时长、音轨、编码、采样率、声道。"""
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
            str(src),
        ],
        what=f"探测 {src.name}",
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
            str(dst),
        ],
        what=what,
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise InputError(f"{what}产出空文件：{dst.name}")
    return dst


def to_wav16k(src: Path | str, dst: Path | str) -> Path:
    """离线工作副本。"""
    return _normalize(Path(src), Path(dst), WAV_ARGS, what=f"归一化为 16k wav（{Path(src).name}）")


def to_mp3_64k(src: Path | str, dst: Path | str) -> Path:
    """在线工作副本。"""
    return _normalize(Path(src), Path(dst), MP3_ARGS, what=f"归一化为 64k mp3（{Path(src).name}）")


def cut(
    src: Path | str, dst: Path | str, start: float, end: float, *, kind: str = "wav16k"
) -> Path:
    """从已归一化的文件上切一段（切片单位）。重编码以保证边界精确。"""
    if end <= start:
        raise InputError(f"切片区间非法：{start}–{end}")
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
            str(dst),
        ],
        what=f"切片 {start:.1f}–{end:.1f}s",
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise InputError(f"切片产出空文件：{dst.name}")
    return dst


def verify(path: Path | str, kind: str) -> AudioInfo:
    """校验工作副本是否真的符合契约（不靠"ffmpeg 没报错"来推断）。"""
    info = probe(path)
    expect = {"wav16k": ("pcm_s16le", 16_000, 1), "mp3_64k": ("mp3", 16_000, 1)}.get(kind)
    if expect is None:
        raise InputError(f"未知的校验类型：{kind}")
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
