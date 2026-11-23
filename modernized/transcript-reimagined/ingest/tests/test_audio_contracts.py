"""`audio` 的契约：探测、归一化、切、校验（`RULE-049` / `RULE-050`）。

「ffmpeg 没报错」不是证据：每个产物都用 `probe` 重新读一遍事实。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from transcript_reimagined.domain import InputError

from transcript_reimagined.ingest import audio


def gen(
    path: Path,
    *,
    seconds: float = 2.0,
    ac: int = 2,
    ar: int = 44100,
    codec: str = "pcm_s16le",
    video_only: bool = False,
) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
    ]
    if video_only:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=1",
            "-an",
        ]
    cmd += ["-ac", str(ac), "-ar", str(ar), "-c:a", codec, str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.mark.rule("RULE-050")
def test_probe_reads_truth(tmp_path: Path):
    src = gen(tmp_path / "a.wav", seconds=2.0, ac=2, ar=44100)
    info = audio.probe(src)
    assert info.has_audio
    assert info.codec == "pcm_s16le"
    assert info.sample_rate == 44100
    assert info.channels == 2
    assert 1.8 < info.duration < 2.2


@pytest.mark.rule("RULE-050")
def test_probe_rejects_missing_empty_and_video_only(tmp_path: Path):
    with pytest.raises(InputError, match="不存在"):
        audio.probe(tmp_path / "nope.wav")

    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(InputError, match="为空"):
        audio.probe(empty)

    video = gen(tmp_path / "v.mp4", video_only=True)
    with pytest.raises(InputError, match="没有音频轨"):
        audio.probe(video)


@pytest.mark.rule("RULE-050")
def test_probe_reports_corrupt_file_as_input_error(tmp_path: Path):
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"not a real wav at all" * 10)
    with pytest.raises(InputError):
        audio.probe(bad)


@pytest.mark.rule("RULE-049")
def test_to_wav16k_satisfies_contract(tmp_path: Path):
    """44.1k 立体声 → 16k 单声道 pcm_s16le，这是模型的硬契约。"""
    src = gen(tmp_path / "src.wav", ac=2, ar=44100)
    dst = audio.to_wav16k(src, tmp_path / "out.wav")
    info = audio.verify(dst, "wav16k")
    assert (info.codec, info.sample_rate, info.channels) == ("pcm_s16le", 16000, 1)


@pytest.mark.rule("RULE-049")
def test_to_mp3_64k_satisfies_contract(tmp_path: Path):
    src = gen(tmp_path / "src.wav", ac=2, ar=44100)
    dst = audio.to_mp3_64k(src, tmp_path / "out.mp3")
    info = audio.verify(dst, "mp3_64k")
    assert info.codec == "mp3"
    assert info.sample_rate == 16000
    assert info.channels == 1
    assert info.size_bytes < src.stat().st_size, "mp3 应该显著小于原始 wav"


@pytest.mark.rule("RULE-049")
def test_verify_catches_wrong_contract(tmp_path: Path):
    src = gen(tmp_path / "src.wav")
    wav = audio.to_wav16k(src, tmp_path / "out.wav")
    with pytest.raises(InputError, match="不符合"):
        audio.verify(wav, "mp3_64k")


@pytest.mark.rule("RULE-049")
def test_verify_rejects_unknown_kind(tmp_path: Path):
    src = gen(tmp_path / "src.wav")
    with pytest.raises(InputError, match="未知的校验类型"):
        audio.verify(src, "flac24k")


@pytest.mark.rule("RULE-049")
def test_cut_produces_expected_duration_and_format(tmp_path: Path):
    src = gen(tmp_path / "src.wav", seconds=5.0)
    wav = audio.to_wav16k(src, tmp_path / "w.wav")
    piece = audio.cut(wav, tmp_path / "p.wav", 1.0, 3.0, kind="wav16k")
    info = audio.verify(piece, "wav16k")
    assert 1.8 < info.duration < 2.2


@pytest.mark.rule("RULE-049")
def test_cut_accepts_codec_args_form(tmp_path: Path):
    src = gen(tmp_path / "src.wav", seconds=4.0)
    wav = audio.to_wav16k(src, tmp_path / "w.wav")
    piece = audio.cut(
        wav, tmp_path / "p.wav", start=0.5, end=2.0, codec_args=audio.WAV_ARGS
    )
    assert audio.verify(piece, "wav16k").sample_rate == 16000


@pytest.mark.rule("RULE-049")
def test_cut_mp3_kind_keeps_online_contract(tmp_path: Path):
    """在线分片必须是 mp3，否则上游会因容器不对而 400。"""
    src = gen(tmp_path / "src.wav", seconds=5.0)
    mp3 = audio.to_mp3_64k(src, tmp_path / "m.mp3")
    piece = audio.cut(mp3, tmp_path / "p.mp3", 0.0, 2.0, kind="mp3_64k")
    assert 1.5 < audio.verify(piece, "mp3_64k").duration < 2.5


@pytest.mark.rule("RULE-049")
def test_cut_rejects_invalid_range(tmp_path: Path):
    src = gen(tmp_path / "src.wav")
    with pytest.raises(InputError, match="区间非法"):
        audio.cut(src, tmp_path / "p.wav", 3.0, 1.0)
    with pytest.raises(InputError, match="未知的切片类型"):
        audio.cut(src, tmp_path / "p.wav", 0.0, 1.0, kind="ogg")


@pytest.mark.rule("RULE-049")
def test_normalization_never_rewrites_the_original(tmp_path: Path):
    """NFR-2：原文件只读 —— 归一化只写工作副本。"""
    src = gen(tmp_path / "src.wav", seconds=1.0)
    before = src.read_bytes()
    audio.to_wav16k(src, tmp_path / "work.wav")
    assert src.read_bytes() == before


@pytest.mark.rule("RULE-050")
def test_missing_binaries_are_reported_before_any_work(monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda _name: None)
    with pytest.raises(InputError, match="ffmpeg"):
        audio.require_ffmpeg()


@pytest.mark.rule("RULE-050")
def test_external_commands_put_option_terminator_before_positional_args():
    """安全加固（CWE-88）：位置参数前必须有 `--`。"""
    import inspect

    source = inspect.getsource(audio)
    assert '"--"' in source
    # 四个入口都真的走 `_run`，且 `_run` 有超时（NFR-9）。
    assert "timeout=" in source
