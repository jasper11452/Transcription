"""前端构建契约：`validate_dist` 是服务启动的硬门槛，它的失败信息必须能指导修复。

这里不跑 npm（测试不该装依赖），只在临时目录里伪造包结构来钉住行为。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from transcript.web.frontend import ensure_frontend, validate_dist


def write_dist(
    dist: Path, *, entry_flag: bool = True, assets: tuple[str, ...] = ("console.js",)
) -> Path:
    """造一份"像真产物"的 dist，返回 manifest 路径。"""
    (dist / ".vite").mkdir(parents=True, exist_ok=True)
    for name in assets:
        (dist / name).write_text("//built", encoding="utf-8")
    (dist / "index.html").write_text('<script src="/static/dist/console.js"></script>')
    (dist / "task.html").write_text('<script src="/static/dist/console.js"></script>')
    manifest = {
        "index.html": {"file": "console.js", "isEntry": entry_flag},
        "task.html": {"file": "console.js", "isEntry": entry_flag},
    }
    (dist / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dist / ".vite" / "manifest.json"


def test_正常产物通过校验(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    write_dist(dist)
    validate_dist(dist)


def test_缺_manifest_报可操作的错误(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as exc:
        validate_dist(tmp_path / "nope")
    assert "npm ci && npm run build" in str(exc.value)


def test_入口不是_isEntry_的也被拦下(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    write_dist(dist, entry_flag=False)
    with pytest.raises(RuntimeError):
        validate_dist(dist)


def test_manifest_引用的资源缺了就报(tmp_path: Path) -> None:
    """HTML 在、js 不在 = 白屏。这种半成品状态必须在启动时就拒绝。"""
    dist = tmp_path / "dist"
    write_dist(dist, assets=("console.js",))
    (dist / "console.js").unlink()
    with pytest.raises(RuntimeError):
        validate_dist(dist)


def test_css_资源也算在内(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    manifest_path = write_dist(dist, assets=("console.js", "app.css"))
    manifest = json.loads(manifest_path.read_text())
    manifest["index.html"]["css"] = ["app.css"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    validate_dist(dist)

    (dist / "app.css").unlink()
    with pytest.raises(RuntimeError):
        validate_dist(dist)


def test_主题脚本缺失时不能静默交付不可用按钮(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    write_dist(dist)
    (dist / "task.html").write_text(
        '<script src="/static/dist/theme.js"></script>', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="theme.js"):
        validate_dist(dist)
    (dist / "theme.js").write_text("// theme", encoding="utf-8")
    validate_dist(dist)


# ---------- ensure_frontend：源码比产物新就要重建 ----------


def make_frontend(root: Path) -> Path:
    frontend = root / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "vite.config.ts").write_text("export default {};", encoding="utf-8")
    (frontend / "src" / "main.tsx").write_text("//x", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    # 没有 node_modules/.bin/vite：等价于"没装依赖"，此时必须报错而不是尝试 npm install
    return frontend


def test_没有_frontend_目录就只校验产物(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    write_dist(dist)
    ensure_frontend(tmp_path / "frontend-missing", dist)  # 不抛异常即通过


def test_源码比产物新且缺依赖时给修复命令(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    write_dist(dist)
    frontend = make_frontend(tmp_path)
    source = frontend / "src" / "main.tsx"
    future = time.time() + 60
    os.utime(source, (future, future))

    with pytest.raises(RuntimeError) as exc:
        ensure_frontend(frontend, dist)
    message = str(exc.value)
    assert "npm ci && npm run build" in message
    assert "Node" in message


def test_产物更新时就跳过(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    manifest = write_dist(dist)
    frontend = make_frontend(tmp_path)
    future = time.time() + 60
    os.utime(manifest, (future, future))
    ensure_frontend(frontend, dist)  # 源码更旧 → 直接返回，不碰 npm
