"""产物装配与落盘：`.txt` / `.srt` / `.raw.json`。

承载 `RULE-132` 的产物面：**替换痕迹写进产物** —— `.txt` 与 `.srt` 都以词表替换
注释块开头，`.raw.json` 保留未替换的原文（`merged_text_before_glossary`）与
`glossary_changes`。

`.raw.json` 的字段结构是下游消费契约（`RULE-134`），字段名与顺序按
`DATA_OBJECTS.md` / legacy `pipeline._write_raw` 固定，本阶段不新增字段。

**产物落盘位置不在这里决策**（`REIMAGINED_ARCHITECTURE.md` §2：产物选择必须是
单点决策，属 `orchestrate`）。这里只做「给我目录与文件名，我写文件」。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .domain import Change, Segment
from .glossary import change_comment
from .render import to_srt, to_txt


@dataclass(frozen=True)
class RawContext:
    """`.raw.json` 里与「这次跑的是什么」有关的部分（provenance）。

    全部字段都可缺省，缺省即不写入对应键 —— 这样 Phase 1 的最小 `run` 入口
    不必伪造 task id 或分片行。**这里没有也不可能出现凭据**（NFR-4）。
    """

    mode: str | None = None
    artifact: str | None = None
    engine: str | None = None
    task_id: int | None = None
    source: str | None = None
    config: dict[str, Any] | None = None
    chunks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ProductSet:
    """三个产物的文本形态（尚未落盘）。"""

    txt: str
    srt: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class WrittenProducts:
    """落盘结果：调用方拿这些路径去发事件 / 落库 / 回给页面。"""

    out_dir: Path
    txt_path: Path
    srt_path: Path
    raw_path: Path


def render_products(
    final_text: str,
    segments: Sequence[Segment] | None,
    changes: Sequence[Change],
    *,
    merged_text_before_glossary: str,
    context: RawContext | None = None,
) -> ProductSet:
    """装配三个产物。

    - `final_text` 是**替换后**的整段文本；`merged_text_before_glossary` 是替换前的原文，
      两者都进 `.raw.json`；
    - `segments` 要求调用方已经逐段做过词表替换（legacy `pipeline.py:358-361` 的做法），
      因为计数只以整段文本那一遍为准、逐段替换的处数不对外计数；
    - `segments` 为 `None` 时按 legacy 行为给 `.txt` 传 `None`（即用整段文本原样输出）。
    """
    ctx = context or RawContext()
    comments = change_comment(changes)

    txt = to_txt(final_text, None, comment_lines=comments)
    seg_list = list(segments or [])
    srt = to_srt(seg_list, comment_lines=comments)

    raw: dict[str, Any] = {}
    if ctx.task_id is not None:
        raw["task_id"] = ctx.task_id
    if ctx.source is not None:
        raw["source"] = ctx.source
    if ctx.mode is not None:
        raw["mode"] = ctx.mode
    if ctx.artifact is not None:
        raw["artifact"] = ctx.artifact
    if ctx.engine is not None:
        raw["engine"] = ctx.engine
    if ctx.config is not None:
        raw["config"] = ctx.config
    if ctx.chunks:
        raw["chunks"] = ctx.chunks
    raw["merged_text_before_glossary"] = merged_text_before_glossary
    raw["final_text"] = final_text
    raw["segments"] = [{"start": s.start, "end": s.end, "text": s.text} for s in seg_list]
    raw["glossary_changes"] = [
        {"wrong": c.wrong, "right": c.right, "count": c.count} for c in changes
    ]
    return ProductSet(txt=txt, srt=srt, raw=raw)


def write_products(products: ProductSet, out_dir: Path | str, stem: str) -> WrittenProducts:
    """把三个产物写到 `out_dir/<stem>.{txt,srt,raw.json}`（UTF-8）。

    目录不存在则创建；`raw.json` 用 `indent=2` 且不转义非 ASCII（既有产物格式）。
    覆盖同名文件是既有行为 —— 产物名由源文件 stem 决定。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    txt_path = out / f"{stem}.txt"
    srt_path = out / f"{stem}.srt"
    raw_path = out / f"{stem}.raw.json"

    txt_path.write_text(products.txt, encoding="utf-8")
    srt_path.write_text(products.srt, encoding="utf-8")
    raw_path.write_text(json.dumps(products.raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return WrittenProducts(out_dir=out, txt_path=txt_path, srt_path=srt_path, raw_path=raw_path)
