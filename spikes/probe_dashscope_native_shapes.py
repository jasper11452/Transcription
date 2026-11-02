"""Spike：qwen-audio-3.0-asr-flash 的响应结构 × result_format × 时长上限。

要回答三个问题（都直接决定解析器怎么写）：
1. 不加 `result_format` 时返回 `output.output.sentence`（含 words）；
   加了 `result_format="message"` 是不是另一个形状？
2. 长音频（>1 句）时 `sentence` 是单个对象还是列表？字级时间戳还在不在？
3. 用户说的"≤5 分钟分片"边界在哪：300s 能过、330s 会怎样？

用法：uv run python spikes/probe_dashscope_native_shapes.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

NATIVE = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
MODEL = "qwen-audio-3.0-asr-flash"
ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "data" / "smoke.wav"


def make_clip(seconds: int, out: Path) -> Path:
    """用样例音频循环拼出一个指定时长的 16k 单声道 wav。"""
    if out.exists() and out.stat().st_size > 0:
        return out
    loops = max(1, seconds // 12 + 1)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for _ in range(loops):
        cmd += ["-i", str(SAMPLE)]
    cmd += [
        "-filter_complex",
        f"concat=n={loops}:v=0:a=1",
        "-t",
        str(seconds),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def summarize(label: str, resp: httpx.Response, elapsed: float) -> dict:
    print(f"\n=== {label}  http={resp.status_code}  {elapsed:.1f}s")
    try:
        body = resp.json()
    except json.JSONDecodeError:
        print("  非 JSON:", resp.text[:300])
        return {}
    if resp.status_code != 200:
        print("  ", json.dumps(body, ensure_ascii=False)[:400])
        return {"status": resp.status_code}

    usage = body.get("usage")
    print("  usage:", json.dumps(usage, ensure_ascii=False) if usage else None)
    out = body.get("output")
    print("  output keys:", list(out.keys()) if isinstance(out, dict) else type(out).__name__)

    # 结构探测：sentence / text / choices 三种都找一遍
    sentences = []
    text = None
    if isinstance(out, dict):
        inner = out.get("output")
        if isinstance(inner, dict):
            print("  output.output keys:", list(inner.keys()))
            if "sentence" in inner:
                sentence = inner["sentence"]
                sentences = sentence if isinstance(sentence, list) else [sentence]
            text = inner.get("text")
        if isinstance(out.get("sentence"), (dict, list)):
            sentence = out["sentence"]
            sentences = sentence if isinstance(sentence, list) else [sentence]
        text = text or out.get("text")

    if sentences:
        print(f"  sentence 条数: {len(sentences)}")
        for i, s in enumerate(sentences[:3]):
            words = s.get("words") or []
            print(
                f"    [{i}] {s.get('begin_time')}–{s.get('end_time')}ms words={len(words)} "
                f"text={str(s.get('text'))[:60]}"
            )
            if words:
                print(f"        首词 {words[0]} … 末词 {words[-1]}")
    if text:
        print("  text:", str(text)[:120])

    # 抽一条完整句子结构，便于写测试夹具
    if sentences:
        first = sentences[0]
        print("  首个 sentence 全字段:", list(first.keys()))
    return body


def main() -> None:
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        print("DASHSCOPE_API_KEY 未设置")
        sys.exit(1)
    headers = {"Authorization": f"Bearer {key}"}
    tmp = ROOT / ".e2e"
    tmp.mkdir(exist_ok=True)

    def payload(path: Path, *, result_format: str | None = None) -> dict:
        b64 = base64.b64encode(path.read_bytes()).decode()
        body = {
            "model": MODEL,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"audio": f"data:audio/wav;base64,{b64}"}]}
                ]
            },
            "parameters": {"format": "wav", "asr_options": {"language": "zh", "enable_itn": True}},
        }
        if result_format:
            body["result_format"] = result_format
        return body

    with httpx.Client(timeout=900, headers=headers) as client:
        # 1. 默认形状（12s）
        t0 = time.time()
        r = client.post(NATIVE, json=payload(SAMPLE))
        first = summarize("12s · 默认形状", r, time.time() - t0)

        # 2. result_format=message（ds_chunks.py 用的形状）
        t0 = time.time()
        r = client.post(NATIVE, json=payload(SAMPLE, result_format="message"))
        summarize("12s · result_format=message", r, time.time() - t0)

        # 3. 长音频（300s，正好是用户说的 5 分钟上限）
        clip300 = make_clip(300, tmp / "clip300.wav")
        t0 = time.time()
        r = client.post(NATIVE, json=payload(clip300))
        summarize("300s · 默认形状", r, time.time() - t0)

        # 4. 超限（330s）
        clip330 = make_clip(330, tmp / "clip330.wav")
        t0 = time.time()
        r = client.post(NATIVE, json=payload(clip330))
        summarize("330s · 超限探测", r, time.time() - t0)

    if first:
        (ROOT / ".e2e" / "ds_native_12s.json").write_text(
            json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n写出 .e2e/ds_native_12s.json（供测试夹具参考）")


if __name__ == "__main__":
    main()
