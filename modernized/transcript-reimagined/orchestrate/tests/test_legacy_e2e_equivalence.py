"""Phase 5 端到端等价：同一输入下，新 Pipeline 的三个产物与 legacy 逐字节一致。

用真实 ffmpeg 生成 12s 样例音频、真实归一化/切片，引擎用确定性假引擎（不发网络）。
legacy 快照只作只读预言机；两边各自用独立的 `state.db`（task_id 都为 1），
所以 `.raw.json` 里的 task_id / source / config 也具备可比性。

这证明的是**编排层**的等价：引擎结果 → 分片落库 → 合并 → 词表 → 渲染 → 三产物。
引擎自身的行为由 Phase 4 的夹具回放测试覆盖。
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import Segment, TranscriptResult, Word
from transcript_reimagined.state import Store

from transcript_reimagined.orchestrate import Pipeline


def _find_legacy_src() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "legacy" / "transcript" / "src"
        if candidate.is_dir():
            return candidate
    return Path("__no_legacy__")


LEGACY_SRC = _find_legacy_src()


def legacy(name: str):
    if not LEGACY_SRC.is_dir():
        pytest.skip(f"legacy 快照不在场：{LEGACY_SRC}")
    if str(LEGACY_SRC) not in sys.path:
        sys.path.insert(0, str(LEGACY_SRC))
    return importlib.import_module(f"transcript.{name}")


def make_wav(path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("没有 ffmpeg")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=12",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
    )
    return path


class NewFakeEngine:
    name = "fake:e2e"
    max_chunk_s = None
    has_timestamps = True

    def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False, duration_s=None):
        idx = int(Path(audio_path).stem.rsplit("_", 1)[-1])
        text = f"第{idx}片：转录工具冒烟测试。"
        words = [
            Word("第", 0.0, 0.1),
            Word(str(idx), 0.1, 0.2),
            Word("片", 0.2, 0.3),
        ]
        segments = [Segment(0.0, 0.5, text, words=list(words))]
        return TranscriptResult(
            text=text,
            segments=segments,
            words=list(words),
            engine=self.name,
            has_timestamps=True,
        )


def make_legacy_engine():
    models = legacy("models")

    class LegacyFakeEngine:
        name = "fake:e2e"
        max_chunk_s = None
        has_timestamps = True

        def transcribe(self, audio_path, *, language=None, hotwords=None, want_timestamps=False):
            idx = int(Path(audio_path).stem.rsplit("_", 1)[-1])
            text = f"第{idx}片：转录工具冒烟测试。"
            words = [
                models.Word("第", 0.0, 0.1),
                models.Word(str(idx), 0.1, 0.2),
                models.Word("片", 0.2, 0.3),
            ]
            return models.TranscriptResult(
                text=text,
                segments=[models.Segment(0.0, 0.5, text, list(words))],
                engine=self.name,
                has_timestamps=True,
            )

    return LegacyFakeEngine()


def read_products(directory: Path) -> dict[str, bytes]:
    return {
        name: (directory / f"meeting.{name}").read_bytes()
        for name in ("txt", "srt", "raw.json")
    }


def test_new_pipeline_products_are_byte_identical_to_legacy(tmp_path: Path):
    source = make_wav(tmp_path / "source" / "meeting.wav")

    common = dict(
        chunk_min_s=3.0,
        chunk_max_s=5.0,
        chunk_overlap_s=0.1,
        output_dir=tmp_path / "fallback",
        glossary_path=tmp_path / "glossary.txt",
        max_attempts=1,
        backoff_base=0.0,
    )

    # ---- legacy ----
    legacy_pipeline_mod = legacy("pipeline")
    legacy_config_mod = legacy("config")
    legacy_store_mod = legacy("store")
    legacy_config = legacy_config_mod.Config(
        config_path=tmp_path / "legacy-config.env",
        state_db=tmp_path / "legacy-state.db",
        **common,
    )
    legacy_store = legacy_store_mod.Store(tmp_path / "legacy-state.db")
    legacy_result = legacy_pipeline_mod.Pipeline(
        legacy_config,
        legacy_store,
        engine_factory=lambda _kind, _cfg, artifact=None: make_legacy_engine(),
        vad_fn=lambda _wav: [(0.0, 12.0)],
        sleep=lambda _s: None,
    ).run(source, mode="offline", artifact="srt")
    assert legacy_result.status == "done"
    expected = read_products(source.parent)

    # ---- new ----
    new_config = Config(
        config_path=tmp_path / "new-config.env",
        state_db=tmp_path / "new-state.db",
        **common,
    )
    new_store = Store(tmp_path / "new-state.db")
    new_result = Pipeline(
        new_config,
        new_store,
        engine_factory=lambda _kind, _cfg, artifact=None: NewFakeEngine(),
        vad_fn=lambda _wav: [(0.0, 12.0)],
        sleep=lambda _s: None,
    ).run(source, mode="offline", artifact="srt")
    assert new_result.status == "done"
    actual = read_products(source.parent)

    assert actual["txt"] == expected["txt"]
    assert actual["srt"] == expected["srt"]
    assert actual["raw.json"] == expected["raw.json"]
