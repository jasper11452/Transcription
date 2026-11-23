"""切片规划的领域模型：分片预算（`AI_NATIVE_SPEC.md` §2 的 `CHUNK_PLAN` 实体）。

架构把 `CHUNK_PLAN` 的归属定在 `ingest`（`REIMAGINED_ARCHITECTURE.md` §2）——
它是「音频该切成哪几片」这件事的输入参数与不变量，不属于全系统公共词汇，
所以不放在 `domain`。公共词汇（`Chunk` / `Segment` / `Word` / `AudioInfo`）住 `domain`。

纯数据 + 纯校验，零 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass

# 静音间隙小于这个值不值得作为边界（`chunking.py:16`）。
MIN_GAP_FOR_CUT_S = 0.15
# 再短的片没有意义；同时保证 inner 至少还能切出东西（`chunking.py:18`）。
MIN_INNER_S = 1.0


@dataclass(frozen=True)
class ChunkPlan:
    """一次切片规划的预算参数。

    - `min_s`：单片的目标下限。它**不是**硬下限：最后一个片的尾巴通常比它短，
      而且 `min_s > inner` 时会被 `inner` 压小（否则 `plan_chunks` 会因为参数矛盾直接报错）。
    - `max_s`：硬上限。`chunk.duration <= max_s` 是**物理不变量**，不是审美问题 ——
      在线引擎有单次硬限（百炼 300s），片长了会被上游直接拒（`RULE-011`）。
    - `overlap_s`：相邻片左右各外扩 `overlap_s/2`，使相邻片重叠，合并阶段再去重。

    `inner`（内容预算）把重叠算进去，所以外扩之后总长仍然 `<= max_s`：

        inner = max(MIN_INNER_S, max_s - overlap)

    参数的合法性在**构造时**校验（`min_s <= 0` 或 `max_s < min_s` 抛 `ValueError`），
    与遗留实现 `plan_chunks` 的报错文本一致 —— Phase 1 要求逐字节等价。
    """

    min_s: float = 30.0
    max_s: float = 120.0
    overlap_s: float = 0.5

    def __post_init__(self) -> None:
        if self.min_s <= 0 or self.max_s < self.min_s:
            raise ValueError(f"切片参数非法：min_s={self.min_s} max_s={self.max_s}")

    @property
    def overlap(self) -> float:
        """负的重叠没有意义，按 0 处理（只有 `overlap_s >= 0` 才可能让不变量失效）。"""
        return max(0.0, self.overlap_s)

    @property
    def half(self) -> float:
        """每侧外扩量。"""
        return self.overlap / 2

    @property
    def inner(self) -> float:
        """每片的内容长度预算：外扩 `overlap` 之后总长仍然 `<= max_s`。"""
        return max(MIN_INNER_S, self.max_s - self.overlap)

    @property
    def target(self) -> float:
        """切点扫描的提前停止阈值：攒够这么长的语音且落在静音处就切。"""
        return min(self.min_s, self.inner)

    @property
    def single_chunk_budget(self) -> float:
        """装得下就不切 —— 多切一片就是多一次引擎调用（在线就是多花钱）。"""
        return self.target
