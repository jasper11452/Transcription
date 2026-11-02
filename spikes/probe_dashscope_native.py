"""Spike：qwen-audio-3.0-asr-flash 的正确调用形状（原生接口）。

背景（用户提供的可用参考 `/Users/jasper/Desktop/asr_test/ds_chunks.py`）：
    dashscope.MultiModalConversation.call(
        model="qwen-audio-3.0-asr-flash",
        messages=[{"role": "user", "content": [{"audio": "file://" + wav}]}],
        result_format="message", format="wav",
        asr_options={"language": "zh", "enable_itn": True})

关键点：`format` 是**顶层参数**（SDK 会塞进 `parameters.format`）；缺它恒报
`UNSUPPORTED_FORMAT: format is empty`（这正是之前兼容模式一直失败的原因）。

SDK 的 `file://` 其实是**先把本地文件上传到 DashScope OSS 再用 URL**
（dashscope/utils/oss_utils.py: check_and_upload_local）。所以本脚本要验证：
原生接口能否直接吃 base64 data URL —— 能吃就不必引入 SDK 依赖。

用法：uv run python spikes/probe_dashscope_native.py [音频路径]
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

NATIVE = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
COMPAT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen-audio-3.0-asr-flash"
DEFAULT_AUDIO = Path(__file__).resolve().parents[1] / "tests" / "data" / "smoke.wav"


def tail(secret: str | None) -> str:
    return f"…{secret[-4:]}" if secret else "<未设置>"


def call(client: httpx.Client, url: str, payload: dict, label: str) -> dict | None:
    t0 = time.time()
    resp = client.post(url, json=payload)
    elapsed = time.time() - t0
    print(f"\n[{label}] http={resp.status_code} {elapsed:.1f}s")
    try:
        body = resp.json()
    except json.JSONDecodeError:
        print("  body:", resp.text[:300])
        return None
    print("  body:", json.dumps(body, ensure_ascii=False)[:600])
    return body


def describe(body: dict | None) -> str | None:
    if not isinstance(body, dict):
        return None
    output = body.get("output") or {}
    for key in ("text", "choices"):
        if key in output:
            value = output[key]
            if key == "choices":
                try:
                    return value[0]["message"]["content"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    return json.dumps(value, ensure_ascii=False)[:300]
            return str(value)[:400]
    return None


def main() -> None:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AUDIO
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        print("DASHSCOPE_API_KEY 未设置")
        return
    print(f"音频：{audio}（{audio.stat().st_size / 1e6:.2f}MB）  key {tail(key)}")
    raw = audio.read_bytes()
    b64 = base64.b64encode(raw).decode()
    mime = "mpeg" if audio.suffix.lower() == ".mp3" else "wav"
    fmt = "mp3" if audio.suffix.lower() == ".mp3" else "wav"
    headers = {"Authorization": f"Bearer {key}"}

    with httpx.Client(timeout=600, headers=headers) as client:
        # 1. 原生 + base64 data URL（最想成立的形状：无 SDK、无 OSS）
        call(
            client,
            NATIVE,
            {
                "model": MODEL,
                "input": {
                    "messages": [
                        {"role": "user", "content": [{"audio": f"data:audio/{mime};base64,{b64}"}]}
                    ]
                },
                "parameters": {
                    "format": fmt,
                    "asr_options": {"language": "zh", "enable_itn": True},
                },
            },
            "native + base64 data URL",
        )

        # 2. 原生 + 裸 base64（不带 data: 前缀）
        call(
            client,
            NATIVE,
            {
                "model": MODEL,
                "input": {"messages": [{"role": "user", "content": [{"audio": b64}]}]},
                "parameters": {
                    "format": fmt,
                    "asr_options": {"language": "zh", "enable_itn": True},
                },
            },
            "native + 裸 base64",
        )

        # 3. 对照：兼容模式（已知恒报 format is empty）
        call(
            client,
            COMPAT,
            {
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": f"data:audio/{mime};base64,{b64}"},
                            }
                        ],
                    }
                ],
                "asr_options": {"language": "zh", "enable_itn": True},
            },
            "compat + base64（对照）",
        )

        # 4. 不带 format（复现 format is empty）
        call(
            client,
            NATIVE,
            {
                "model": MODEL,
                "input": {
                    "messages": [
                        {"role": "user", "content": [{"audio": f"data:audio/{mime};base64,{b64}"}]}
                    ]
                },
            },
            "native + base64，缺 format（对照）",
        )

    # 5. SDK 路径（若本机有 dashscope）
    try:
        import dashscope

        dashscope.api_key = key
        t0 = time.time()
        resp = dashscope.MultiModalConversation.call(
            model=MODEL,
            messages=[{"role": "user", "content": [{"audio": f"file://{audio}"}]}],
            result_format="message",
            format=fmt,
            asr_options={"language": "zh", "enable_itn": True},
        )
        print(f"\n[SDK file://] status={resp.status_code} {time.time() - t0:.1f}s")
        print("  ", json.dumps(getattr(resp, "output", None), ensure_ascii=False)[:400])
    except ImportError:
        print("\n[SDK file://] 未安装 dashscope，跳过")


if __name__ == "__main__":
    main()
