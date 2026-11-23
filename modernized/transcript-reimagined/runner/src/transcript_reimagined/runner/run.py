"""纵向切片的执行体：元数据 → 分片计划 → 词表替换 → 渲染 → 落盘。

这是「重写一个模块的标准动作」的载体：一次真实运行会穿过三层（``runner`` →
``{ingest, post}`` → ``domain``）、读写真实文件系统、并按单点决策产出三个文件。

有意不做的事（架构 §5 的范围约束）：不含 config、不含 store、不含 pipeline、不含 web；
不含真实 ffprobe/VAD/引擎调用；不含重试与并发（那些属 Phase 5 的 orchestrate）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from transcript_reimagined.domain import Change, Chunk, Segment
from transcript_reimagined.ingest import plan_chunks
from transcript_reimagined.post import apply_rules, change_comment, load_glossary, to_srt, to_txt

from .metadata import AudioMetadata, MetadataError, load_metadata, parse_metadata
from .products import (
    ALLOWED_ARTIFACTS,
    ProductError,
    ProductPaths,
    select_products,
    write_products,
)

ENTRY_ID = "transcript-runner (phase-1 vertical slice)"


@dataclass(frozen=True)
class RunRequest:
    """一次运行的全部入参。三个元数据来源互斥，必须且只能给一个。"""

    metadata_path: Path | None = None
    metadata_text: str | None = None
    metadata: AudioMetadata | None = None
    out_dir: Path = Path("out")
    glossary_path: Path | None = None
    artifact: str | None = None  # 覆盖元数据里的 artifact
    stem: str | None = None  # 覆盖产物文件名（默认取源文件 stem）


@dataclass
class RunResult:
    """一次运行的事实与产物。"""

    metadata: AudioMetadata
    artifact: str
    paths: ProductPaths
    chunks: list[Chunk]
    changes: list[Change]
    txt: str
    srt: str
    raw: dict
    trace: list[str] = field(default_factory=list)

    @property
    def files(self) -> dict[str, str]:
        return self.paths.written()


def _resolve_metadata(request: RunRequest) -> AudioMetadata:
    given = [
        request.metadata is not None,
        request.metadata_text is not None,
        request.metadata_path is not None,
    ]
    if sum(given) != 1:
        raise MetadataError("必须且只能提供 metadata / metadata_text / metadata_path 之一")
    if request.metadata is not None:
        return request.metadata
    if request.metadata_text is not None:
        return parse_metadata(request.metadata_text)
    assert request.metadata_path is not None  # 由上面 count 保证
    return load_metadata(request.metadata_path)


def _slice_segments(segments: tuple[Segment, ...], rules) -> tuple[list[Segment], list[Change]]:
    """对段落做与正文同一套替换，保证 srt 与 txt 的用词一致。"""
    if not rules:
        return list(segments), []
    sliced: list[Segment] = []
    changes: list[Change] = []
    for seg in segments:
        text, seg_changes = apply_rules(seg.text, rules)
        changes.extend(seg_changes)
        sliced.append(Segment(seg.start, seg.end, text, seg.words, seg.speaker))
    return sliced, changes


def _artifact_for(request: RunRequest, metadata: AudioMetadata) -> str:
    artifact = request.artifact if request.artifact is not None else metadata.artifact
    if artifact not in ALLOWED_ARTIFACTS:
        raise ProductError(f"artifact 只能是 {' / '.join(ALLOWED_ARTIFACTS)}，收到：{artifact!r}")
    return artifact


def _chunk_rows(chunks: list[Chunk]) -> list[dict]:
    """``.raw.json`` 里的分片记录。

    键与 legacy 的 ``.raw.json`` 对齐（``RULE-034`` / ``RULE-132`` 的消费面），
    但**状态**是 ``planned``：本阶段不执行引擎调用，只有计划，没有分片级结果。
    """
    return [
        {
            "idx": c.index,
            "start": c.start,
            "end": c.end,
            "status": "planned",
            "text": None,
            "attempts": 0,
            "error": None,
            "words": [],
        }
        for c in chunks
    ]


def run(request: RunRequest) -> RunResult:
    """跑一次切片。失败（``ProductError`` / ``MetadataError``）时**不写任何文件**。"""
    trace: list[str] = []
    metadata = _resolve_metadata(request)
    artifact = _artifact_for(request, metadata)
    trace.append(f"artifact={artifact} mode={metadata.mode}")

    rules = load_glossary(request.glossary_path) if request.glossary_path else []
    trace.append(f"glossary: {len(rules)} 条替换规则")

    chunk = metadata.chunk
    chunks = plan_chunks(
        list(metadata.spans),
        metadata.duration_s,
        min_s=chunk.min_s,
        max_s=chunk.max_s,
        overlap_s=chunk.overlap_s,
    )
    trace.append(
        f"plan: {len(chunks)} 片（min_s={chunk.min_s} max_s={chunk.max_s} "
        f"overlap_s={chunk.overlap_s}）"
    )

    final_text, changes = apply_rules(metadata.merged_text, rules)
    segments, seg_changes = _slice_segments(metadata.segments, rules)
    trace.append(f"glossary: 正文替换 {len(changes)} 项，段落替换 {len(seg_changes)} 项")
    comment = change_comment(changes)

    stem = request.stem or metadata.path.stem or "output"
    paths = select_products(
        Path(request.out_dir),
        stem,
        artifact=artifact,
        has_timestamps=metadata.has_timestamps,
        engine=metadata.engine,
    )
    trace.append(f"products: {sorted(paths.written())}")

    # 段落交给 to_txt 是**有意的**：激活 RULE-136 的说话人分块契约（见 LEGACY_DEVIATIONS.md）。
    txt_content = to_txt(final_text, segments or None, comment_lines=comment)
    srt_content = to_srt(segments, comment_lines=comment) if paths.srt is not None else ""

    raw_payload: dict = {
        "produced_by": ENTRY_ID,
        "task_id": metadata.task_id,
        "source": str(metadata.path),
        "mode": metadata.mode,
        "artifact": artifact,
        "engine": metadata.engine,
        "chunk_count": len(chunks),
        "chunk_params": {
            "min_s": chunk.min_s,
            "max_s": chunk.max_s,
            "overlap_s": chunk.overlap_s,
        },
        "chunks": _chunk_rows(chunks),
        "merged_text_before_glossary": metadata.merged_text,
        "final_text": final_text,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
        "glossary_changes": [
            {"wrong": c.wrong, "right": c.right, "count": c.count} for c in changes
        ],
    }
    write_products(
        paths,
        txt_content=txt_content,
        srt_content=srt_content,
        raw_payload=raw_payload,
    )
    trace.append(f"write: {paths.raw_json.name}")

    return RunResult(
        metadata=metadata,
        artifact=artifact,
        paths=paths,
        chunks=chunks,
        changes=changes,
        txt=txt_content,
        srt=srt_content,
        raw=raw_payload,
        trace=trace,
    )
