"""文本与时间轴对齐。

背景（实测结论，见 docs/spec.md 与 spikes/probe_offline_timestamps.py）：
Qwen3-ASR 输出质量高但**不提供细粒度时间戳**，whisper 提供词级时间戳但会丢标点。
所以：以 whisper 的词时间戳为骨架，把 Qwen 的文本按字符相似度映射上去，再按标点组句。

这里的核心不变式：**时间必须单调不减**，且每个字都要有归属——错配只能表现为
"边界不精确"，不能表现为"整句丢失或乱序"。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Segment, Word

HARD_BREAK = frozenset("。！？!?…\n")
SOFT_BREAK = frozenset("，,；;、：:")

MIN_SEGMENT_S = 0.35
MAX_SEGMENT_S = 15.0
SOFT_BREAK_MIN_CHARS = 12
SOFT_BREAK_MIN_S = 5.0
MIN_TAIL_CHARS = 4
_MIN_DURATION_S = 0.05


def _is_content_char(ch: str) -> bool:
    """内容字符：中日韩、字母、数字。标点与空白不参与对齐。"""
    return ch.isalnum()


def _char_spans(words: list[Word]) -> tuple[str, list[tuple[float, float]]]:
    """把词级时间戳展开成"逐字符时间"，得到可比对的骨架。"""
    chars: list[str] = []
    spans: list[tuple[float, float]] = []
    for word in words:
        for ch in word.text:
            if _is_content_char(ch):
                chars.append(ch)
                spans.append((word.start, word.end))
    return "".join(chars), spans


def _interpolate(times: list[tuple[float, float] | None]) -> list[tuple[float, float]]:
    """给未匹配上的字符补时间：在左右已知点之间线性插值，端点用最近值。"""
    n = len(times)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        return [(0.0, 0.0)] * n
    out: list[tuple[float, float] | None] = list(times)
    for idx in range(known[0]):
        out[idx] = times[known[0]]
    for idx in range(known[-1] + 1, n):
        out[idx] = times[known[-1]]
    for left, right in zip(known, known[1:], strict=False):
        if right - left <= 1:
            continue
        a, b = times[left], times[right]
        assert a is not None and b is not None
        step_s = (b[0] - a[0]) / (right - left)
        step_e = (b[1] - a[1]) / (right - left)
        for k in range(1, right - left):
            out[left + k] = (a[0] + step_s * k, a[1] + step_e * k)
    return [t or (0.0, 0.0) for t in out]


def map_times(text: str, words: list[Word]) -> list[tuple[float, float] | None]:
    """文本（含标点）逐字符 → 时间。标点位置为 None。"""
    skeleton, spans = _char_spans(words)
    content = "".join(ch for ch in text if _is_content_char(ch))
    if not skeleton or not content:
        return [None] * len(text)

    matcher = SequenceMatcher(None, skeleton, content, autojunk=False)
    content_times: list[tuple[float, float] | None] = [None] * len(content)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                content_times[j1 + offset] = spans[i1 + offset]
        elif tag == "replace":
            # 长度不等时按比例落位：宁可按比例分，也不要让整块丢失
            w_len = (i2 - i1) or 1
            for offset in range(j2 - j1):
                src = i1 + min(w_len - 1, int(offset * w_len / max(1, j2 - j1)))
                content_times[j1 + offset] = spans[src]

    filled = _interpolate(content_times)
    out: list[tuple[float, float] | None] = []
    it = iter(filled)
    for ch in text:
        out.append(next(it) if _is_content_char(ch) else None)
    return out


def _window_duration(
    char_times: list[tuple[float, float] | None], start: int, end: int
) -> float | None:
    """窗口 [start, end) 内已知时间的实障跨度。"""
    known = [t for t in char_times[start:end] if t]
    if not known:
        return None
    return known[-1][1] - known[0][0]


def _tail_after_last_punct(text: str, start: int, end: int) -> str:
    """窗口 [start, end) 内**当前标点之前**最后一个标点之后的文字。

    要把正在判定的那个标点排除掉，否则尾巴总是空字符串，规则永远不成立。
    """
    for idx in range(end - 2, start, -1):
        if idx < len(text) and text[idx] in HARD_BREAK | SOFT_BREAK:
            return text[idx + 1 : end - 1]
    return text[start : end - 1]


def split_sentence_ranges(
    char_times: list[tuple[float, float] | None],
    text: str,
    *,
    max_segment_s: float = MAX_SEGMENT_S,
    soft_min_chars: int = SOFT_BREAK_MIN_CHARS,
    soft_min_s: float = SOFT_BREAK_MIN_S,
    min_tail_chars: int = MIN_TAIL_CHARS,
) -> list[tuple[int, int]]:
    """按标点 + 时长上限切分句子，返回 [start, end) 字符下标区间。

    四条断句规则（按优先级）：
    1. 句末标点（。！？）—— 一定断；
    2. 句中标点（，；：）—— 当内容已经够长（字数或时长）才断，产生“可读的一行”；
    3. **不以悬空引导词结尾**：“第一，…” “第二，” 这种尾巴不能单独收尾，
       否则字幕会停在上面，人读到“第二，”就断了；
    4. 硬上限 —— 一直没有标点时必须断开。
    """
    ranges: list[tuple[int, int]] = []
    start = 0
    for idx, ch in enumerate(text):
        end = idx + 1
        boundary = ch in HARD_BREAK
        if not boundary and ch in SOFT_BREAK:
            span = _window_duration(char_times, start, end)
            long_enough = (end - start) >= soft_min_chars or (
                span is not None and span >= soft_min_s
            )
            has_tail = len(_tail_after_last_punct(text, start, end).strip()) >= min_tail_chars
            boundary = long_enough and has_tail
        if not boundary:
            span = _window_duration(char_times, start, end)
            boundary = span is not None and span >= max_segment_s
        if boundary:
            ranges.append((start, end))
            start = end
    if start < len(text):
        ranges.append((start, len(text)))
    return [(s, e) for s, e in ranges if text[s:e].strip()]


def build_segments(
    text: str,
    words: list[Word],
    *,
    offset: float = 0.0,
    min_segment_s: float = MIN_SEGMENT_S,
    fallback_duration: float | None = None,
) -> list[Segment]:
    """文本 + 词级时间戳 → 带时间轴的句子段。

    时间戳缺失时**不丢内容**：按等比/名义时长铺开。宁可时间不精确，
    也不能让用户拿到一份缺字的稿子（内容丢失比时间不准严重得多）。
    """
    if not text.strip():
        return []
    char_times = map_times(text, words)
    if not any(t for t in char_times):
        return _fallback_segments(
            text, offset=offset, duration=fallback_duration, min_segment_s=min_segment_s
        )

    segments: list[Segment] = []
    prev_end = offset
    for start, end in split_sentence_ranges(char_times, text):
        chunk_text = text[start:end]
        times = [t for t in char_times[start:end] if t]
        if not times:
            continue
        seg_start = max(prev_end, times[0][0] + offset)
        seg_end = max(seg_start + min_segment_s, times[-1][1] + offset)
        segments.append(
            Segment(
                start=round(seg_start, 3),
                end=round(seg_end, 3),
                text=chunk_text.strip(),
                words=[w for w in words if seg_start - offset <= w.start <= seg_end - offset],
            )
        )
        prev_end = seg_start + _MIN_DURATION_S
    return enforce_monotonic(segments)


def _fallback_segments(
    text: str,
    *,
    offset: float,
    duration: float | None,
    min_segment_s: float,
) -> list[Segment]:
    """对齐骨架完全不可用时的兜底：按句等分时间，内容一字不丢。"""
    ranges = split_sentence_ranges([None] * len(text), text)
    pieces = [text[s:e].strip() for s, e in ranges if text[s:e].strip()]
    if not pieces:
        pieces = [text.strip()]
    total = duration if duration and duration > 0 else max(1.0, 0.25 * len(text))
    step = max(min_segment_s, total / len(pieces))
    return enforce_monotonic(
        [
            Segment(
                start=round(offset + i * step, 3), end=round(offset + (i + 1) * step, 3), text=piece
            )
            for i, piece in enumerate(pieces)
        ]
    )


def enforce_monotonic(segments: list[Segment]) -> list[Segment]:
    """时间单调不减：交集/倒序会让播放器与剪辑软件丢弃整段字幕。"""
    out: list[Segment] = []
    prev_end = 0.0
    for seg in segments:
        start = max(seg.start, prev_end)
        end = max(seg.end, start + _MIN_DURATION_S)
        if not seg.text.strip():
            continue
        out.append(
            Segment(start=round(start, 3), end=round(end, 3), text=seg.text, words=seg.words)
        )
        prev_end = end
    return out


def normalize_for_compare(text: str) -> str:
    """比较两份转写是否"只是专名与标点不同"时用的归一化。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
