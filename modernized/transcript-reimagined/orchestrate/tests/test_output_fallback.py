"""产物目录回退：源目录不可写时落到 `<OUTPUT_DIR>/<stem>/`（RULE-133）。"""

from __future__ import annotations

import os

import pytest

from orchestrate_fakes import FakeEngine, env, make_pipeline  # noqa: F401


@pytest.mark.rule("RULE-133")
def test_read_only_source_folder_falls_back_to_the_output_directory(env):  # noqa: F811
    config, store, source, source_dir = env
    original_mode = source_dir.stat().st_mode
    try:
        os.chmod(source_dir, 0o500)
        result = make_pipeline(config, store, FakeEngine()).run(source, artifact="txt")
        assert result.status == "done"
        expected = config.output_dir / source.stem
        assert result.out_dir == expected
        assert (expected / "meeting.txt").is_file()
        assert not (source_dir / "meeting.txt").exists()
    finally:
        os.chmod(source_dir, original_mode)
