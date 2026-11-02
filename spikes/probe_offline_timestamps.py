"""Spike：离线引擎是否具备时间戳能力（spec Open Questions #3）。

用法：uv run python spikes/probe_offline_timestamps.py
产出：结论打印到 stdout；不改动任何产品代码。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "data" / "smoke.wav"
QWEN_DIR = (
    Path.home() / ".cache/huggingface/hub/models--mlx-community--Qwen3-ASR-0.6B-8bit/snapshots"
)
WHISPER = "mlx-community/whisper-large-v3-turbo"


def dump(label: str, obj: object) -> None:
    print(f"\n=== {label} ===")
    print("type:", type(obj).__name__)
    if hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            preview = repr(v)
            print(f"  {k}: {preview[:300]}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            print(f"  {k}: {repr(v)[:300]}")


def probe_qwen() -> None:
    from mlx_audio.stt.utils import load_model

    snapshots = sorted(QWEN_DIR.glob("*")) if QWEN_DIR.exists() else []
    if not snapshots:
        print("Qwen3-ASR 权重未缓存，跳过")
        return
    model = load_model(str(snapshots[-1]), lazy=False)
    out = model.generate(str(SAMPLE))
    dump("Qwen3-ASR generate() 返回对象", out)
    print("\n-- 是否有时间戳字段 --")
    for name in ("segments", "words", "timestamps", "chunks"):
        v = getattr(out, name, None)
        print(f"  {name}: {'缺失' if v is None else repr(v)[:200]}")


def probe_whisper() -> None:
    import mlx_whisper

    out = mlx_whisper.transcribe(
        str(SAMPLE),
        path_or_hf_repo=WHISPER,
        word_timestamps=True,
        language="zh",
        verbose=False,
    )
    dump("mlx-whisper transcribe() 顶层", {k: v for k, v in out.items() if k != "segments"})
    segs = out.get("segments") or []
    print(f"\n段落数: {len(segs)}")
    if segs:
        dump("第一段", segs[0])
        words = segs[0].get("words") or []
        print(f"\n第一段词数: {len(words)}")
        for w in words[:5]:
            print("  ", w)


if __name__ == "__main__":
    only = os.environ.get("ONLY", "")
    if not only or only == "qwen":
        probe_qwen()
    if not only or only == "whisper":
        probe_whisper()
    print(
        "\n采样:", json.dumps({"file": str(SAMPLE), "exists": SAMPLE.exists()}, ensure_ascii=False)
    )
