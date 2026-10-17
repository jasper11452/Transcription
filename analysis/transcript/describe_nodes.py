#!/usr/bin/env python3
"""为 topology.json 的每个叶子节点生成描述包，并把子代理返回的段落合并回去。

两步用法：

    python3 analysis/transcript/describe_nodes.py packets   # 写 map/packets/<id>.txt
    python3 analysis/transcript/describe_nodes.py merge      # 读 map/descriptions.json 并入 topology.json

为什么要先落盘再合并：描述段落由子代理产生、由本脚本写入，子代理从不直接改
topology.json。合并时逐条校验「段落里出现的每个数字和标识符形状的名字，都必须
能在它的包里找到」—— 校验不过的节点留空，不塞进未经核对的内容。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path("legacy/transcript")
ANALYSIS = pathlib.Path("analysis/transcript")
TOPOLOGY = ANALYSIS / "topology.json"
PACKETS = ANALYSIS / "map" / "packets"
DESCRIPTIONS = ANALYSIS / "map" / "descriptions.json"

PACKET_LINES = 150

# 包体里要带的头部注释：文件开头的 docstring / 注释块，最多 40 行。
def header_of(path: pathlib.Path, limit: int = 40) -> str:
    if not path.is_file():
        return ""
    if path.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".html"}:
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    for ln in lines[:limit]:
        s = ln.strip()
        if not s and out:
            out.append(ln)
            continue
        if s.startswith(("#", "//", "/*", "*", "'''", '"""')) or (not out and not s):
            out.append(ln)
        elif not out:
            continue
        else:
            break
    return "\n".join(out).strip()


def pick_excerpt(path: pathlib.Path) -> str:
    """取最能说明这段代码在做什么的连续片段：优先文件开头的正文，不够则补最大函数。"""
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= PACKET_LINES:
        return "\n".join(lines)
    return "\n".join(lines[:PACKET_LINES])


def load() -> dict:
    return json.loads(TOPOLOGY.read_text(encoding="utf-8"))


def leaves(topo: dict) -> list[dict]:
    return [c for d in topo["root"]["children"] for c in d["children"]]


def connections(topo: dict, node_id: str) -> str:
    by_id = {c["id"]: c for c in leaves(topo)}
    out: list[str] = []
    for e in topo["edges"]:
        if e["source"] == node_id:
            t = by_id.get(e["target"], {})
            out.append(f"  -> {e['target']}  [{e['kind']}]  {t.get('name','')}")
        elif e["target"] == node_id:
            s = by_id.get(e["source"], {})
            out.append(f"  <- {e['source']}  [{e['kind']}]  {s.get('name','')}")
    role = []
    if node_id in topo["entryPoints"]:
        role.append("这是入口点（entry point）。")
    if node_id in topo["deadEnds"]:
        role.append("这是死端候选（dead end）。")
    head = " ".join(role)
    return head + ("\n" if head else "") + "\n".join(out)


def cmd_packets() -> None:
    topo = load()
    PACKETS.mkdir(parents=True, exist_ok=True)
    written = 0
    for node in leaves(topo):
        if node["kind"] == "datastore":
            continue
        target = ROOT / node["file"]
        files = sorted(
            p
            for p in ([target] if target.is_file() else target.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".html"}
        )
        # 目录型叶子（如 components/）逐个列出成员文件行数，不塞满包体。
        if target.is_dir():
            body = "\n".join(
                f"  {sum(1 for _ in p.open(encoding='utf-8', errors='replace')):>5} 行  "
                f"{p.relative_to(ROOT)}"
                for p in files
            )
        else:
            body = pick_excerpt(target)
        text = "\n".join(
            [
                f"节点 id      : {node['id']}",
                f"节点名       : {node['name']}",
                f"位置         : {node['file']}",
                f"代码行数     : {node.get('loc', 0)}",
                "",
                "—— 文件头部注释 ——",
                header_of(target) or "(无)",
                "",
                "—— 连接（来自拓扑图）——",
                connections(topo, node["id"]) or "(无连接)",
                "",
                "—— 源码片段 ——",
                body or "(目录型节点，仅列成员文件)",
            ]
        )
        (PACKETS / f"{node['id'].replace('.', '_')}.txt").write_text(text, encoding="utf-8")
        written += 1
    print(f"wrote {written} packets to {PACKETS}")


# 段落里出现的、需要能在包体中核对的 token：数字，以及标识符形状的名字。
NUM = re.compile(r"\b\d[\d,.]*\b")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")
CJK = re.compile(r"[一-鿿]")


def word_count(paragraph: str) -> int:
    """中英混排的「词数」：每个汉字算一个词，拉丁词按空白切分。"""
    return len(CJK.findall(paragraph)) + len(
        [w for w in re.split(r"\s+", CJK.sub(" ", paragraph)) if w.strip()]
    )
# 常见英语词与量词不参与核对（它们不该出现在包体里）。
STOP = {
    "this", "that", "with", "from", "into", "when", "then", "than", "they", "them",
    "their", "there", "these", "those", "which", "while", "would", "could", "should",
    "have", "has", "been", "being", "does", "doesn", "each", "only", "also", "because",
    "instead", "never", "always", "after", "before", "every", "read", "reads", "write",
    "writes", "call", "calls", "called", "node", "nodes", "line", "lines", "file",
    "files", "code", "module", "modules", "step", "steps", "flow", "flows", "store",
    "stores", "data", "used", "uses", "using", "same", "true", "false", "none", "null",
    "http", "https", "json", "string", "number", "value", "values", "state", "status",
    "type", "types", "name", "names", "path", "paths", "text", "task", "tasks",
}
# 段落里合法但不来自包体的词：中文写作里必然出现的英文连接词、以及图本身的术语。
ALLOW = {"HTTP", "SSE", "API", "SQLite", "MLX", "Python", "TypeScript", "React", "Vite", "CLI"}


def cmd_merge() -> None:
    topo = load()
    descs = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    packets = {
        p.stem: p.read_text(encoding="utf-8") for p in PACKETS.glob("*.txt")
    }
    merged, rejected = 0, []
    by_id = {c["id"]: c for c in leaves(topo)}
    for node_id, paragraph in descs.items():
        node = by_id.get(node_id)
        packet = packets.get(node_id.replace(".", "_"))
        if node is None or packet is None:
            rejected.append((node_id, "no node or no packet"))
            continue
        n = word_count(paragraph)
        if not (55 <= n <= 90):
            rejected.append((node_id, f"{n} words, outside 55-90"))
            continue
        missing = [
            tok
            for tok in set(NUM.findall(paragraph)) | set(IDENT.findall(paragraph))
            if tok not in packet and tok not in STOP and tok not in ALLOW
        ]
        if missing:
            rejected.append((node_id, f"not in packet: {sorted(missing)[:6]}"))
            continue
        node["description"] = paragraph
        merged += 1
    TOPOLOGY.write_text(
        json.dumps(topo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"merged {merged} descriptions into {TOPOLOGY}")
    for node_id, why in rejected:
        print(f"  REJECTED {node_id}: {why}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "packets"
    {"packets": cmd_packets, "merge": cmd_merge}[cmd]()