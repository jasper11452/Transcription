"""merge —— 去重：只在分片边界去重、正文零丢失。

**Phase 3 才落地**（`REIMAGINED_ARCHITECTURE.md` §5）。本模块只固化签名与常量，
调用即 `NotImplementedError`。

落地时要满足的规则：
- `RULE-001`（**P0-1**）分片边界去重、绝不丢正文 —— 重复文字只在两个分片拼接处去掉，
  且只在切完还剩非空内容时才丢弃；时间戳重叠单独修
- `RULE-023` 成本跨片累加，audio_seconds 不聚合（各引擎口径不同）
- `RULE-024` 相邻分片的重叠判定

⚠️ 写测试前必读 `AI_NATIVE_SPEC.md` §5.4：P0-1 的**例子**在规则卡里是错的 ——
`longest_overlap` 要求 `>= _MIN_OVERLAP_CHARS = 4` 的重叠，3 字符的重叠检测为 0、
重复文本原样保留。生日判据必须用 ≥4 字符的重叠。
⚠️ `RULE-024` 的 `_MIN_COVERAGE` 可执行常量是 **0.8**，而 docstring 写的是 70% ——
以代码为准（更严格的那个），docstring 的意图（保守阈值来自一次 87 分钟录音丢 111 字
的真实事故）保留。
"""

from __future__ import annotations

from collections.abc import Sequence

from .domain import Segment

# 重叠窗口与阈值（`RULE-024`）。实现时不得放宽。
OVERLAP_WINDOW_CHARS = 240
MIN_OVERLAP_CHARS = 4
TAIL_TOLERANCE = 3
HEAD_TOLERANCE = 1
GAP_TOLERANCE = 1
MIN_COVERAGE = 0.8  # docstring 说 70%，代码是 80% —— 以代码为准（更严格）
MIN_SEGMENT_S = 0.05

# 去重切掉后要剥掉的行首标点（`RULE-001`）。
LEADING_PUNCTUATION = "。！？!?…，,；;、：:. \n\t"


def longest_overlap(prev_text: str, next_text: str) -> int:
    """两个相邻分片文本的最长重叠字符数（`RULE-024`）；小于阈值视为无重叠。"""
    raise NotImplementedError("merge.longest_overlap 属 Phase 3（RULE-024）")


def merge_results(results: Sequence[object]) -> object:
    """把按分片顺序排列的转写结果合并成一份（`RULE-001` / `RULE-023` / `RULE-024`）。

    不变量：正文零丢失；分片内部段落之间绝不去重；时间轴修好使播放器不会同时显示两行。
    """
    raise NotImplementedError(
        "merge.merge_results 属 Phase 3（RULE-001 / RULE-023 / RULE-024）；"
        "Phase 1 的 post 只含 glossary + render"
    )


def repair_timeline(segments: Sequence[Segment]) -> list[Segment]:
    """修相邻段落的时间戳重叠（`RULE-001` 的后半句），画面不叠行。"""
    raise NotImplementedError("merge.repair_timeline 属 Phase 3（RULE-001）")
