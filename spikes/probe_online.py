"""Spike：核实两个在线引擎的精确 id、端点形态与能力（spec Open Questions #1/#2）。

用法：
    uv run python spikes/probe_online.py

凭据：从 shell 环境读取（仅用于验证，产品代码只读 ~/.config/transcript/config.env）。
只打印 key 尾号与错误码，不打印任何明文密钥。
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import httpx

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "data" / "smoke.mp3"
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def tail(secret: str | None) -> str:
    if not secret:
        return "<未设置>"
    return f"…{secret[-4:]} (len={len(secret)})"


def show(label: str, resp: httpx.Response) -> object | None:
    print(f"  http={resp.status_code}")
    body: object | None = None
    try:
        body = resp.json()
    except Exception:
        print("  body:", resp.text[:400])
        return None
    text = json.dumps(body, ensure_ascii=False)
    print("  body:", text[:700])
    return body


def probe_dashscope_models(key: str, label: str) -> list[str]:
    print(f"\n-- DashScope 模型清单 [{label} {tail(key)}]")
    with httpx.Client(timeout=30) as c:
        r = c.get(
            f"{DASHSCOPE_BASE}/compatible-mode/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
    body = show("models", r)
    ids: list[str] = []
    if isinstance(body, dict):
        ids = [m.get("id", "") for m in body.get("data", [])]
    asr = [i for i in ids if "asr" in i.lower() or "audio" in i.lower()]
    print(f"  asr/audio 相关 id: {asr}")
    return asr


def probe_dashscope_asr(key: str, model: str) -> None:
    print(f"\n-- DashScope ASR 调用 model={model} (key {tail(key)})")

    # 形态 A：OpenAI 兼容 /audio/transcriptions（multipart）
    print("  [形态A] compatible-mode /audio/transcriptions")
    with httpx.Client(timeout=180) as c:
        files = {"file": ("smoke.mp3", SAMPLE.read_bytes(), "audio/mpeg")}
        data = {"model": model, "response_format": "json"}
        try:
            r = c.post(
                f"{DASHSCOPE_BASE}/compatible-mode/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=data,
            )
            show("A", r)
        except Exception as e:  # noqa: BLE001
            print("  异常:", e)

    # 形态 B：DashScope 原生 multimodal-generation + file://
    print("  [形态B] 原生 multimodal-generation + file://")
    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [{"audio": f"file://{SAMPLE}"}]}]},
        "parameters": {},
    }
    with httpx.Client(timeout=180) as c:
        try:
            r = c.post(
                f"{DASHSCOPE_BASE}/api/v1/services/aigc/multimodal-generation/generation",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            show("B", r)
        except Exception as e:  # noqa: BLE001
            print("  异常:", e)

    # 形态 C：base64 data URL（compatible-mode）
    print("  [形态C] compatible-mode + base64 data URL")
    b64 = base64.b64encode(SAMPLE.read_bytes()).decode()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": f"data:audio/mpeg;base64,{b64}", "format": "mp3"},
                    }
                ],
            }
        ],
    }
    with httpx.Client(timeout=180) as c:
        try:
            r = c.post(
                f"{DASHSCOPE_BASE}/compatible-mode/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            show("C", r)
        except Exception as e:  # noqa: BLE001
            print("  异常:", e)


def probe_openrouter(key: str) -> None:
    print(f"\n-- OpenRouter mai-transcribe-2 (key {tail(key)})")
    print("  音频体积:", round(SAMPLE.stat().st_size / 1e6, 2), "MB")

    def call(extra: dict, label: str) -> None:
        with httpx.Client(timeout=300) as c:
            files = {"file": ("smoke.mp3", SAMPLE.read_bytes(), "audio/mpeg")}
            data = {
                "model": "microsoft/mai-transcribe-2",
                "response_format": "verbose_json",
                **extra,
            }
            try:
                r = c.post(
                    f"{OPENROUTER_BASE}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files=files,
                    data=data,
                )
                body = show(label, r)
                if isinstance(body, dict):
                    print("    keys:", list(body.keys()))
                    segs = body.get("segments") or []
                    print("    segments:", len(segs), segs[:2] if segs else None)
                    usage = body.get("usage") or {}
                    print(
                        "    usage/cost:",
                        {k: v for k, v in usage.items() if "cost" in k or "duration" in k},
                    )
            except Exception as e:  # noqa: BLE001
                print("  异常:", e)

    print("  [无热词]")
    call({}, "plain")
    print("  [prompt 热词尝试]")
    call({"prompt": "转录工具，离线转写，在线字幕，专有名词，校对"}, "prompt")
    print("  [diarization 尝试]")
    call(
        {"provider": json.dumps({"options": {"azure": {"diarization": {"enabled": True}}}})}, "diar"
    )


if __name__ == "__main__":
    if not SAMPLE.exists():
        print("样例缺失:", SAMPLE)
        sys.exit(1)

    ds = os.environ.get("DASHSCOPE_API_KEY")
    yp = os.environ.get("YP_DASHSCOPE_API_KEY")
    ork = os.environ.get("OPENROUTER_API_KEY")

    if ds:
        ids = probe_dashscope_models(ds, "DASHSCOPE_API_KEY")
        target = next((i for i in ids if "3.0-asr" in i or "3-asr" in i), None)
        for cand in filter(None, [target, "qwen-audio-3.0-asr-flash", "qwen3-asr-flash"]):
            probe_dashscope_asr(ds, cand)
    else:
        print("DASHSCOPE_API_KEY 未设置，跳过")

    if yp and yp != ds:
        print(f"\n== 第二把 key 对照 ({tail(yp)})")
        probe_dashscope_models(yp, "YP_DASHSCOPE_API_KEY")

    if ork:
        probe_openrouter(ork)
    else:
        print("OPENROUTER_API_KEY 未设置，跳过")
