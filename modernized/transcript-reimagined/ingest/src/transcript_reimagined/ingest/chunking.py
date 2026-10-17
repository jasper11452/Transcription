"""切片规划：把语音区间拼成 30–120s 的片，边界落在静音处并留重叠。

纯函数，不依赖模型/ffmpeg，因此可以独立单测 —— 切片错了，后面全错。

**核心不变量**（回归测试守着它）：``chunk.duration <= max_s``。
这条不是审美问题：在线引擎有单次硬限（百炼 300s），片长了会被上游直接拒。
实现方式是把重叠算在预算内（``inner = max_s - overlap``），切点优先取静音间隙，
但**只接受放得下的那个间隙**；放不下就按 ``inner`` 硬切。

承载的规则（``AI_NATIVE_SPEC.md`` §5.2）：
- ``RULE-011`` 分片预算与长度不变量（``plan_chunks`` 的整体形状）
- ``RULE-012`` 切点优先落静音（``best`` 候选与两处 clamp）

搬运自 ``legacy/transcript/src/transcript/chunking.py``（Phase 1 要求逐字节等价，
由 ``tests/test_equivalence_with_legacy_chunking.py`` 做差分验证）。
**唯二**相对 legacy 的改动：``Chunk`` 从 ``domain`` 包导入（架构要求 ``ingest``
只依赖 ``domain``），以及把派生预算值收敛到 ``ChunkPlan``（行为不变）。

本模块零 I/O、零第三方依赖：只 import stdlib 与 ``domain``。
"""

from __future__ import annotations

from ..domain.models import Chunk
from .plan import MIN_GAP_FOR_CUT_S, MIN_INNER_S, ChunkPlan

__all__ = ["MIN_GAP_FOR_CUT_S", "MIN_INNER_S", "plan_chunks", "plan_chunks_with"]


def plan_chunks(
    spans: list[tuple[float, float]],
    duration: float,
    *,
    min_s: float = 30.0,
    max_s: float = 120.0,
    overlap_s: float = 0.5,
) -> list[Chunk]:
    """生成切片计划。

    规则：
    - 切点优先落在静音间隙中点；但片长必须放得进 ``max_s``（含左右外扩的重叠）；
    - 找不到可用间隙时按 ``inner`` 硬切，连续长语音也能被切开；
    - 每片左右各外扩 ``overlap_s/2``，使相邻片有重叠，合并阶段再去重；
    - 全程只覆盖 ``[0, duration]``，不留缝也不越界。

    ``duration <= 0`` 返回空计划；``min_s <= 0`` 或 ``max_s < min_s`` 抛 ``ValueError``。

    ⚠️ 两个检查的**顺序**是契约的一部分：``duration <= 0`` 先行返回，所以
    ``plan_chunks([], 0.0, min_s=0, max_s=0)`` 返回 ``[]`` 而不是抛错。
    调换顺序会让这里与 legacy 分道扬镳。
    """
    if duration <= 0:
        return []

    # 参数非法抛 ValueError 而不是规划出坏计划；报错文本与 legacy 一致。
    # 用 ChunkPlan 持有派生值：overlap / half / inner / target 只在 plan.py 里算一次，
    # 这里只取用 —— 公式若被改坏，改的是同一个地方，不会出现两份真相。
    plan = ChunkPlan(min_s=min_s, max_s=max_s, overlap_s=overlap_s)
    half = plan.half
    inner = plan.inner
    target = plan.target

    if duration <= target:
        return [Chunk(index=0, start=0.0, end=duration)]

    spans = sorted((max(0.0, s), min(duration, e)) for s, e in spans if e > s)

    cuts: list[float] = []
    cursor = 0.0
    i = 0
    while duration - cursor > inner:
        acc = 0.0
        j = i
        best: float | None = None
        while j < len(spans) and spans[j][1] > cursor:
            acc += spans[j][1] - spans[j][0]
            gap_after = spans[j + 1][0] - spans[j][1] if j + 1 < len(spans) else None
            if gap_after is not None and gap_after >= MIN_GAP_FOR_CUT_S:
                # 间隙的中点，但只接受还放得进 inner 的那个（再往后就放不下了）
                candidate = (spans[j][1] + spans[j + 1][0]) / 2
                if candidate - cursor > inner:
                    break  # 再往后就放不下了，就用目前最好的
                best = candidate
                if acc >= target:
                    break  # 已经够长且落在静音处，就是它了
            if acc >= inner:
                break
            j += 1

        # 没有可用间隙（连续语音）时硬切；两处 clamp 见 RULE-012
        cut = best if best is not None else cursor + inner
        cut = max(cursor + MIN_INNER_S, min(duration, cut))
        cuts.append(cut)
        cursor = cut
        while i < len(spans) and spans[i][1] <= cursor:
            i += 1

    bounds = [0.0, *cuts, duration]
    chunks: list[Chunk] = []
    for idx in range(len(bounds) - 1):
        raw_start, raw_end = bounds[idx], bounds[idx + 1]
        if raw_end - raw_start <= 0.01:
            continue
        start = max(0.0, raw_start - half) if idx > 0 else 0.0
        end = min(duration, raw_end + half) if idx < len(bounds) - 2 else duration
        # 浮点保护：不变量成立时这里是空操作
        end = min(end, start + max_s)
        chunks.append(Chunk(index=len(chunks), start=start, end=max(start, end)))

    # 末路兜底：所有片段都被过滤掉时退化为整段一片（不是空计划 ——
    # 「切不出片」和「不切」对调用方是两件不同的事）
    return chunks or [Chunk(index=0, start=0.0, end=duration)]


def plan_chunks_with(
    spans: list[tuple[float, float]],
    duration: float,
    plan: ChunkPlan,
) -> list[Chunk]:
    """``plan_chunks`` 的预算对象版本 —— 调用方（``orchestrate``）持有一个
    ``ChunkPlan`` 时用它，免得把三个字段在调用点拆开再传。

    纯转发，不重复实现：两者行为必须完全一致（有测试钉住这一点）。
    """
    return plan_chunks(
        spans,
        duration,
        min_s=plan.min_s,
        max_s=plan.max_s,
        overlap_s=plan.overlap_s,
    )
