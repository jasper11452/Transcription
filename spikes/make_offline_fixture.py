"""把真实模型的输出录成测试夹具。

单元测试不该依赖模型推理（慢、吃内存、结果会随版本漂移），
但也不该用编造的数据验证对齐算法。所以：模型跑一次，存成 JSON，测试读夹具。

用法：uv run python spikes/make_offline_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "data" / "smoke.wav"
OUT = ROOT / "tests" / "data" / "offline_fixture.json"

QWEN_REPO = "mlx-community/Qwen3-ASR-1.7B-8bit"
WHISPER_REPO = "mlx-community/whisper-large-v3-turbo"


def main() -> None:
    import mlx_whisper
    from mlx_audio.stt.utils import load_model

    print("whisper ...")
    w = mlx_whisper.transcribe(
        str(SAMPLE),
        path_or_hf_repo=WHISPER_REPO,
        word_timestamps=True,
        language="zh",
        verbose=False,
    )
    words = [
        {
            "text": word["word"],
            "start": float(word["start"]),
            "end": float(word["end"]),
            "probability": float(word.get("probability") or 0.0),
        }
        for seg in w["segments"]
        for word in (seg.get("words") or [])
    ]

    print("qwen3-asr ...")
    model = load_model(QWEN_REPO, lazy=False)
    q = model.generate(str(SAMPLE))

    payload = {
        "source": str(SAMPLE.name),
        "qwen": {"text": q.text, "segments": list(q.segments or [])},
        "whisper": {"text": w["text"], "words": words},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT}（{len(words)} 个词）")


if __name__ == "__main__":
    main()
