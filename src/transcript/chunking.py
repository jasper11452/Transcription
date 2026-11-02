"""切片规划：把语音区间拼成 30–120s 的片，边界落在静音处并留重叠。

纯函数，不依赖模型/ffmpeg，因此可以独立单测——切片错了，后面全错。

**核心不变量**（回归测试守着它）：`chunk.duration <= max_s`。
这条不是审美问题：在线引擎有单次硬限（百炼 300s），片长了会被上游直接拒。
实现方式是把重叠算在预算内（`inner = max_s - overlap`），切点优先取静音间隙，
但**只接受放得下的那个间隙**；放不下就按 `inner` 硬切。
"""

from __future__ import annotations

from .models import Chunk

# 静音间隙小于这个值不值得作为边界
MIN_GAP_FOR_CUT_S = 0.15
# 再短的片没有意义；同时保证 inner 至少还能切出东西
MIN_INNER_S = 1.0


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
    - 切点优先落在静音间隙中点；但片长必须放得进 `max_s`（含左右外扩的重叠）；
    - 找不到可用间隙时按 `inner` 硬切，连续长语音也能被切开；
    - 每片左右各外扩 `overlap_s/2`，使相邻片有重叠，合并阶段再去重；
    - 全程只覆盖 `[0, duration]`，不留缝也不越界。
    """
    if duration <= 0:
        return []
    if min_s <= 0 or max_s < min_s:
        raise ValueError(f"切片参数非法：min_s={min_s} max_s={max_s}")

    overlap = max(0.0, overlap_s)
    half = overlap / 2
    # 每片的"内容长度"预算：外扩 overlap 之后总长仍然 ≤ max_s
    inner = max(MIN_INNER_S, max_s - overlap)
    target = min(min_s, inner)

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
                candidate = (spans[j][1] + spans[j + 1][0]) / 2
                if candidate - cursor > inner:
                    break  # 再往后就放不下了，就用目前最好的
                best = candidate
                if acc >= target:
                    break  # 已经够长且落在静音处，就是它了
            if acc >= inner:
                break
            j += 1

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

    return chunks or [Chunk(index=0, start=0.0, end=duration)]
