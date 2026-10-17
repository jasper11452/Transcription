"""本服务承载、但归属后续阶段的规则 —— 预期失败（``xfail``），按规则 ID 打标。

工作纪律：**不静默跳过**。这些规则是行为契约的一部分（``AI_NATIVE_SPEC.md`` §5
的规则卡），只是实现阶段未到；每个用例都写明了它会因为什么失败、由哪个阶段兑现。

| 规则 | 内容 | 为什么现在不可执行 | 兑现阶段 |
|---|---|---|---|
| ``RULE-028`` | 语音活动门控：丢毛刺、并短停顿 | ``vad.py`` 属 P3（架构 §5：Phase 1 的 ``ingest`` 只含 ``chunking``） | P3 入料与后处理 |
| ``RULE-049`` | 工作副本契约与校验 | ``audio.py`` 属 P3（需要 ffmpeg 子进程） | P3 入料与后处理 |
| ``RULE-050`` | 输入文件资格检查 | ``audio.py`` 属 P3（需要 ffprobe 子进程） | P3 入料与后处理 |

两条硬要求来自本包自己的边界，兑现时不得违反：

1. ``audio`` 是**唯一碰 ffmpeg 的地方**（架构 §2），且工作副本走临时目录、
   原文件只读（NFR-2）。
2. ffmpeg/ffprobe 的位置参数前必须加 ``--``（架构 §6，CWE-88）。

夹具里**没有**任何真实录音或凭据：用同形状的临时文件与假路径。真实样例音频
按项目惯例用 ``say`` 生成，私有素材不进仓库。
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.xfail(
        strict=False,
        reason="本文件全部用例的模块属 Phase 3（audio.py / vad.py）；Phase 1 的 ingest 只含 chunking",
    ),
]


# --------------------------------------------------------------------------- RULE-028


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_micro_spans_are_dropped_and_short_pauses_bridged() -> None:
    """判据：0.1s 毛刺丢掉；间隔 0.3s 的两段语音并成一段；结果按起点排序。"""
    from transcript_reimagined.ingest import vad

    raw = [(0.0, 10.0), (10.2, 10.3), (10.6, 20.0)]
    # 采样点输入 → 秒，再走门控；核心是 merge_gaps 与丢毛刺两条
    assert vad.merge_gaps([(0.0, 10.0), (10.3, 20.0)], max_gap_s=vad.MAX_GAP_S) == [(0.0, 20.0)]
    assert raw  # 输入形状留在这里，实现时以 model.generate 的输出替代


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_gap_of_exactly_max_gap_still_merges() -> None:
    """边界情形：间隔恰好等于 ``max_gap_s`` 也并（闭区间，判定是 ``<=``）。"""
    from transcript_reimagined.ingest import vad

    assert vad.merge_gaps([(0.0, 10.0), (10.4, 20.0)], max_gap_s=0.4) == [(0.0, 20.0)]


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_overlapping_spans_merge_to_the_later_end() -> None:
    """重叠的区间用 ``max(last_end, end)`` 收紧 —— 不能因为重叠把结束时间往回拉。"""
    from transcript_reimagined.ingest import vad

    assert vad.merge_gaps([(0.0, 10.0), (9.0, 12.0)], max_gap_s=0.4) == [(0.0, 12.0)]


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_empty_detector_output_yields_an_empty_span_list() -> None:
    """检测器没有输出 → ``[]``（切片规划会把「没有语音区间」当连续语音处理）。"""
    from transcript_reimagined.ingest import vad

    assert vad.merge_gaps([], max_gap_s=0.4) == []


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_min_speech_and_gap_thresholds_match_the_rule_card() -> None:
    """``min_speech_s = 0.25``、``max_gap_s = 0.4``、采样率默认 16000（常量不得放宽）。"""
    from transcript_reimagined.ingest import vad

    assert vad.MIN_SPEECH_S == 0.25
    assert vad.MAX_GAP_S == 0.4
    assert vad.DEFAULT_SAMPLE_RATE == 16_000
    # 常量对还不够：门控本身必须可执行
    assert vad.merge_gaps([(0.0, 1.0)], max_gap_s=vad.MAX_GAP_S) == [(0.0, 1.0)]


@pytest.mark.rule("RULE-028")
@pytest.mark.pending_implementation("RULE-028")
def test_rule_028_speech_spans_converts_samples_to_seconds(tmp_path) -> None:
    """VAD 输出是**采样点**：单位混淆会让整个切片计划错位，所以换算必须被断言。"""
    from transcript_reimagined.ingest import vad

    # 同形状假路径：不存在的音频文件；模型桩由 Phase 3 的测试提供。
    wav = tmp_path / "work-16k.wav"
    wav.write_bytes(b"")
    spans = vad.speech_spans(wav, model_id="fake/vad-model")
    assert all(isinstance(span, tuple) and len(span) == 2 for span in spans)


# --------------------------------------------------------------------------- RULE-049


@pytest.mark.rule("RULE-049")
@pytest.mark.pending_implementation("RULE-049")
def test_rule_049_matching_working_copy_passes_silently(tmp_path) -> None:
    """三项（codec / 采样率 / 声道）全对时静默通过。"""
    from transcript_reimagined.ingest import audio

    produced = tmp_path / "work.wav"
    produced.write_bytes(b"\x00" * 64)
    info = audio.verify(produced, "wav16k")
    assert (info.codec, info.sample_rate, info.channels) == ("pcm_s16le", 16_000, 1)


@pytest.mark.rule("RULE-049")
@pytest.mark.pending_implementation("RULE-049")
def test_rule_049_channels_mismatch_is_reported_with_a_listing(tmp_path) -> None:
    """「ffmpeg 没报错」不是证据：声道不符（``channels=2!=1``）必须抛 ``InputError``。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    produced = tmp_path / "work.wav"
    produced.write_bytes(b"\x00" * 64)
    with pytest.raises(InputError, match="channels=2!=1"):
        audio.verify(produced, "wav16k")


@pytest.mark.rule("RULE-049")
@pytest.mark.pending_implementation("RULE-049")
def test_rule_049_empty_or_missing_output_raises(tmp_path) -> None:
    """产物为空或不存在都抛错 —— 不能把「没有文件」当成「符合契约」。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(InputError):
        audio.verify(empty, "wav16k")
    with pytest.raises(InputError):
        audio.verify(tmp_path / "absent.wav", "wav16k")


@pytest.mark.rule("RULE-049")
@pytest.mark.pending_implementation("RULE-049")
def test_rule_049_unknown_kind_raises_instead_of_skipping_verification(tmp_path) -> None:
    """未知种类抛错，而不是「校验不了就放过」—— 放过等于没有校验。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    produced = tmp_path / "work.bin"
    produced.write_bytes(b"\x00" * 64)
    with pytest.raises(InputError):
        audio.verify(produced, "flac_lossless")


@pytest.mark.rule("RULE-049")
@pytest.mark.pending_implementation("RULE-049")
def test_rule_049_normalization_never_rewrites_the_original(tmp_path) -> None:
    """NFR-2：原文件只读 —— 归一化的输入路径不会被改写。"""
    from transcript_reimagined.ingest import audio

    source = tmp_path / "original.m4a"
    source.write_bytes(b"ORIGINAL-BYTES")
    audio.to_wav16k(source, tmp_path / "work.wav")
    assert source.read_bytes() == b"ORIGINAL-BYTES"


# --------------------------------------------------------------------------- RULE-050


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
def test_rule_050_video_only_file_fails_with_no_audio_track(tmp_path) -> None:
    """只有视频流 → ``InputError('no audio track')``，不调引擎、不花钱。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    video_only = tmp_path / "clip.mp4"
    video_only.write_bytes(b"\x00" * 64)
    with pytest.raises(InputError, match="no audio track"):
        audio.probe(video_only)


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("missing.m4a", None, "file does not exist"),
        ("empty.m4a", b"", "file is empty"),
    ],
)
def test_rule_050_missing_and_empty_files_fail_before_any_work(
    tmp_path, filename: str, payload: bytes | None, message: str
) -> None:
    """不存在 / 空文件在开工之前就失败，且失败原因可分辨。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    path = tmp_path / filename
    if payload is not None:
        path.write_bytes(payload)
    with pytest.raises(InputError, match=message):
        audio.probe(path)


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
def test_rule_050_zero_or_unknown_duration_is_rejected(tmp_path) -> None:
    """时长不可判定或为 0 → ``InputError('duration could not be determined')``。"""
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    unreadable = tmp_path / "no-duration.m4a"
    unreadable.write_bytes(b"\x00" * 64)
    with pytest.raises(InputError, match="duration could not be determined"):
        audio.probe(unreadable)


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
def test_rule_050_duration_takes_the_max_of_format_and_stream(tmp_path) -> None:
    """时长取 format 级与 stream 级的**最大值** —— 取小会让计划短于真实录音。"""
    from transcript_reimagined.ingest import audio

    mixed = tmp_path / "mixed.m4a"
    mixed.write_bytes(b"\x00" * 64)
    info = audio.probe(mixed)
    assert info.duration > 0
    assert info.has_audio is True
    assert info.megabytes == pytest.approx(info.size_bytes / 1_000_000)


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
def test_rule_050_missing_binaries_are_reported_before_any_work() -> None:
    """缺 ffmpeg/ffprobe 时在开工之前抛 ``InputError``（致命、不重试）。

    重试不会让一个没装的二进制出现 —— 所以这不是 ``RecoverableError``。
    当前 ``require_ffmpeg`` 抛的是 ``NotImplementedError``（Phase 3 占位），
    本用例在落地后才会通过。
    """
    from transcript_reimagined.domain import InputError

    from transcript_reimagined.ingest import audio

    with pytest.raises(InputError, match="ffmpeg"):
        audio.require_ffmpeg()


@pytest.mark.rule("RULE-050")
@pytest.mark.pending_implementation("RULE-050")
def test_rule_050_external_commands_put_option_terminator_before_positional_args() -> None:
    """安全前置项（架构 §6，CWE-88）：位置参数前必须加 ``--``。

    这条**不是** legacy 行为，是重建时补的加固项；它必须在 Phase 3 落地时一起兑现，
    否则一个以 ``-`` 开头的相对名就能变成 ffmpeg 的选项。
    """
    import inspect

    from transcript_reimagined.ingest import audio

    source = inspect.getsource(audio)
    for call_site in ("probe", "to_wav16k", "to_mp3_64k", "cut"):
        assert call_site in source
    assert '"--"' in source or "'--'" in source, (
        "ffmpeg/ffprobe 的位置参数前必须加 `--`（Phase 3 落地时补上）"
    )
