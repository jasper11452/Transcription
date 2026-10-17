"""前端构建门禁：产物完整性、源码过期重建、绝不自动 npm install（NFR-7）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from transcript_reimagined.web.frontend import ensure_frontend, validate_dist


def good_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / ".vite").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "assets" / "index.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "assets" / "task.js").write_text("console.log(2)", encoding="utf-8")
    (dist / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    (dist / "task.html").write_text("<html><head></head></html>", encoding="utf-8")
    (dist / ".vite" / "manifest.json").write_text(
        json.dumps(
            {
                "index.html": {"isEntry": True, "file": "assets/index.js"},
                "task.html": {"isEntry": True, "file": "assets/task.js"},
            }
        ),
        encoding="utf-8",
    )
    return dist


def test_good_dist_passes(tmp_path: Path):
    validate_dist(good_dist(tmp_path))


def test_missing_manifest_is_rejected(tmp_path: Path):
    dist = good_dist(tmp_path)
    (dist / ".vite" / "manifest.json").unlink()
    with pytest.raises(RuntimeError, match="manifest"):
        validate_dist(dist)


def test_missing_entry_file_is_rejected(tmp_path: Path):
    dist = good_dist(tmp_path)
    (dist / "assets" / "index.js").unlink()
    with pytest.raises(RuntimeError, match="index.js"):
        validate_dist(dist)


def test_missing_entry_marker_is_rejected(tmp_path: Path):
    dist = good_dist(tmp_path)
    manifest_path = dist / ".vite" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["index.html"].pop("isEntry")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="isEntry"):
        validate_dist(dist)


def test_wheel_install_without_source_only_validates(tmp_path: Path):
    dist = good_dist(tmp_path)
    ensure_frontend(tmp_path / "no-frontend", dist)


def test_stale_sources_without_node_modules_fail_with_actionable_message(tmp_path: Path):
    dist = good_dist(tmp_path)
    frontend = tmp_path / "frontend"
    source = frontend / "src" / "main.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("x", encoding="utf-8")
    manifest = dist / ".vite" / "manifest.json"
    os.utime(manifest, (0, 0))
    with pytest.raises(RuntimeError, match="node_modules"):
        ensure_frontend(frontend, dist)


def test_stale_sources_are_rebuilt_with_existing_local_dependencies(tmp_path: Path, monkeypatch):
    dist = good_dist(tmp_path)
    frontend = tmp_path / "frontend"
    source = frontend / "src" / "main.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("x", encoding="utf-8")
    vite = frontend / "node_modules" / ".bin" / "vite"
    vite.parent.mkdir(parents=True)
    vite.write_text("", encoding="utf-8")
    manifest = dist / ".vite" / "manifest.json"
    os.utime(manifest, (0, 0))

    import transcript_reimagined.web.frontend as frontend_mod

    calls: list[tuple[list[str], Path]] = []
    monkeypatch.setattr(frontend_mod.shutil, "which", lambda _name: "/usr/local/bin/npm")
    monkeypatch.setattr(
        frontend_mod.subprocess,
        "run",
        lambda cmd, cwd, check, timeout: calls.append((cmd, cwd)),
    )
    ensure_frontend(frontend, dist)
    assert calls and calls[0][0][1:] == ["run", "build"]
    assert calls[0][1] == frontend


def test_missing_npm_after_stale_sources_fails(tmp_path: Path, monkeypatch):
    dist = good_dist(tmp_path)
    frontend = tmp_path / "frontend"
    source = frontend / "src" / "main.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("x", encoding="utf-8")
    vite = frontend / "node_modules" / ".bin" / "vite"
    vite.parent.mkdir(parents=True)
    vite.write_text("", encoding="utf-8")
    os.utime(dist / ".vite" / "manifest.json", (0, 0))

    import transcript_reimagined.web.frontend as frontend_mod

    monkeypatch.setattr(frontend_mod.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="npm"):
        ensure_frontend(frontend, dist)


def test_create_app_refuses_to_start_with_broken_dist(tmp_path: Path):
    from transcript_reimagined.config import Config
    from transcript_reimagined.state import Store

    from transcript_reimagined.web import create_app

    bad = tmp_path / "dist"
    bad.mkdir()
    with pytest.raises(RuntimeError, match="前端产物"):
        create_app(
            Config(config_path=tmp_path / "c.env", state_db=tmp_path / "s.db"),
            Store(tmp_path / "s.db"),
            dist_dir=bad,
            validate_frontend=True,
        )
