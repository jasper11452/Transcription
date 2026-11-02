"""端到端验收：一次真实运行必须真的在临时目录里写出文件，并真的能读回来。

这是 Phase 1 修订的核心判据 —— 试点要碰到的接缝是**文件 I/O 与跨包 import**，
不是纯函数的输入输出。因此这里的断言全部基于磁盘上的字节，而不是内存里的返回值。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _fixtures import metadata_doc, metadata_json
from transcript_reimagined.runner.metadata import MetadataError
from transcript_reimagined.runner.products import ProductError
from transcript_reimagined.runner.run import RunRequest, run


def test_runner_writes_three_real_files_and_reads_them_back(out_dir, glossary_file):
    """一次运行 → 三个文件真的落在磁盘上 → 读回来内容自洽。"""
    result = run(
        RunRequest(metadata_text=metadata_json(), out_dir=out_dir, glossary_path=glossary_file)
    )

    written = sorted(result.files)
    assert written == ["raw_json", "srt", "txt"]
    on_disk = sorted(p.name for p in out_dir.iterdir())
    assert on_disk == ["2026-10-17 会议.raw.json", "2026-10-17 会议.srt", "2026-10-17 会议.txt"]

    txt = result.paths.txt.read_text(encoding="utf-8")
    srt = result.paths.srt.read_text(encoding="utf-8")
    raw = json.loads(result.paths.raw_json.read_text(encoding="utf-8"))

    assert raw["final_text"] == "我们把集诚做完了。请确认集诚的报价。"
    assert txt.splitlines()[0].startswith("# 词表替换")
    assert txt.splitlines()[1] == "[speaker_1] 我们把集诚做完了。请确认集诚的报价。"
    assert txt.splitlines()[2] == "[speaker_2] 好的。"
    assert srt.splitlines()[2] == "1"
    assert "00:00:00,000 --> 00:00:20,000" in srt
    assert srt.rstrip().endswith("好的。")
    # 300s + 两段语音（中间 1.2s 静音）→ 3 个切点、4 片；末片是静音尾巴（无正文，不等于丢正文）
    assert raw["chunk_count"] == len(result.chunks) == 4
    assert result.chunks[-1].end == 300.0


def test_runner_metadata_can_come_from_a_real_file(tmp_path, out_dir):
    """元数据本身必须能从磁盘读（真实文件 I/O，而不是内联字符串）。"""
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(metadata_json(artifact="txt"), encoding="utf-8")
    result = run(RunRequest(metadata_path=meta_path, out_dir=out_dir))
    assert result.paths.txt.is_file()
    assert result.paths.raw_json.is_file()


def test_runner_glossary_can_come_from_a_real_file(tmp_path, out_dir):
    glossary = tmp_path / "glossary.txt"
    glossary.write_text("艾麦 -> 集诚\n", encoding="utf-8")
    result = run(
        RunRequest(
            metadata_text=metadata_json(
                merged_text="艾麦", segments=[{"start": 0.0, "end": 1.0, "text": "艾麦"}]
            ),
            out_dir=out_dir,
            glossary_path=glossary,
        )
    )
    txt = result.paths.txt.read_text(encoding="utf-8")
    assert txt.splitlines()[0] == "# 词表替换（原始转写见 .raw.json）：艾麦→集诚 ×1"
    assert txt.splitlines()[1] == "集诚"
    assert result.paths.srt.read_text(encoding="utf-8").splitlines()[4] == "集诚"


def test_runner_creates_the_output_directory_if_missing(tmp_path, glossary_file):
    nested = tmp_path / "deeply" / "nested" / "out"
    assert not nested.exists()
    run(RunRequest(metadata_text=metadata_json(), out_dir=nested, glossary_path=glossary_file))
    assert nested.is_dir()
    assert len(list(nested.iterdir())) == 3


def test_runner_reports_metadata_problems_without_writing_anything(out_dir):
    with pytest.raises(MetadataError):
        run(RunRequest(metadata_text="{not json", out_dir=out_dir))
    with pytest.raises(MetadataError):
        run(RunRequest(metadata_text=json.dumps({"spans": []}), out_dir=out_dir))
    assert list(out_dir.iterdir()) == [], "失败时不得留下任何文件"


def test_runner_refuses_srt_without_timestamps_and_writes_nothing(out_dir):
    with pytest.raises(ProductError) as excinfo:
        run(
            RunRequest(
                metadata_text=metadata_json(artifact="srt", has_timestamps=False),
                out_dir=out_dir,
            )
        )
    assert "不提供时间戳" in str(excinfo.value)
    assert list(out_dir.iterdir()) == []


def test_runner_txt_task_does_not_write_an_srt(out_dir):
    """``RULE-061`` 的补齐项：``artifact=txt`` 且没有段落时间轴 → 只有 .txt。"""
    result = run(
        RunRequest(
            metadata_text=metadata_json(artifact="txt", segments=[]),
            out_dir=out_dir,
        )
    )
    assert result.paths.srt is None
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "2026-10-17 会议.raw.json",
        "2026-10-17 会议.txt",
    ]


def test_runner_uses_the_requested_artifact_over_the_metadata(tmp_path, out_dir):
    meta = tmp_path / "meta.json"
    meta.write_text(metadata_json(artifact="srt"), encoding="utf-8")
    result = run(RunRequest(metadata_path=meta, out_dir=out_dir, artifact="txt", stem="override"))
    assert result.artifact == "txt"
    assert (out_dir / "override.txt").is_file()


def test_runner_runs_as_a_module_end_to_end(tmp_path, out_dir):
    """真实进程边界：``python -m transcript_reimagined.runner`` 也必须写出文件。"""
    meta = tmp_path / "meta.json"
    meta.write_text(metadata_json(artifact="txt"), encoding="utf-8")
    env = {"PYTHONPATH": os.pathsep.join(str(p) for p in MEMBER_SRC), "PATH": "/usr/bin:/bin"}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "transcript_reimagined.runner",
            str(meta),
            "--out",
            str(out_dir),
            "--artifact",
            "txt",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert set(payload["files"]) == {"txt", "raw_json"}
    assert (out_dir / "2026-10-17 会议.txt").is_file()


def test_runner_cli_exit_code_3_when_the_product_is_refused(tmp_path, out_dir):
    meta = tmp_path / "meta.json"
    meta.write_text(metadata_json(artifact="srt", has_timestamps=False), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "transcript_reimagined.runner", str(meta), "--out", str(out_dir)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": os.pathsep.join(str(p) for p in MEMBER_SRC), "PATH": "/usr/bin:/bin"},
        cwd=str(tmp_path),
        check=False,
    )
    assert completed.returncode == 3
    assert "产物被拒绝" in completed.stderr
    assert list(out_dir.iterdir()) == []


def test_runner_is_reproducible(out_dir, glossary_file, tmp_path):
    """两次运行（不同输出目录）必须逐字节一致 —— 产物是确定性的。"""
    first = run(
        RunRequest(metadata_text=metadata_json(), out_dir=out_dir, glossary_path=glossary_file)
    )
    second_dir = tmp_path / "again"
    second = run(
        RunRequest(metadata_text=metadata_json(), out_dir=second_dir, glossary_path=glossary_file)
    )
    for name, path in first.files.items():
        other = Path(second.files[name])
        assert Path(path).read_bytes() == other.read_bytes(), name
    assert second.txt == first.txt and second.srt == first.srt


def test_metadata_sample_fixture_matches_the_documented_contract():
    from _fixtures import DATA

    sample = json.loads((DATA / "metadata.sample.json").read_text(encoding="utf-8"))
    assert sample == metadata_doc()


def test_runner_never_writes_outside_the_output_directory(out_dir, glossary_file, tmp_path):
    """``NFR-2`` 的同形要求：源目录是只读的，产物只落在输出目录里。"""
    source_dir = tmp_path / "read-only-source"
    source_dir.mkdir()
    before = sorted(p.name for p in source_dir.iterdir())
    run(RunRequest(metadata_text=metadata_json(), out_dir=out_dir, glossary_path=glossary_file))
    assert sorted(p.name for p in source_dir.iterdir()) == before
    assert set(sorted(p.suffix for p in out_dir.iterdir())) == {".txt", ".srt", ".json"}


#: 真实进程边界要把四个成员的 src 都放上 PYTHONPATH：
#: `runner` 不再自带 `domain`/`ingest`/`post` 的副本（那是脚手架阶段的
#: 复制，已按架构评审 M4 删除），兄弟包靠 PEP 420 命名空间合并。
MEMBER_SRC = [Path(__file__).resolve().parents[2] / m / "src"
              for m in ("domain", "ingest", "post", "runner")]
