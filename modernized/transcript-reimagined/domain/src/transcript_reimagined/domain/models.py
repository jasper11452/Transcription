"""领域模型：分片、段落、词、结果。所有引擎的公共语言。

零 I/O、零第三方依赖 —— 只允许 stdlib（`math` / `dataclasses` / `pathlib`）。
这条边界由 `tests/test_zero_dependency_contract.py` 用 AST 扫描守住。

重建自 `legacy/transcript/src/transcript/models.py`（Phase 1 要求逐字节等价），
承载 `RULE-025`（SRT 时间戳格式与取整）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Word:
    """词级时间戳。中文按字给出，英文按词。"""

    text: str
    start: float
    end: float
    probability: float | None = None


@dataclass
class Segment:
    """带时间轴的文本段，SRT 的最小单位。"""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None  # e.g. "speaker_1"；None = 未做说话人分离

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def shifted(self, offset: float) -> Segment:
        """把分片内的相对时间轴平移成整段音频的绝对时间轴。

        ⚠️ 已知行为（不是笔误）：`speaker` **不在**平移结果里 —— legacy 的
        `shifted()` 就没带它（`models.py:34-43`）。Phase 1 要求逐字节等价，故照旧保留，
        并由 `tests/test_rule_136_speaker_output.py` 断言钉住。是否该修属于 Phase 3
        （`diar` 连通）的决策点，修它是一次需要署名的行为变更。
        """
        return Segment(
            start=self.start + offset,
            end=self.end + offset,
            text=self.text,
            words=[
                Word(w.text, w.start + offset, w.end + offset, w.probability) for w in self.words
            ],
        )


@dataclass
class Chunk:
    """切片计划里的一片。切片是重试与落盘的唯一单位。"""

    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TranscriptResult:
    """一个引擎对一段音频的转写结果。"""

    text: str
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    audio_seconds: float | None = None
    cost_usd: float | None = None
    engine: str = ""
    has_timestamps: bool = False

    def shifted(self, offset: float) -> TranscriptResult:
        return TranscriptResult(
            text=self.text,
            segments=[s.shifted(offset) for s in self.segments],
            language=self.language,
            audio_seconds=self.audio_seconds,
            cost_usd=self.cost_usd,
            engine=self.engine,
            has_timestamps=self.has_timestamps,
        )


@dataclass
class AudioInfo:
    """ffprobe 看到的事实。"""

    path: Path
    duration: float
    size_bytes: int
    codec: str | None
    sample_rate: int | None
    channels: int | None
    has_audio: bool

    @property
    def megabytes(self) -> float:
        return self.size_bytes / 1_000_000


@dataclass(frozen=True)
class Rule:
    """词表里的一条 `错词 -> 正确词` 映射。

    裸热词**不是**规则 —— 它没有错词侧，由 `parse_hot_words` 单独给出。

    住在 `domain` 而不是 `post`：它是「语音转写」这件事的公共词汇，与
    `Segment` 同级。`CHUNK_PLAN` 是唯一真正专属某一层的实体，住在 `ingest`。
    """

    wrong: str
    right: str


@dataclass(frozen=True)
class Change:
    """一次实际发生的替换：`count` 只统计真正匹配到的处数。

    住 `domain` 的理由同 `Rule` —— `post` 产出它、`orchestrate` 把它写进
    `.raw.json`、`web` 把它展示给用户，三处都需要同一个类型对象。
    """

    wrong: str
    right: str
    count: int

    def describe(self) -> str:
        return f"{self.wrong}→{self.right} ×{self.count}"


@dataclass(frozen=True)
class Issue:
    """一条会被忽略的词表问题，带行号。

    住 `domain` 的理由同 `Rule` / `Change`：`post` 产出它（`parse_glossary_report`）、
    `web` 把它连同行号展示给用户、`runner` 的端到端测试断言它 —— 三处都要同一个
    类型对象。裸热词**不是**问题，是合法写法，所以它没有出现在这里。
    """

    line: int
    message: str

    def describe(self) -> str:
        return f"第 {self.line} 行：{self.message}"


def fmt_timestamp(seconds: float, *, sep: str = ",") -> str:
    """秒 → SRT 时间戳（HH:MM:SS,mmm）。

    取整语义（`RULE-025`，人裁定「改注释，代码不变」）：
    毫秒由 Python 内建 `round()` 得出，即 **round-half-to-even（半值取偶）**，
    **不是**四舍五入（half-up）。恰好落在半毫秒的值会取到偶数一侧：
    0.0005s → `000`（而非 001）、0.0015s → `002`。这是**刻意保留**的现行为，
    不是缺陷修复项（见 `AI_NATIVE_SPEC.md` §6b）。

    负秒先夹到 0：`-1.0` → `00:00:00,000`。
    取整后毫秒数恰为 1000 时进位一秒，因此 59.9996s → `00:01:00,000`，
    绝不产出 `00:00:59,1000`。
    """
    seconds = max(0.0, float(seconds))
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = math.floor(seconds)
    if ms == 1000:  # 进位：毫秒位满 1000 时归零并给秒 +1
        total += 1
        ms = 0
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"
