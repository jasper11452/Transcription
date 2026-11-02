#!/usr/bin/env python3
"""从 legacy/transcript 提取拓扑：模块、边、入口点、数据存储、死端、人话流程。

为什么手写：pydeps 与 madge 都不在本机，而本系统的依赖关系有两个特点让通用
工具不够用 —— (1) 引擎选择是配置驱动的分发（engines/base.py 的 SPECS 注册表 +
artifact 决定走向），静态 import 图看不到；(2) 前端的两个页面入口由后端内联
boot payload 驱动，边只存在于 HTTP/SSE 契约里。所以脚本自己解析 AST 建模块图，
再手动叠上这两类分发边和数据连接。

用法：python3 analysis/transcript/extract_topology.py
输出：analysis/transcript/topology.json
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

ROOT = pathlib.Path("legacy/transcript")
SRC = ROOT / "src" / "transcript"
OUT = pathlib.Path("analysis/transcript/topology.json")


SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".jsx", ".css", ".html"}
SKIP_DIR = {"node_modules", ".venv", "__pycache__", ".git", ".pytest_cache", ".ruff_cache"}


def loc_of(path: pathlib.Path) -> int:
    """源代码行数：只有源码扩展名、跳过依赖与缓存目录、不计空行与纯注释行。"""
    if not path.exists():
        return 0
    if path.is_dir():
        return sum(
            loc_of(p)
            for p in sorted(path.rglob("*"))
            if p.is_file()
            and p.suffix in SOURCE_EXT
            and not any(part in SKIP_DIR for part in p.parts)
        )
    if path.suffix not in SOURCE_EXT:
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return sum(
        1
        for ln in (s.strip() for s in lines)
        if ln and not ln.startswith(("#", "//", "/*", "*", '"""', "'''"))
    )


# ---------------------------------------------------------------- 模块依赖图

def py_module_graph() -> dict[str, set[str]]:
    """src/transcript/**.py 的内部 import 图，模块名 -> 它 import 的同包模块名。"""
    graph: dict[str, set[str]] = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        me = ".".join(parts)
        if not me:
            me = "__init__"
        deps: set[str] = set()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            graph[me] = deps
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                # 相对 import：from . import x / from .engines import base
                if n.level:
                    # level=1 指自己所在的包，level=2 指上一级：
                    # web.jobs 里 `from ..summary import X` -> base 为空 -> summary
                    base = parts[: len(parts) - n.level]
                    if n.module:
                        cand = ".".join(base + n.module.split("."))
                        deps.add(cand)
                    for a in n.names:
                        deps.add(".".join(base + [a.name]))
                elif n.module and n.module.startswith("transcript"):
                    deps.add(n.module.removeprefix("transcript."))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("transcript."):
                        deps.add(a.name.removeprefix("transcript."))
        graph[me] = deps
    # 归一化：把 "web.app" 这种点号路径收敛到实际存在的模块名上
    known = set(graph)
    norm: dict[str, set[str]] = {}
    for me, deps in graph.items():
        keep = set()
        for d in deps:
            if d in known:
                keep.add(d)
                continue
            # 逐级回退：from transcript.web import app -> web.app / web
            head = d
            while head and head not in known:
                head = head.rpartition(".")[0]
            if head:
                keep.add(head)
        norm[me] = keep
    return norm


def frontend_import_graph() -> dict[str, set[str]]:
    """frontend/src 内部的 import 图。"""
    fe = ROOT / "frontend" / "src"
    graph: dict[str, set[str]] = {}
    for p in sorted(fe.rglob("*.ts*")):
        rel = p.relative_to(fe).with_suffix("")
        me = "/".join(rel.parts)
        deps: set[str] = set()
        text = p.read_text(encoding="utf-8", errors="replace")
        # 支持相对路径与 @/ 别名（vite.config.ts 里 @ -> frontend/src）
        for m in re.finditer(r"""from\s+["']([^"']+)["']""", text):
            spec = m.group(1)
            if spec.startswith("@/"):
                target = fe / spec[2:]
            elif spec.startswith("."):
                target = (p.parent / spec).resolve()
            else:
                continue
            for cand in (target.with_suffix(""), target, pathlib.Path(str(target) + ".tsx")):
                try:
                    r = cand.relative_to(fe.resolve())
                    deps.add("/".join(r.with_suffix("").parts))
                    break
                except ValueError:
                    continue
        graph[me] = deps
    return graph


# ---------------------------------------------------------------- 叶子定义

# id 必须唯一，且每个叶子的 file 互不相同（extract-rules 按这些位置分片）。
LEAVES: list[dict] = [
    # 1 核心契约
    {"id": "config", "name": "config.py", "kind": "module", "dom": "core", "file": "src/transcript/config.py"},
    {"id": "errors", "name": "errors.py", "kind": "module", "dom": "core", "file": "src/transcript/errors.py"},
    {"id": "models", "name": "models.py", "kind": "module", "dom": "core", "file": "src/transcript/models.py"},
    # 2 音频入料
    {"id": "audio", "name": "audio.py", "kind": "module", "dom": "ingest", "file": "src/transcript/audio.py"},
    {"id": "vad", "name": "vad.py", "kind": "module", "dom": "ingest", "file": "src/transcript/vad.py"},
    {"id": "chunking", "name": "chunking.py", "kind": "module", "dom": "ingest", "file": "src/transcript/chunking.py"},
    # 3 编排
    {"id": "pipeline", "name": "pipeline.py", "kind": "module", "dom": "pipeline", "file": "src/transcript/pipeline.py"},
    # 4 引擎
    {"id": "engines.base", "name": "engines/base.py", "kind": "module", "dom": "engines", "file": "src/transcript/engines/base.py"},
    {"id": "engines.offline", "name": "engines/offline.py", "kind": "module", "dom": "engines", "file": "src/transcript/engines/offline.py"},
    {"id": "engines.dashscope", "name": "engines/dashscope.py", "kind": "module", "dom": "engines", "file": "src/transcript/engines/dashscope.py"},
    {"id": "engines.openrouter", "name": "engines/openrouter.py", "kind": "module", "dom": "engines", "file": "src/transcript/engines/openrouter.py"},
    {"id": "engines.bcut", "name": "engines/bcut.py", "kind": "module", "dom": "engines", "file": "src/transcript/engines/bcut.py"},
    # 5 后处理
    {"id": "align", "name": "align.py", "kind": "module", "dom": "post", "file": "src/transcript/align.py"},
    {"id": "merge", "name": "merge.py", "kind": "module", "dom": "post", "file": "src/transcript/merge.py"},
    {"id": "glossary", "name": "glossary.py", "kind": "module", "dom": "post", "file": "src/transcript/glossary.py"},
    {"id": "render", "name": "render.py", "kind": "module", "dom": "post", "file": "src/transcript/render.py"},
    # 6 存储
    {"id": "store", "name": "store.py", "kind": "module", "dom": "state", "file": "src/transcript/store.py"},
    # 7 总结
    {"id": "summary", "name": "summary.py", "kind": "module", "dom": "summary", "file": "src/transcript/summary.py"},
    # 8 分离
    {"id": "diar", "name": "diar.py", "kind": "module", "dom": "diar", "file": "src/transcript/diar.py"},
    # 9 Web
    {"id": "web.app", "name": "web/app.py", "kind": "module", "dom": "web", "file": "src/transcript/web/app.py"},
    {"id": "web.jobs", "name": "web/jobs.py", "kind": "module", "dom": "web", "file": "src/transcript/web/jobs.py"},
    {"id": "web.frontend", "name": "web/frontend.py", "kind": "module", "dom": "web", "file": "src/transcript/web/frontend.py"},
    # 10 前端
    {"id": "ui.main", "name": "main.tsx（控制台页）", "kind": "module", "dom": "ui", "file": "frontend/src/main.tsx"},
    {"id": "ui.task", "name": "task.tsx（任务详情页）", "kind": "module", "dom": "ui", "file": "frontend/src/task.tsx"},
    {"id": "ui.lib", "name": "lib/（API · 类型 · SSE）", "kind": "module", "dom": "ui", "file": "frontend/src/lib"},
    {"id": "ui.components", "name": "components/（含 9 个未用组件）", "kind": "module", "dom": "ui", "file": "frontend/src/components"},
    # 11 CLI
    {"id": "cli", "name": "cli.py", "kind": "module", "dom": "cli", "file": "src/transcript/cli.py"},
    # 12 死代码与验证
    {"id": "workbench", "name": "static/workbench/（无路由挂载）", "kind": "module", "dom": "harness", "file": "src/transcript/web/static/workbench"},
    {"id": "tests", "name": "tests/", "kind": "module", "dom": "harness", "file": "tests"},
    {"id": "spikes", "name": "spikes/", "kind": "module", "dom": "harness", "file": "spikes"},
]

DATASTORES: list[dict] = [
    {"id": "ds:state_db", "name": "state.db（SQLite）", "kind": "datastore", "dom": "data"},
    {"id": "ds:config_env", "name": "~/.config/transcript/config.env", "kind": "datastore", "dom": "data"},
    {"id": "ds:user_text", "name": "glossary.txt · summary-prompt.txt", "kind": "datastore", "dom": "data"},
    {"id": "ds:uploads", "name": "uploads/（浏览器副本）", "kind": "datastore", "dom": "data"},
    {"id": "ds:artifacts", "name": "<原名>.txt · .srt · .raw.json", "kind": "datastore", "dom": "data"},
    {"id": "ds:models", "name": "MLX 模型权重（树外）", "kind": "datastore", "dom": "data"},
    {"id": "ds:cloud", "name": "云端引擎 API（dashscope · openrouter · bcut）", "kind": "datastore", "dom": "data"},
]

DOMAINS = [
    ("core", "1 · 核心契约 · 配置 · 错误"),
    ("ingest", "2 · 音频入料与切片"),
    ("pipeline", "3 · 流水线编排"),
    ("engines", "4 · 引擎适配器"),
    ("post", "5 · 后处理与产物"),
    ("state", "6 · 状态存储"),
    ("summary", "7 · Agent 总结"),
    ("diar", "8 · 说话人分离"),
    ("web", "9 · Web 服务与任务运行"),
    ("ui", "10 · React SPA"),
    ("cli", "11 · CLI 入口"),
    ("harness", "12 · 死代码 · 测试 · 探针"),
    ("data", "数据存储"),
]


def build() -> dict:
    py = py_module_graph()
    ui = frontend_import_graph()

    # 模块名 -> 叶子 id
    alias = {
        "config": "config", "errors": "errors", "models": "models",
        "audio": "audio", "vad": "vad", "chunking": "chunking",
        "pipeline": "pipeline",
        "engines": "engines.base", "engines.base": "engines.base",
        "engines.offline": "engines.offline", "engines.dashscope": "engines.dashscope",
        "engines.openrouter": "engines.openrouter", "engines.bcut": "engines.bcut",
        "align": "align", "merge": "merge", "glossary": "glossary", "render": "render",
        "store": "store", "summary": "summary", "diar": "diar",
        "web": "web.app", "web.app": "web.app", "web.jobs": "web.jobs",
        "web.frontend": "web.frontend", "cli": "cli",
    }

    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(src: str, dst: str, kind: str) -> None:
        if src == dst or (src, dst, kind) in seen:
            return
        seen.add((src, dst, kind))
        edges.append({"source": src, "target": dst, "kind": kind})

    # --- 源码里的静态调用边 ---
    for me, deps in py.items():
        src = alias.get(me)
        if not src:
            continue
        for d in deps:
            dst = alias.get(d)
            if dst:
                add(src, dst, "call")

    # --- 前端的静态 import 边（折叠到 ui.lib / ui.components） ---
    for me, deps in ui.items():
        src = "ui.main" if me == "main" else "ui.task" if me == "task" else "ui.lib"
        dst = None
        for d in deps:
            head = d.split("/")[0]
            if head == "lib":
                dst = "ui.lib"
            elif head == "components":
                dst = "ui.components"
            elif d == "main":
                dst = "ui.main"
            elif d == "task":
                dst = "ui.task"
            if dst:
                add(src, dst, "call")

    # --- 分发边：引擎注册表驱动的选择（静态 import 看不到） ---
    add("pipeline", "engines.base", "dispatch")
    add("web.app", "engines.base", "dispatch")
    for eng in ("offline", "dashscope", "openrouter", "bcut"):
        add("engines.base", f"engines.{eng}", "dispatch")

    # --- 分发边：前端没有路由库，靠 HTTP/SSE 契约打到后端 ---
    add("ui.lib", "web.app", "dispatch")
    add("ui.main", "ui.lib", "call")
    add("ui.task", "ui.lib", "call")

    # --- 数据连接（代码到存储的 join） ---
    for m in ("pipeline", "web.app", "web.jobs", "cli"):
        add(m, "ds:state_db", "write")
        add(m, "ds:state_db", "read")
    add("store", "ds:state_db", "write")
    add("store", "ds:state_db", "read")

    for m in ("web.app", "cli"):
        add(m, "ds:config_env", "write")
    add("config", "ds:config_env", "read")
    add("summary", "ds:config_env", "read")
    for eng in ("dashscope", "openrouter"):
        add(f"engines.{eng}", "ds:config_env", "read")

    add("glossary", "ds:user_text", "read")
    add("summary", "ds:user_text", "read")
    add("web.app", "ds:user_text", "write")

    add("pipeline", "ds:uploads", "read")
    add("web.app", "ds:uploads", "write")

    add("pipeline", "ds:artifacts", "write")
    add("web.app", "ds:artifacts", "read")
    add("ui.task", "ds:artifacts", "read")

    add("engines.offline", "ds:models", "read")
    add("vad", "ds:models", "read")

    for eng in ("dashscope", "openrouter", "bcut"):
        add(f"engines.{eng}", "ds:cloud", "write")
        add(f"engines.{eng}", "ds:cloud", "read")
    add("summary", "ds:cloud", "write")
    add("summary", "ds:cloud", "read")

    # --- 树 ---
    by_dom: dict[str, list[dict]] = {}
    for leaf in LEAVES:
        path = ROOT / leaf["file"]
        node = {
            "id": leaf["id"],
            "name": leaf["name"],
            "kind": leaf["kind"],
            "language": "python" if leaf["file"].endswith(".py") else "typescript",
            "loc": loc_of(path),
            "file": leaf["file"],
        }
        by_dom.setdefault(leaf["dom"], []).append(node)
    for ds in DATASTORES:
        by_dom.setdefault(ds["dom"], []).append(
            {"id": ds["id"], "name": ds["name"], "kind": "datastore"}
        )

    children = []
    for key, label in DOMAINS:
        kids = by_dom.get(key)
        if not kids:
            continue
        children.append({"id": f"dom:{key}", "name": label, "kind": "domain", "children": kids})

    # --- 入口点 ---
    # cli.py 的 main()、把 bootstrap 装进页面并挂全部路由的 web/app.py，
    # 以及浏览器直接加载的两个页面入口。
    entry_points = ["cli", "web.app", "ui.main", "ui.task"]

    # --- 死端候选 ---
    # 有入边的一律不算死端（diar 被 pipeline 惰性调用，所以不算）。
    # 例外：tests/ 与 spikes/ 是验证与研究产物，scc 的入口不适用，不算「死代码」。
    inbound: dict[str, int] = {}
    for e in edges:
        inbound[e["target"]] = inbound.get(e["target"], 0) + 1
    harness = {"tests", "spikes"}
    dead_ends = []
    for leaf in LEAVES:
        if leaf["id"] in entry_points or leaf["id"] in harness:
            continue
        if inbound.get(leaf["id"], 0) == 0:
            dead_ends.append(leaf["id"])
    # ui.components 有入边，但其中 9/14 个组件零引用 —— 手工加回来。
    if "ui.components" not in dead_ends:
        dead_ends.append("ui.components")

    # --- 观测 ---
    observations = [
        "引擎选择是配置驱动的分发，静态 import 图看不到：pipeline/web.app 只 import "
        "engines.base，真正的引擎由 SPECS 注册表 + artifact 决定。图上 engines.base → "
        "offline/dashscope/openrouter/bcut 四条 dispatch 边就是这条链路 —— 重建时这张注册表是"
        "必须保留的单一真相来源。",
        "web/app.py 是唯一的 HTTP 汇聚点（hub）：cli、前端两个页面、以及全部数据存储都连到它。"
        "它同时是 743 行、复杂度 171 的单个闭包函数，零可测接缝 —— 这是整张图上最集中的单点。",
        "store.py 是 state.db 的**唯一**合法写入者，但 pipeline、web.jobs、web.app、cli 都直接"
        "连到 state.db。日志与任务状态绕过 store 层的写入路径没有集中，重建时应把 state.db "
        "收敛到单一仓储接口后面。",
        "ds:config_env 有 5 个读取者（config/summary/dashscope/openrouter）和 2 个写入者"
        "（web.app/cli）。凭据读取路径分散在四个模块里，而写入路径有两份实现 —— 其中 "
        "config.py:213 的 save_credentials 没有任何调用者（见技术债 #7）。",
        "diar.py 的入边只有 pipeline 的惰性调用一条，且 enable_diar 只从配置文件读、没有路由或"
        "UI 暴露。图上它是叶子，实质上是要么接通、要么移出 src/ 的判断题（见技术债 #9）。",
        "static/workbench 与 tests/spikes 同属 12 域，但 workbench 零入边、零路由挂载 —— 它不"
        "是测试也不是运行时的一部分，是 4,233 行不可达代码。另两域是有用途的研究/验证产物。",
    ]

    # --- 人话流程 ---
    flows = [
        {
            "name": "深夜批量整理：把一个录音变成字幕",
            "persona": "在深夜整理会议录音的项目所有者",
            "description": "把一段已录好的会议音频拖进控制台，等到出字幕，打开录入栏改几个专名就走。",
            "steps": [
                {"label": "拖入音频文件", "nodes": ["ui.main", "ui.lib", "web.app"]},
                {"label": "确认离线/在线与产物种类", "nodes": ["web.app", "config", "engines.base"]},
                {"label": "浏览器副本落到本机 uploads", "nodes": ["web.app", "ds:uploads"]},
                {"label": "切静音、归一化、规划分片", "nodes": ["pipeline", "audio", "vad", "chunking"]},
                {"label": "逐片转写（离线常驻模型／在线并行）", "nodes": ["engines.offline", "engines.dashscope", "ds:models", "ds:cloud"]},
                {"label": "对齐时间轴、去重、套热词", "nodes": ["align", "merge", "glossary"]},
                {"label": "渲染并落到原文件旁", "nodes": ["render", "ds:artifacts"]},
            ],
        },
        {
            "name": "边转录边校对：已完成的分片立刻可见",
            "persona": "想在转录还没跑完时就开始改错字的人",
            "description": "转录跑着，任务详情页已经能把跑完的那几段字幕显示出来，改一个专名不用等全部结束。",
            "steps": [
                {"label": "打开任务详情页", "nodes": ["ui.task", "ui.lib"]},
                {"label": "每片完成即写入本地库", "nodes": ["pipeline", "store", "ds:state_db"]},
                {"label": "服务端把进度与分片文本推给页面", "nodes": ["web.jobs", "web.app"]},
                {"label": "页面增量追加字幕与文稿", "nodes": ["ui.task"]},
                {"label": "改热词后重新生成产物", "nodes": ["glossary", "web.app", "ds:user_text"]},
            ],
        },
        {
            "name": "断点续跑：进程被杀也不重复付费",
            "persona": "转录到一半被迫关机、又不想重花钱的人",
            "description": "跑到一半的转录中断后重开，已完成的那些分片不重跑、不重复付费，接着跑剩下的。",
            "steps": [
                {"label": "任务中断，已完成分片留在本地库", "nodes": ["pipeline", "store", "ds:state_db"]},
                {"label": "重新打开时识别可续跑", "nodes": ["web.app", "web.jobs"]},
                {"label": "复用缓存分片，只补缺口", "nodes": ["pipeline", "engines.base"]},
                {"label": "补完后才写产物（失败不写半成品）", "nodes": ["render", "ds:artifacts"]},
            ],
        },
        {
            "name": "显式开启 Agent 总结：从转录文本到要点与待办",
            "persona": "开完会想把两小时录音直接变成行动项的人",
            "description": "转录完成后显式开一次总结，拿到项目标题、主旨、要点和待办，边生成边显示。",
            "steps": [
                {"label": "在任务详情页显式开启总结", "nodes": ["ui.task", "web.app"]},
                {"label": "服务端读配置与热词，组装提示词", "nodes": ["summary", "config", "ds:config_env", "ds:user_text"]},
                {"label": "转录文本与提示词发往配置的 Base URL", "nodes": ["summary", "ds:cloud"]},
                {"label": "流式回传正文，思考过程折叠", "nodes": ["summary", "web.app", "ui.task"]},
            ],
        },
    ]

    root = {
        "id": "sys",
        "name": "transcript",
        "kind": "system",
        "children": children,
    }

    return {
        "system": "transcript",
        "root": root,
        "edges": edges,
        "entryPoints": entry_points,
        "deadEnds": dead_ends,
        "observations": observations,
        "flows": flows,
    }


def main() -> None:
    topo = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(topo, ensure_ascii=False, indent=2), encoding="utf-8")

    leaves = [c for d in topo["root"]["children"] for c in d["children"]]
    mods = [c for c in leaves if c["kind"] == "module"]
    total_loc = sum(c.get("loc", 0) for c in mods)
    from collections import Counter

    kinds = Counter(e["kind"] for e in topo["edges"])
    print(f"wrote {OUT}")
    print(f"  domains     {len(topo['root']['children'])}")
    print(f"  leaves      {len(leaves)}  ({len(mods)} modules, "
          f"{len(leaves) - len(mods)} datastores)")
    print(f"  module LOC  {total_loc:,}")
    print(f"  edges       {len(topo['edges'])}  {dict(kinds)}")
    print(f"  entryPoints {topo['entryPoints']}")
    print(f"  deadEnds    {topo['deadEnds']}")
    print(f"  flows       {len(topo['flows'])}: " + "; ".join(f["name"] for f in topo["flows"]))
    print("  largest modules:")
    for c in sorted(mods, key=lambda x: -x.get("loc", 0))[:8]:
        print(f"    {c['loc']:>5}  {c['id']:<20} {c['file']}")


if __name__ == "__main__":
    main()