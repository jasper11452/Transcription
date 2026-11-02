"""切片规划的单测。切片错了后面全错，所以这里覆盖边界与不变式。"""

from __future__ import annotations

from transcript.chunking import plan_chunks


def test_short_audio_single_chunk():
    chunks = plan_chunks([(0.0, 5.0)], 5.0, min_s=30, max_s=120)
    assert len(chunks) == 1
    assert (chunks[0].start, chunks[0].end) == (0.0, 5.0)


def test_no_spans_tiles_by_max_for_long_audio():
    """VAD 什么都没检出时，长音频必须按 max_s 硬切，不能整段一片。"""
    chunks = plan_chunks([], 300.0, min_s=30, max_s=120)
    assert len(chunks) == 3
    assert chunks[-1].end == 300.0
    assert all(c.duration <= 120.0 + 0.01 for c in chunks)


def test_no_spans_short_audio_is_one_chunk():
    chunks = plan_chunks([], 20.0, min_s=30, max_s=120)
    assert len(chunks) == 1
    assert chunks[0].end == 20.0


def test_chunk_never_exceeds_max_even_with_overlap():
    """不变量：片长（含外扩的重叠）绝不能超过 max_s。

    实测反例（修复前）：两段 200s 语音 + 1s 静音、max_s=120 时会切出 200.75s 的片；
    百炼场景（max_s=300）会切出 300.25s，直接超过上游 300s 硬限。
    """
    cases = [
        ([(0.0, 200.0), (201.0, 400.0)], 400.0, 30.0, 120.0, 0.5),
        ([(0.0, 320.0)], 320.0, 30.0, 300.0, 0.5),
        ([], 700.0, 30.0, 120.0, 0.5),
        ([(int(i * 10), int(i * 10) + 9) for i in range(40)], 400.0, 30.0, 120.0, 0.5),
    ]
    for spans, duration, min_s, max_s, overlap in cases:
        chunks = plan_chunks(
            [(float(a), float(b)) for a, b in spans],
            duration,
            min_s=min_s,
            max_s=max_s,
            overlap_s=overlap,
        )
        assert chunks, f"不能切出空计划：{spans}"
        for c in chunks:
            assert c.duration <= max_s + 1e-6, f"{c.duration:.2f}s 超过上限 {max_s}s"
        assert chunks[0].start == 0.0
        assert chunks[-1].end == duration
        for prev, cur in zip(chunks, chunks[1:], strict=False):
            assert cur.start < prev.end, "相邻片必须重叠"


def test_long_continuous_speech_hard_cuts_at_max():
    """连续语音没有可用间隙时必须按 max_s 硬切，不能无限累积。"""
    chunks = plan_chunks([(0.0, 400.0)], 400.0, min_s=30, max_s=120, overlap_s=0.0)
    assert len(chunks) > 1
    assert all(c.duration <= 120.0 + 0.01 for c in chunks)
    assert chunks[-1].end == 400.0


def test_audio_that_fits_in_one_chunk_is_not_split():
    """装得下就不切。

    修复前这里被切成 3 片（每片只有 30s）：94s 音频、上限 120s 本来一片就够，
    多切两片等于多两次引擎调用（在线就是多花钱）。旧断言把过度切分当成了期望值。
    """
    spans = [(0.0, 30.0), (32.0, 62.0), (64.0, 94.0)]
    chunks = plan_chunks(spans, 94.0, min_s=30, max_s=120, overlap_s=0.0)
    assert len(chunks) == 1
    assert (chunks[0].start, chunks[0].end) == (0.0, 94.0)


def test_cuts_prefer_silence_gaps():
    """需要切的时候（连续语音够长），切点必须落在静音间隙里，而不是语音中间。"""
    spans = [(0.0, 100.0), (102.0, 200.0), (202.0, 300.0)]
    chunks = plan_chunks(spans, 300.0, min_s=30, max_s=120, overlap_s=0.0)
    assert len(chunks) > 1, "300s 音频在上限 120s 下必须被切开"
    gaps = [(100.0, 102.0), (200.0, 202.0)]
    for cut in [c.end for c in chunks[:-1]]:
        assert any(s < cut < e for s, e in gaps), f"切点 {cut} 不在静音间隙内"
    for c in chunks:
        assert c.duration <= 120.0 + 1e-6


def test_chunks_cover_timeline_and_have_overlap():
    """不变式：必须无缝隙覆盖 [0, duration]，相邻片必须有重叠。"""
    spans = [(i * 10.0, i * 10.0 + 9.0) for i in range(40)]
    duration = 400.0
    chunks = plan_chunks(spans, duration, min_s=30, max_s=120, overlap_s=0.5)

    assert chunks[0].start == 0.0
    assert chunks[-1].end == duration
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert prev.end - cur.start > 0, "相邻片必须重叠，否则边界会丢字"
    for c in chunks:
        assert c.start < c.end
        assert c.start >= 0.0 and c.end <= duration


def test_indices_are_sequential():
    chunks = plan_chunks([(0.0, 300.0)], 300.0, min_s=30, max_s=60, overlap_s=0.4)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_small_gaps_do_not_become_cuts():
    """句间 0.3s 停顿不该切，否则每句话都成一片。"""
    spans = [(0.0, 20.0), (20.3, 40.0), (40.3, 60.0), (60.3, 80.0)]
    chunks = plan_chunks(spans, 80.0, min_s=30, max_s=120, overlap_s=0.0)
    assert len(chunks) <= 3
