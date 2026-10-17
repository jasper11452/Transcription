"""align —— 对齐：文本与时间轴、单调时间不变量。

**Phase 3 才落地**（`REIMAGINED_ARCHITECTURE.md` §5：`post/` 在 Phase 1 只含
`glossary.py` + `render.py`）。本模块只固化签名与不变量，不提供半成品实现 ——
调用它会得到明确的 `NotImplementedError`，而不是一个静默出错的结果。

归属理由（§2b）：`build_segments` 的调用点拿到的是普通 `Word` 列表，与具体引擎无关；
「单调时间不变量」是 post 的性质，不是引擎适配的性质。因此 align 住在 `post`。

落地时要满足的规则（`AI_NATIVE_SPEC.md` §5 之外的 align 三条）：
- `RULE-008` 字幕行的断句规则（硬断 `。！？!?…\\n`；软断 `，,；;、：:`；`MAX_SEGMENT_S=15.0`）
- `RULE-009` 无可用时间戳时的兜底时间分配（`nominal = max(1.0, 0.25 * len(text))`）
- `RULE-010` 字级时间映射与单调时间不变量（标点与空白不参与对齐；时间取 3 位小数）
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .domain import Segment, Word

# 常量按规则卡先落在这里，实现时不得放宽（`RULE-008` / `RULE-009` / `RULE-010`）。
HARD_BREAK = "。！？!?…\n"
SOFT_BREAK = "，,；;、：:"
MAX_SEGMENT_S = 15.0
SOFT_BREAK_MIN_CHARS = 12
SOFT_BREAK_MIN_S = 5.0
MIN_TAIL_CHARS = 4
MIN_SEGMENT_S = 0.35
MIN_DURATION_S = 0.05
TIME_DECIMALS = 3


def normalize_for_compare(text: str) -> str:
    """比对用归一化：抹掉标点与空白的差异，只看正文字符。

    用途是「两次转写是否只差标点」这条一致性判据。
    """
    raise NotImplementedError(
        "align.normalize_for_compare 属 Phase 3（RULE-010）；Phase 1 的 post 只含 glossary + render"
    )


def build_segments(
    text: str,
    words: Sequence[Word] | None = None,
    *,
    duration_s: float | None = None,
) -> list[Segment]:
    """把引擎给的文本与词级时间戳切成带时间轴的段落（`RULE-008` / `RULE-009` / `RULE-010`）。

    不变量：产出的段落时间**单调不减**；任何段落时长 `>= MIN_DURATION_S`；
    文本为空时返回空列表（不造段）。
    """
    raise NotImplementedError(
        "align.build_segments 属 Phase 3（RULE-008 / RULE-009 / RULE-010）；"
        "Phase 1 的 post 只含 glossary + render"
    )


def align_words(
    text: str, words: Iterable[Word], *, duration_s: float | None = None
) -> list[Segment]:
    """字级/词级时间映射（`RULE-010`）的入口别名，Phase 3 与 `build_segments` 合并实现。"""
    raise NotImplementedError("align.align_words 属 Phase 3（RULE-010）")
