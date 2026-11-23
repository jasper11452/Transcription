"""产物渲染：txt / srt。

承载的规则（`AI_NATIVE_SPEC.md` §5.2）：
- `RULE-062` SRT 拒绝倒序时间、编号只数存活行
- `RULE-135` SRT 长行折行（42 字符）
- `RULE-136` 带说话人的文本输出分块

`RULE-132`（替换痕迹写进产物）由 `comment_lines` 入参承接 —— 渲染层只负责加
`#` 前缀，注释内容由 `glossary.change_comment` 给出。

SRT 的两个硬要求：时间格式合法（`HH:MM:SS,mmm`）、时间单调不减。外加本工具
的要求：**错误文本绝不混进产物 —— 宁可任务失败**（`to_srt` 对倒序时间抛错）。
"""

from __future__ import annotations

from .domain import Segment, fmt_timestamp

# SRT 单条字幕的字符上限：再长会被播放器截断或压成多行。
MAX_SRT_LINE_CHARS = 42
# 折行时在中点之后多远范围内找标点（`RULE-135`）。
_WRAP_PUNCT_WINDOW = 10
_WRAP_PUNCTUATION = "，,。；;、：:！？!?"


def _wrap(text: str, limit: int = MAX_SRT_LINE_CHARS) -> str:
    """按字符宽度折行，最多两行（`RULE-135`）。

    - `len(text) <= limit` 原样返回（42 字符以内不折）；
    - 否则从中点起在 10 个字符内找标点，**在该标点之后**断行（标点留在前一行）；
    - 10 个字符内没有标点则在中点硬切；
    - **只折一次** —— 折完仍然可能超过 `limit`，这是既有行为，不是缺陷。
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    mid = len(text) // 2
    for i in range(mid, min(len(text), mid + _WRAP_PUNCT_WINDOW)):
        if text[i] in _WRAP_PUNCTUATION:
            return text[: i + 1].strip() + "\n" + text[i + 1 :].strip()
    return text[:mid].strip() + "\n" + text[mid:].strip()


def to_srt(segments: list[Segment], *, comment_lines: list[str] | None = None) -> str:
    """段落 → SRT 正文（`RULE-062`、`RULE-135`、`RULE-132`）。

    - 空文本段落跳过（`strip()` 之后为空）；
    - 倒序（`end < start`）抛 `ValueError`，让任务失败而不是写出播放器会丢的坏字幕
      （`end == start` 是允许的）；
    - 编号在过滤**之后**从 1 连续分配，跳空段不留断档；
    - 有注释时以 `# ` 前缀的注释块开头，但没有存活段落时返回空串（注释一并丢弃）。
    """
    bodies: list[str] = []
    has_speaker = any(seg.speaker for seg in segments)
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if seg.end < seg.start:
            raise ValueError(f"时间倒序：{seg.start} → {seg.end}（{text[:20]}）")
        start, end = fmt_timestamp(seg.start), fmt_timestamp(seg.end)
        prefix = ""
        if seg.speaker:
            prefix = f"[{seg.speaker}] "
        elif has_speaker:
            # 与 `to_txt` 一致：同一份产物里不要一半有标签一半没有。
            prefix = "[?] "
        bodies.append(f"{start} --> {end}\n{wrap_srt_line(prefix + text)}")

    if not bodies:
        return ""

    blocks: list[str] = []
    if comment_lines:
        blocks.append("\n".join(f"# {line}" for line in comment_lines))
    blocks.extend(f"{idx}\n{body}" for idx, body in enumerate(bodies, start=1))
    return "\n\n".join(blocks) + "\n"


def to_txt(
    text: str, segments: list[Segment] | None = None, *, comment_lines: list[str] | None = None
) -> str:
    """纯文本稿（`RULE-136`、`RULE-132`）。

    - 有段落且**任一段带 speaker**：同一说话人的连续段落合并成一块，前缀 `[<speaker>] `，
      无 speaker 的段落用 `[?]`；
    - 有段落但都不带 speaker：一段一行（同一说话人的 `None` 不做 `[?]` 分块）；
    - 没有段落：按合并文本原样输出；
    - 注释行加 `# ` 前缀置于最前；正文为空则整体为空串。
    """
    parts: list[str] = []
    if comment_lines:
        parts.extend(f"# {line}" for line in comment_lines)
    if segments:
        has_speaker = any(s.speaker for s in segments)
        if has_speaker:
            lines: list[str] = []
            cur_spk: str | None = None
            cur_texts: list[str] = []
            for s in segments:
                t = s.text.strip()
                if not t:
                    continue  # 空白段跳过，且不断开说话人的连续块
                spk = s.speaker or "?"
                if spk != cur_spk:
                    if cur_texts:
                        lines.append(f"[{cur_spk}] {''.join(cur_texts)}")
                    cur_spk, cur_texts = spk, [t]
                else:
                    cur_texts.append(t)
            if cur_texts:
                lines.append(f"[{cur_spk}] {''.join(cur_texts)}")
            body = "\n".join(lines)
        else:
            body = "\n".join(s.text.strip() for s in segments if s.text.strip())
    else:
        body = text.strip()
    if body:
        parts.append(body)
        parts.append("")
    return "\n".join(parts) if parts else ""


# `_wrap` 是 legacy 的函数名（`render.py:15`），Phase 1 的等价性测试按名字引用它。
# 对外用 `wrap_srt_line`，这里保留一个同义词以免测试改成「新名字」而丢掉新旧对照。
wrap_srt_line = _wrap
