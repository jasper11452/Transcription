"""`transcript-post-run` —— Phase 1 的最小纵向切片入口（`post` 这一侧）。

架构 §5 要求 Phase 1 有一条**可执行的纵向切片**，而不是只把纯函数搬进来：
读一份元数据 JSON → 词表 → 渲染 → 写真实的 `.txt` / `.srt` / `.raw.json` 到磁盘。
这样试点才碰到文件 I/O、跨包 import 与产物落盘。

**post 的位置在切片的下游**：本入口消费分片计划与逐片文本，产出三个产物；
分片规划属 `ingest` 包，本入口**不重新实现** `chunking`（Phase 1 里 `ingest` 由
另一个服务并行脚手架）。要跑通完整切片时，把 `ingest` 产出的 JSON 一次喂进来。

输入 JSON（`--input <file>` 或 stdin）:

```json
{
  "source": "meeting.m4a",
  "artifact": "srt",
  "merged_text": "我们把集成做完了",
  "segments": [{"start": 0.0, "end": 3.2, "text": "我们把集成做完了", "speaker": null}],
  "glossary": "小新\n集成 -> 集诚\n",
  "glossary_path": "/path/to/glossary.txt",
  "chunks": [{"idx": 0, "start": 0.0, "end": 120.0, "status": "done", "text": "…"}]
}
```

用法::

    transcript-post-run --input plan.json --out-dir out --stem meeting

`artifact="srt"` 而没有任何段落时**拒绝出产物**（`RULE-061`：没有时间轴就不写 srt）。
`artifact="txt"` 只写 `.txt` + `.raw.json`，**不写** `.srt`（Q9 裁定）。产物落盘位置
由本入口决定 —— 它是 orchestrate 单点决策在 Phase 1 的替身（架构 §2：产物选择必须是
单点决策）。

安全（NFR-4）：本入口不读、不接受任何凭据；`source` 只是 provenance 字符串。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .domain import Change, Segment, Word
from .glossary import apply_rules, change_header_line, hotwords, parse_glossary, parse_hot_words
from .products import (
    ProductSet,
    RawContext,
    render_products_for,
    write_products_for,
)


class InputError(Exception):
    """输入 JSON 不合法 —— 明确失败，不猜。"""


@dataclass(frozen=True)
class BuiltProducts:
    """切片入口的装配结果。"""

    products: ProductSet
    changes: list[Change] = field(default_factory=list)
    words: list[str] = field(default_factory=list)

    @property
    def header(self) -> str:
        return change_header_line(self.changes)


def parse_segments(raw: Any) -> list[Segment]:
    """把输入 JSON 里的 `segments` 转成 `Segment` 列表。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InputError("segments 必须是数组")
    segments: list[Segment] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise InputError(f"segments[{i}] 必须是对象")
        try:
            text = str(item["text"])
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"segments[{i}] 缺字段或类型不对：{exc}") from exc
        words = [
            Word(str(w["text"]), float(w["start"]), float(w["end"]), w.get("probability"))
            for w in item.get("words", [])
        ]
        speaker = item.get("speaker")
        segments.append(
            Segment(start, end, text, words=words, speaker=str(speaker) if speaker else None)
        )
    return segments


def load_glossary_text(payload: dict[str, Any]) -> str:
    """词表来源优先级：内联 `glossary` > `glossary_path` 指向的文件 > 空。

    刻意不做配置优先级（`RULE-105` 属 Phase 2 的 `config` 包，架构 §5 的范围约束
    明确排除 `config`）—— 入口只接受调用方指定的路径。
    """
    if payload.get("glossary") is not None:
        return str(payload["glossary"])
    path = payload.get("glossary_path")
    if path:
        p = Path(str(path)).expanduser()
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return ""


def build_products(payload: dict[str, Any]) -> BuiltProducts:
    """payload → 三个产物的文本（不落盘）。入口与验收测试共用这一条路径。"""
    merged_text = str(payload.get("merged_text", ""))
    segments = parse_segments(payload.get("segments"))
    artifact = str(payload.get("artifact", "srt"))
    glossary_text = load_glossary_text(payload)

    rules = parse_glossary(glossary_text)
    final_text, changes = apply_rules(merged_text, rules)
    # 逐段替换只为字幕文本服务；计数只以整段那一次为准（RULE-022 的边界说明）。
    replaced_segments = [
        Segment(s.start, s.end, apply_rules(s.text, rules)[0], s.words, s.speaker) for s in segments
    ]

    if artifact == "srt" and not replaced_segments:
        raise InputError("引擎不提供时间戳，无法产出 srt（改用 artifact=txt 或换引擎）")

    ctx = RawContext(
        mode=payload.get("mode"),
        artifact=artifact,
        engine=payload.get("engine"),
        task_id=payload.get("task_id"),
        source=payload.get("source"),
        config=payload.get("config"),
        chunks=list(payload.get("chunks") or []),
    )
    products = render_products_for(
        final_text,
        replaced_segments,
        changes,
        artifact=artifact,
        merged_text_before_glossary=merged_text,
        context=ctx,
    )
    return BuiltProducts(
        products=products,
        changes=changes,
        words=hotwords(rules, extra=parse_hot_words(glossary_text)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transcript-post-run",
        description="post 的最小纵向切片入口：元数据 JSON → 词表 → 渲染 → 三个产物",
    )
    parser.add_argument("--input", help="输入 JSON 路径（省略则读 stdin）")
    parser.add_argument("--out-dir", required=True, help="产物输出目录")
    parser.add_argument("--stem", help="产物文件名（默认取 source 的 stem）")
    args = parser.parse_args(argv)

    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"输入不是合法 JSON：{exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("输入 JSON 顶层必须是对象", file=sys.stderr)
        return 2

    source = payload.get("source")
    stem = args.stem or (Path(str(source)).stem if source else "transcript")
    try:
        built = build_products(payload)
    except InputError as exc:
        print(f"拒绝出产物：{exc}", file=sys.stderr)
        return 1

    written = write_products_for(
        built.products, args.out_dir, stem, artifact=str(payload.get("artifact", "srt"))
    )
    print(
        json.dumps(
            {
                "out_dir": str(written.out_dir),
                "txt_path": str(written.txt_path),
                "srt_path": str(written.srt_path) if written.srt_path else None,
                "raw_path": str(written.raw_path),
                "changes": [c.describe() for c in built.changes],
                "hotwords": built.words,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
