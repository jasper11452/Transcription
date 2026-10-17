"""前端源码与构建产物的一致性（NFR-12 / Phase 6 exit criteria）。

Python 侧不跑 React 单测（主题/壳层行为由 `npm test` 的 11 条 Node 测试覆盖）；
这里守住三件容易漂移的事：依赖清单与源码一致、未用组件已删除、构建产物可启动。
"""

from __future__ import annotations

import json
from pathlib import Path

from transcript_reimagined.web.frontend import DIST_DIR, validate_dist

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"

REMOVED_DEPS = (
    "react-router-dom",
    "@tanstack/react-query",
    "zustand",
    "@radix-ui/react-dialog",
    "@radix-ui/react-dropdown-menu",
    "@radix-ui/react-progress",
    "@radix-ui/react-select",
    "@radix-ui/react-toast",
)
KEPT_UI = {"badge.tsx", "button.tsx", "input.tsx", "tabs.tsx", "textarea.tsx"}


def test_package_json_matches_the_source():
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    dependencies = package["dependencies"]
    for dep in REMOVED_DEPS:
        assert dep not in dependencies, f"{dep} 已删除，不能留在 package.json"
    source = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.ts*"))
    for dep in REMOVED_DEPS:
        assert f"from '{dep}'" not in source and f'from "{dep}"' not in source


def test_unused_shadcn_components_are_deleted():
    ui = SRC / "components" / "ui"
    assert {p.name for p in ui.glob("*.tsx")} == KEPT_UI
    source = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
    for name in ("alert", "card", "dialog", "dropdown-menu", "label", "progress", "select", "skeleton", "toast"):
        assert f"components/ui/{name}" not in source


def test_vite_outputs_into_the_web_package():
    config = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    assert "../web/src/transcript_reimagined/web/static/dist" in config
    assert "manifest: true" in config


def test_committed_dist_passes_the_startup_gate():
    validate_dist(DIST_DIR)
    manifest = json.loads(
        (DIST_DIR / ".vite" / "manifest.json").read_text(encoding="utf-8")
    )
    for entry in ("index.html", "task.html"):
        assert manifest[entry]["isEntry"] is True
    assert (DIST_DIR / "theme.js").is_file()


def test_frontend_fixes_are_present_in_source():
    """Q1 / Q2 / Q4 / Q5 / Q6 / Q10 的修复必须在源码里留痕，防止回退。"""
    main = (SRC / "main.tsx").read_text(encoding="utf-8")
    task = (SRC / "task.tsx").read_text(encoding="utf-8")
    sidebar = (SRC / "components" / "history-sidebar.tsx").read_text(encoding="utf-8")

    assert "请先输入密钥" in main  # Q1 空输入无操作
    assert "请选择音频文件或填写路径" in main  # Q5 来源守卫
    assert "visibleModels" in task and "slice(0, 60)" in task  # Q2 先计数后截断
    assert "chunkTexts" in task  # Q4 segments 优先
    assert "t.interrupted" in task  # Q10 服务端状态
    assert "t.interrupted" in sidebar and "cancelling: true" in sidebar  # Q6 / Q10
    # C8：config → API → UI 三处都能开启
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    api = (SRC / "lib" / "api.ts").read_text(encoding="utf-8")
    assert 'id="diarEnabled"' in index
    assert "saveDiarSetting" in main
    assert "saveDiarSetting" in api
