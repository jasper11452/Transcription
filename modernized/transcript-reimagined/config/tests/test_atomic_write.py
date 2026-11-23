"""用户文件的原子写：临时文件 → fsync → chmod → os.replace。

这是 `config` 包唯一的写盘通道；`config.env` / `glossary.txt` /
`summary-prompt.txt` 都走它。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from transcript_reimagined.config import atomic_write, write_config_template


def test_atomic_write_creates_parent_and_sets_mode(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "file.txt"
    atomic_write(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_replaces_existing_content(tmp_path: Path):
    target = tmp_path / "file.txt"
    target.write_text("old", encoding="utf-8")
    atomic_write(target, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"


def test_atomic_write_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "file.txt"
    atomic_write(target, "x\n")
    assert [p.name for p in tmp_path.iterdir()] == ["file.txt"]


def test_atomic_write_cleans_up_when_write_fails(tmp_path: Path, monkeypatch):
    target = tmp_path / "file.txt"

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(target, "x\n")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_config_template_is_not_overwritten(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text("DASHSCOPE_API_KEY=mine\n", encoding="utf-8")
    write_config_template(target)
    assert target.read_text(encoding="utf-8") == "DASHSCOPE_API_KEY=mine\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_config_template_created_with_600(tmp_path: Path):
    target = tmp_path / "config.env"
    write_config_template(target)
    assert "DASHSCOPE_API_KEY=" in target.read_text(encoding="utf-8")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
