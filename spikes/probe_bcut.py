"""Spike：必剪（bcut）ASR 流程验证。

参考实现：`/Users/jasper/Desktop/online_bcut_srt.py`（独立脚本，无鉴权、返回 utterances 时间轴）。
本脚本把它拆成最小可验证步骤，确认在"64k mp3 工作副本"上也能跑通。

用法：uv run python spikes/probe_bcut.py [音频路径]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
HEADERS = {
    "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
    "Content-Type": "application/json",
}
DEFAULT_AUDIO = Path(__file__).resolve().parents[1] / "tests" / "data" / "smoke.mp3"


def main() -> None:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AUDIO
    payload = audio.read_bytes()
    print(f"音频：{audio}（{len(payload) / 1e3:.0f}KB）")

    with httpx.Client(timeout=120, headers=HEADERS) as client:
        t0 = time.time()
        created = client.post(
            f"{BASE}/resource/create",
            content=json.dumps(
                {
                    "type": 2,
                    "name": "audio.mp3",
                    "size": len(payload),
                    "ResourceFileType": "mp3",
                    "model_id": "8",
                }
            ),
        )
        print(f"[1] resource/create http={created.status_code} {time.time() - t0:.1f}s")
        data = created.json().get("data") or {}
        if not data:
            print("  失败：", created.text[:300])
            return
        urls = data["upload_urls"]
        per_size = data["per_size"]
        print(
            f"    resource_id={data['resource_id']} 分片数={len(urls)} 单片={per_size / 1e6:.1f}MB"
        )

        etags: list[str] = []
        for i, url in enumerate(urls):
            chunk = payload[i * per_size : (i + 1) * per_size]
            put = client.put(url, content=chunk, headers=HEADERS)
            etags.append(put.headers.get("Etag", ""))
            print(f"[2] PUT 分片 {i + 1}/{len(urls)} http={put.status_code} etag={etags[-1][:16]}…")

        done = client.post(
            f"{BASE}/resource/create/complete",
            content=json.dumps(
                {
                    "InBossKey": data["in_boss_key"],
                    "ResourceId": data["resource_id"],
                    "Etags": ",".join(etags),
                    "UploadId": data["upload_id"],
                    "model_id": "8",
                }
            ),
        )
        download_url = (done.json().get("data") or {}).get("download_url")
        print(f"[3] create/complete http={done.status_code} url={str(download_url)[:80]}…")

        task = client.post(f"{BASE}/task", json={"resource": download_url, "model_id": "8"})
        task_id = (task.json().get("data") or {}).get("task_id")
        print(f"[4] task http={task.status_code} task_id={task_id}")

        result = None
        for second in range(120):
            q = client.get(f"{BASE}/task/result", params={"model_id": 7, "task_id": task_id})
            body = q.json().get("data") or {}
            state = body.get("state")
            if state == 4:
                result = json.loads(body.get("result") or "{}")
                print(f"[5] 完成，用时 {second}s，http={q.status_code}")
                break
            if second % 5 == 0:
                print(f"[5] 等待中 {second}s state={state}")
            time.sleep(1)

    if not result:
        print("未拿到结果")
        return
    utterances = result.get("utterances") or []
    print(f"\nutterances: {len(utterances)} 条")
    for u in utterances[:5]:
        print(
            f"  {u['start_time'] / 1000:7.2f}s - {u['end_time'] / 1000:7.2f}s  {u['transcript'][:60]}"
        )
    keys = sorted(result.keys())
    print("\nresult 顶层字段：", keys)


if __name__ == "__main__":
    main()
