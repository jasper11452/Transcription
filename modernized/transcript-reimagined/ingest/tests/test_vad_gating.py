"""`vad` 的门控：丢毛刺、并短停顿、采样点换秒（`RULE-028`）。

不加载真实模型：用同形状的桩对象验证单位换算与门控；真实模型的 smoke 测试
只在显式要求时执行（模型权重约 1.2MB，但加载会拖慢默认套件）。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.ingest import vad


@pytest.mark.rule("RULE-028")
def test_merge_gaps_bridges_short_pauses():
    assert vad.merge_gaps([(0.0, 10.0), (10.3, 20.0)], max_gap_s=0.4) == [(0.0, 20.0)]


@pytest.mark.rule("RULE-028")
def test_gap_of_exactly_max_gap_still_merges():
    assert vad.merge_gaps([(0.0, 10.0), (10.4, 20.0)], max_gap_s=0.4) == [(0.0, 20.0)]


@pytest.mark.rule("RULE-028")
def test_overlapping_spans_merge_to_the_later_end():
    assert vad.merge_gaps([(0.0, 10.0), (9.0, 12.0)], max_gap_s=0.4) == [(0.0, 12.0)]


@pytest.mark.rule("RULE-028")
def test_empty_detector_output_yields_empty_list():
    assert vad.merge_gaps([], max_gap_s=0.4) == []


@pytest.mark.rule("RULE-028")
def test_constants_match_the_rule_card():
    assert vad.MIN_SPEECH_S == 0.25
    assert vad.MAX_GAP_S == 0.4
    assert vad.DEFAULT_SAMPLE_RATE == 16_000


class _FakeOut:
    def __init__(self, timestamps, sample_rate=16_000):
        self.timestamps = timestamps
        if sample_rate is not None:
            self.sample_rate = sample_rate


class _FakeModel:
    def __init__(self, out):
        self._out = out

    def generate(self, _path):
        return self._out


def _install(monkeypatch, out, model_id="fake/vad"):
    monkeypatch.setattr(vad, "_model", _FakeModel(out))
    monkeypatch.setattr(vad, "_model_id", model_id)


@pytest.mark.rule("RULE-028")
def test_speech_spans_converts_samples_to_seconds_and_gates(monkeypatch):
    _install(
        monkeypatch,
        _FakeOut(
            [
                {"start": 0, "end": 16_000},       # 1.0s
                {"start": 16_480, "end": 16_800},  # 0.02s 毛刺 → 丢
                {"start": 17_280, "end": 32_000},  # 0.92s，与上一段间隔 0.08s → 并
                {"start": 64_000, "end": 80_000},  # 4–5s，间隔 2s → 独立
            ]
        ),
    )
    spans = vad.speech_spans("unused.wav", model_id="fake/vad")
    assert spans == [(0.0, 2.0), (4.0, 5.0)]


@pytest.mark.rule("RULE-028")
def test_missing_sample_rate_falls_back_to_16k(monkeypatch):
    _install(monkeypatch, _FakeOut([{"start": 0, "end": 8_000}], sample_rate=None))
    assert vad.speech_spans("unused.wav", model_id="fake/vad") == [(0.0, 0.5)]


@pytest.mark.rule("RULE-028")
def test_no_detections_yield_empty_list(monkeypatch):
    _install(monkeypatch, _FakeOut([]))
    assert vad.speech_spans("unused.wav", model_id="fake/vad") == []
