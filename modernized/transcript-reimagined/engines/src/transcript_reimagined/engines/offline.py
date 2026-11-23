"""离线引擎：Qwen3-ASR 出文本 + mlx-whisper 出词级时间戳。

为什么是两个模型（实测结论，见 spikes/probe_offline_timestamps.py）：
- Qwen3-ASR-1.7B-8bit 文本质量高、**自带标点**，但 `segments` 只有一条覆盖整片，
  没有可用的细粒度时间戳；
- mlx-whisper（large-v3-turbo）词级时间戳精确（中文按字给 start/end），但会丢标点。

所以：文本取 Qwen，时间轴取 whisper，再由 ``orchestrate`` 调 ``post.align`` 把两者
按字符相似度对齐（架构 v2：引擎不 import post）。两个模型都懒加载并常驻
（合计约 4GB，M4 Max 48GB 可接受），避免每次分片重载。

**Q3 修复（已署名）**：删掉遗留的「时间轴兜底死分支」。遗留代码在
``build_segments`` 拿不到段落时，用同样的参数再调一次 ``_whisper_words`` ——
结果完全相同，只会把成本翻倍。重建版只取一次词级时间轴；退化时由
``align.build_segments`` 的等比兜底报告。
"""

from __future__ import annotations

from pathlib import Path

from transcript_reimagined.config import Config
from transcript_reimagined.domain import FatalError, TranscriptResult, Word

_qwen_model = None
_qwen_id: str | None = None


def _load_qwen(model_id: str):
    global _qwen_model, _qwen_id
    if _qwen_model is not None and _qwen_id == model_id:
        return _qwen_model
    try:
        from mlx_audio.stt.utils import load_model
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise FatalError("未安装 mlx-audio，离线引擎不可用（uv sync 后重试）") from exc
    _qwen_model = load_model(model_id, lazy=False)
    _qwen_id = model_id
    return _qwen_model


def _whisper_words(audio_path: Path, *, repo: str, language: str | None) -> list[Word]:
    try:
        import mlx_whisper
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise FatalError("未安装 mlx-whisper，无法产出时间轴（uv sync 后重试）") from exc
    out = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=repo,
        word_timestamps=True,
        language=language,
        verbose=False,
    )
    words: list[Word] = []
    for seg in out.get("segments") or []:
        for word in seg.get("words") or []:
            text = (word.get("word") or "").strip()
            if not text:
                continue
            words.append(
                Word(
                    text,
                    float(word["start"]),
                    float(word["end"]),
                    float(word.get("probability") or 0.0),
                )
            )
    return words


class OfflineEngine:
    """离线双模型引擎。文本与时间轴分开取，各自用最擅长的那个。"""

    def __init__(self, config: Config):
        self.config = config
        self.name = "offline:qwen3-asr+whisper"
        self.has_timestamps = True
        # 本地模型没有服务端单次上限，切片长度完全由配置决定
        self.max_chunk_s = None

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        hotwords: list[str] | None = None,
        want_timestamps: bool = False,
        duration_s: float | None = None,  # noqa: ARG002 - 离线没有单次上限
    ) -> TranscriptResult:
        path = Path(audio_path)
        qwen = _load_qwen(self.config.offline_model)
        out = qwen.generate(
            str(path),
            hotwords=list(hotwords) if hotwords else None,
            language=language,
        )
        text = (getattr(out, "text", "") or "").strip()
        lang = None
        languages = getattr(out, "language", None)
        if isinstance(languages, list) and languages:
            lang = languages[0]
        elif isinstance(languages, str):
            lang = languages

        words: list[Word] = []
        if want_timestamps and text:
            # 只算一次。遗留实现失败后会再调一次同样的函数（死分支）。
            words = _whisper_words(path, repo=self.config.timing_model, language=language)

        return TranscriptResult(
            text=text,
            segments=[],
            language=lang,
            audio_seconds=None,
            cost_usd=0.0,
            engine=self.name,
            # 能力标记：离线引擎始终能提供时间轴；本片没取到词时由 align 等比兜底。
            has_timestamps=True,
            words=words,
        )
