"""端到端冒烟：真实模型、真实 ffmpeg、真实 VAD，跑通离线路径。

`-m smoke` 才跑（默认 pytest 不跑）：它要加载约 4GB 模型，秒级~分钟级耗时。
它验证的正是 spec 第 10 节的验收判据里"能自动验证的那部分"：
文本质量、时间轴合法性、内容不丢、产物结构。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from transcript.align import normalize_for_compare
from transcript.config import Config
from transcript.pipeline import Pipeline
from transcript.store import Store

pytestmark = pytest.mark.smoke

DATA = Path(__file__).parent / "data"
SRT_TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")

# 样例音频是用 `say -v Tingting` 生成的确定性内容
EXPECTED_PHRASES = ["转录工具冒烟测试", "离线转写", "在线字幕", "专有名词"]


@pytest.fixture(scope="module")
def offline_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    work = tmp_path_factory.mktemp("smoke")
    config = Config(
        config_path=work / "config.env",
        state_db=work / "state.db",
        output_dir=work / "output",
        glossary_path=work / "glossary.txt",
    )
    store = Store(config.state_db)
    events: list = []
    pipeline = Pipeline(config, store, on_event=events.append)
    source = work / "smoke.wav"
    source.write_bytes((DATA / "smoke.wav").read_bytes())

    result = pipeline.run(source, mode="offline", artifact="srt", language="zh")
    return {"result": result, "store": store, "events": events, "source": source}


def _to_seconds(match: re.Match[str]) -> tuple[float, float]:
    vals = [int(v) for v in match.groups()]
    start = vals[0] * 3600 + vals[1] * 60 + vals[2] + vals[3] / 1000
    end = vals[4] * 3600 + vals[5] * 60 + vals[6] + vals[7] / 1000
    return start, end


def test_offline_run_succeeds(offline_run: dict):
    result = offline_run["result"]
    assert result.status == "done", result.error
    assert result.txt_path and result.txt_path.exists()
    assert result.srt_path and result.srt_path.exists()
    assert result.raw_path and result.raw_path.exists()


def test_transcript_keeps_all_expected_phrases(offline_run: dict):
    """质量判据的第一层：内容不能缺（专名以外的字词应全部到位）。"""
    text = offline_run["result"].txt_path.read_text(encoding="utf-8")
    normalized = normalize_for_compare(text)
    for phrase in EXPECTED_PHRASES:
        assert phrase in normalized, f"转写丢了「{phrase}」：{text}"


def test_transcript_has_punctuation(offline_run: dict):
    """离线文本取 Qwen3-ASR，必须带标点（这正是选它而不是 whisper 的理由）。"""
    text = offline_run["result"].txt_path.read_text(encoding="utf-8")
    assert any(mark in text for mark in "。！？，"), "标点缺失，说明文本来源不是 Qwen3-ASR"


def test_srt_is_structurally_valid(offline_run: dict):
    srt = offline_run["result"].srt_path.read_text(encoding="utf-8")
    blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
    assert blocks, "srt 不能为空"

    prev_end = 0.0
    for i, block in enumerate(blocks, start=1):
        lines = block.strip().splitlines()
        assert lines[0] == str(i), f"编号不连续：{lines[0]}"
        match = SRT_TIME.match(lines[1])
        assert match, f"时间行非法：{lines[1]}"
        start, end = _to_seconds(match)
        assert end > start, "结束时间必须大于开始时间"
        assert start >= prev_end - 1e-6, "时间必须单调不减（倒序会被播放器丢弃）"
        prev_end = end
        assert len(lines) >= 3 and lines[2].strip(), "字幕文本不能为空"


def test_srt_text_matches_txt_content(offline_run: dict):
    """srt 与 txt 必须来自同一份转写：一处对齐失败不该造成两份产物不一致。"""
    srt = offline_run["result"].srt_path.read_text(encoding="utf-8")
    txt = offline_run["result"].txt_path.read_text(encoding="utf-8")
    srt_text = normalize_for_compare(
        "".join(line for block in srt.split("\n\n") for line in block.splitlines()[2:])
    )
    # 必须相等，不是"互相包含"：包含式断言会放过分片边界上的重复（实测 87 分钟录音差 54 字）
    assert srt_text == normalize_for_compare(txt)


def test_srt_covers_the_audio_duration(offline_run: dict):
    """时间轴要覆盖整段音频，而不是把整段挤在头一秒。"""
    srt = offline_run["result"].srt_path.read_text(encoding="utf-8")
    times = [
        _to_seconds(m)
        for m in (SRT_TIME.match(b.splitlines()[1]) for b in srt.strip().split("\n\n"))
        if m
    ]
    assert times[-1][1] > 8.0, "11.9s 的音频，最后一条字幕不该在 8s 前就结束"


def test_chunk_rows_are_persisted_with_segments(offline_run: dict):
    """分片级落盘必须带时间轴，否则续跑出来的 srt 会散架。"""
    chunks = offline_run["store"].chunks_for(offline_run["result"].task_id)
    assert chunks, "分片状态必须入库"
    assert all(c.status == "done" for c in chunks)
    assert all(c.text for c in chunks)
    assert any(c.segments for c in chunks), "分段时间轴没落盘"


def test_task_record_is_complete(offline_run: dict):
    task = offline_run["store"].get_task(offline_run["result"].task_id)
    assert task is not None
    assert task.status == "done"
    assert task.chars and task.chars > 20
    assert task.engine and task.engine.startswith("offline")
    assert task.error is None


def test_progress_events_cover_the_pipeline(offline_run: dict):
    stages = {e.stage for e in offline_run["events"]}
    assert {"probe", "normalize", "vad", "plan", "chunk", "merge", "done"} <= stages, stages


def test_no_error_text_leaks_into_output(offline_run: dict):
    """错误不得当结果返回：产物里不能出现错误字样。"""
    text = offline_run["result"].txt_path.read_text(encoding="utf-8")
    for marker in ("Traceback", "失败", "Error", "HTTP"):
        assert marker not in text, f"产物里混进了错误文本：{marker}"
