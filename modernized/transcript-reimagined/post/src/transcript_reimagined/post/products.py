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
    """落盘结果：调用方拿这些路径去发事件 / 落库 / 回给页面。

    `srt_path` 为 `None` 表示这次按 `artifact` **没有写** `.srt`（Q9 裁定：
    `artifact=txt` 只写 `.txt`，不写一个空 `.srt` 充数）。
    """

    out_dir: Path
    txt_path: Path
    srt_path: Path | None
    raw_path: Path


#: 产物选择是**单点决策**（Q9 / `RULE-061`）：`artifact` → 要写哪几个文件。
#: `srt` 仍写 `.txt`（正文稿始终需要）；`txt` 绝不写 `.srt`。
PRODUCT_KINDS: dict[str, tuple[str, ...]] = {
    "txt": ("txt",),
    "srt": ("txt", "srt"),
}


def select_product_kinds(artifact: str) -> tuple[str, ...]:
    """`artifact` → 要写的产物种类。未知值直接报错，不猜。"""
    kinds = PRODUCT_KINDS.get(artifact)
    if kinds is None:
        raise ValueError(f"未知产物：{artifact}（只有 txt / srt）")
    return kinds


def render_products_for(
    final_text: str,
    segments: Sequence[Segment] | None,
    changes: Sequence[Change],
    *,
    artifact: str,
    merged_text_before_glossary: str,
    context: RawContext | None = None,
) -> ProductSet:
    """按 `artifact` 只渲染被选中的产物。

    这是 `orchestrate` 的唯一入口：`artifact=txt` 时连 `to_srt` 都不会调用 ——
    因此一个时间轴坏掉的文本任务不会因为「顺手渲染 srt」而失败。
    """
    kinds = select_product_kinds(artifact)
    ctx = context or RawContext()
    comments = change_comment(changes)
    seg_list = list(segments or [])
    # 只有确实带说话人时才把 segments 交给 txt 渲染器：无说话人时传 None，
    # 保持 legacy 的「合并文本原样一行」形态（逐字节等价）。Q8 要求 txt/srt
    # 双产物一致输出 speaker；UAT 实测此前 txt 丢标签，就是这里传了 None。
    has_speaker = any(s.speaker for s in seg_list)

    txt = (
        to_txt(final_text, seg_list if has_speaker else None, comment_lines=comments)
        if "txt" in kinds
        else ""
    )
    srt = to_srt(seg_list, comment_lines=comments) if "srt" in kinds else ""

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
    if ctx.chunks:
        # 字段顺序与 legacy `_write_raw` 一致：chunk_count 在 config 之前。
        raw["chunk_count"] = len(ctx.chunks)
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


def render_products(
    final_text: str,
    segments: Sequence[Segment] | None,
    changes: Sequence[Change],
    *,
    merged_text_before_glossary: str,
    context: RawContext | None = None,
) -> ProductSet:
    """装配三个产物（总是 txt + srt）。

    保留给 Phase 1 的切片入口与「三件套」测试；`orchestrate` 用
    `render_products_for(..., artifact=...)` 做单点产物决策。
    """
    return render_products_for(
        final_text,
        segments,
        changes,
        artifact="srt",
        merged_text_before_glossary=merged_text_before_glossary,
        context=context,
    )


def write_products(products: ProductSet, out_dir: Path | str, stem: str) -> WrittenProducts:
    """把三个产物写到 `out_dir/<stem>.{txt,srt,raw.json}`（UTF-8）。

    目录不存在则创建；`raw.json` 用 `indent=2` 且不转义非 ASCII（既有产物格式）。
    覆盖同名文件是既有行为 —— 产物名由源文件 stem 决定。

    **orchestrate 请用 `write_products_for`**：这个函数总是写三个文件，只保留给
    Phase 1 的切片入口与「三件套」测试。
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


def write_products_for(
    products: ProductSet, out_dir: Path | str, stem: str, *, artifact: str
) -> WrittenProducts:
    """按 `artifact` 只写被选中的产物（Q9 的单点决策）。

    `artifact=txt` → 只落 `.txt` + `.raw.json`，**不存在** `.srt` 文件；
    `artifact=srt` → 落 `.txt` + `.srt` + `.raw.json`。
    """
    kinds = select_product_kinds(artifact)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    txt_path = out / f"{stem}.txt"
    raw_path = out / f"{stem}.raw.json"
    txt_path.write_text(products.txt, encoding="utf-8")
    srt_path: Path | None = None
    if "srt" in kinds:
        srt_path = out / f"{stem}.srt"
        srt_path.write_text(products.srt, encoding="utf-8")
    raw_path.write_text(json.dumps(products.raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return WrittenProducts(out_dir=out, txt_path=txt_path, srt_path=srt_path, raw_path=raw_path)
