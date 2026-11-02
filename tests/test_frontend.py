"""Build lifecycle tests never invoke npm, install dependencies, or access user data."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from transcript.web.frontend import ensure_frontend, validate_dist


def built(dist: Path) -> None:
    dist.mkdir(parents=True, exist_ok=True)
    (dist / ".vite").mkdir(exist_ok=True)
    (dist / "assets").mkdir(exist_ok=True)
    (dist / "assets/app.js").write_text("export {}")
    for name in ("index.html", "task.html"):
        (dist / name).write_text("<div id='root'></div>")
    (dist / ".vite/manifest.json").write_text(
        json.dumps(
            {
                name: {"file": "assets/app.js", "isEntry": True}
                for name in ("index.html", "task.html")
            }
        )
    )


def checkout(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}")
    (frontend / "src").mkdir()
    (frontend / "src/main.tsx").write_text("export {}")
    (frontend / "node_modules/.bin").mkdir(parents=True)
    (frontend / "node_modules/.bin/vite").touch()
    return frontend, tmp_path / "dist"


def test_installed_wheel_does_not_need_node(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    built(dist)
    run = Mock(side_effect=AssertionError("must not invoke npm"))
    monkeypatch.setattr(subprocess, "run", run)
    ensure_frontend(tmp_path / "absent-source", dist)
    run.assert_not_called()


def test_missing_packaged_asset_has_actionable_error(tmp_path):
    built(tmp_path)
    (tmp_path / "assets/app.js").unlink()
    with pytest.raises(RuntimeError, match="产物缺失或不完整"):
        validate_dist(tmp_path)


def test_fresh_checkout_does_not_rebuild(tmp_path, monkeypatch):
    frontend, dist = checkout(tmp_path)
    built(dist)
    run = Mock(side_effect=AssertionError("fresh build must be reused"))
    monkeypatch.setattr(subprocess, "run", run)
    ensure_frontend(frontend, dist)
    run.assert_not_called()


def test_stale_checkout_builds_once_with_timeout(tmp_path, monkeypatch):
    frontend, dist = checkout(tmp_path)
    built(dist)
    stamp = (dist / ".vite/manifest.json").stat().st_mtime_ns + 10_000_000
    source = frontend / "src/main.tsx"
    os.utime(source, ns=(stamp, stamp))
    monkeypatch.setattr("transcript.web.frontend.shutil.which", lambda _: "/bin/npm")
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    ensure_frontend(frontend, dist)
    run.assert_called_once_with(["/bin/npm", "run", "build"], cwd=frontend, check=True, timeout=120)


def test_missing_dependencies_never_auto_install(tmp_path, monkeypatch):
    frontend, dist = checkout(tmp_path)
    (frontend / "node_modules/.bin/vite").unlink()
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="启动不会自动下载依赖"):
        ensure_frontend(frontend, dist)
    run.assert_not_called()


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, "npm"), subprocess.TimeoutExpired("npm", 120)]
)
def test_failed_build_never_falls_back_to_old_pages(tmp_path, monkeypatch, error):
    frontend, dist = checkout(tmp_path)
    monkeypatch.setattr("transcript.web.frontend.shutil.which", lambda _: "/bin/npm")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))
    with pytest.raises(RuntimeError, match="服务未启动"):
        ensure_frontend(frontend, dist)
