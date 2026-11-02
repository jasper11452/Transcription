"""产物渲染：txt / srt。

SRT 的两个硬要求：时间格式合法（HH:MM:SS,mmm）、时间单调不减。
外加一条本工具的要求：**错误文本绝不混进产物**——宁可任务失败。
"""

from __future__ import annotations

import re

from .models import Segment, fmt_timestamp

# SRT 单条字幕的字符上限：再长会被播放器截断或压成多行
MAX_SRT_LINE_CHARS = 42


def _wrap(text: str, limit: int = MAX_SRT_LINE_CHARS) -> str:
    """按字符宽度折行，最多两行。中文没有空格，只能按字数折。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    mid = len(text) // 2
    # 优先在标点处断开，否则按中点硬切
    for i in range(mid, min(len(text), mid + 10)):
        if text[i] in "，,。；;、：:！？!?":
            return text[: i + 1].strip() + "\n" + text[i + 1 :].strip()
    return text[:mid].strip() + "\n" + text[mid:].strip()


def to_srt(segments: list[Segment], *, comment_lines: list[str] | None = None) -> str:
    """段落 → SRT。空段落被跳过，时间不合法时抛错而不是写出坏字幕。"""
    bodies: list[str] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if seg.end < seg.start:
            raise ValueError(f"时间倒序：{seg.start} → {seg.end}（{text[:20]}）")
        start, end = fmt_timestamp(seg.start), fmt_timestamp(seg.end)
        bodies.append(f"{start} --> {end}\n{_wrap(text)}")

    # 编号必须在**输出之后**连续分配：跳过空段后 enumerate 下标会出现断档
    blocks: list[str] = []
    if comment_lines:
        blocks.append("\n".join(f"# {line}" for line in comment_lines))
    blocks.extend(f"{idx}\n{body}" for idx, body in enumerate(bodies, start=1))

    if not bodies:
        return ""
    return "\n\n".join(blocks) + "\n"


def to_txt(
    text: str, segments: list[Segment] | None = None, *, comment_lines: list[str] | None = None
) -> str:
    """纯文本稿。有段落就按段落换行（便于对照），否则原样输出。

    当段落带 speaker 标签时，同一说话人的连续段落合并成一块，前缀 [speaker_N]。
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
                    continue
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


_SRT_TIME = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def parse_srt(text: str) -> list[Segment]:
    """把 SRT 读回段落：在线校对后用它重写产物。

    - 折行按“无空格拼接”还原，与 _wrap 对称（_wrap 只插换行、不插空格）；
    - 注释行与序号丢弃；时间轴不合法或正文为空的块直接跳过，不写坏产物。
    """
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        # 注释块没有时间行，会在下面被 time_at 跳过；不能按 "#" 过滤正文，
        # 否则一句以 "#" 开头的字幕会被当成注释丢掉。
        time_at = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if time_at is None:
            continue
        match = _SRT_TIME.search(lines[time_at])
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
        start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1.ljust(3, "0")) / 1000
        end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2.ljust(3, "0")) / 1000
        body = "".join(line.strip() for line in lines[time_at + 1:])
        if not body or end < start:
            continue
        segments.append(Segment(start=start, end=end, text=body))
    return segments
