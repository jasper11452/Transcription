"""必剪（bcut）适配器——免费的在线选择。

流程是四步：

1. `POST /resource/create`      申请上传，拿到 in_boss_key / upload_id / upload_urls / per_size
2. `PUT  <upload_urls[i]>`      逐片上传（用 Etag 串起来）
3. `POST /resource/create/complete` 提交合并，拿到 download_url
4. `POST /task` + `GET /task/result` 轮询到 `state == 4`

特点与代价（写进 spec，用户需要知情）：
- **不需要密钥**、免费、返回**句级**时间戳（`utterances[].start_time/end_time`，毫秒）；
- 音频会上传到 B 站的存储，且它是**匿名**接口——可用性不由我们掌控；
- 质量上偶有音近错字，所以默认仍不是首选引擎。

**D6（已署名）**：90s 风控冷却从实例级提到**进程级**。遗留每个任务新建引擎实例，
`_banned_until` 随实例消失 —— 两个 bcut 任务能各自去撞正在风控的上游。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from transcript_reimagined.config import Config
from transcript_reimagined.domain import (
    FatalError,
    RecoverableError,
    Segment,
    TranscriptResult,
    classify_http,
)

HEADERS = {
    "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
    "Content-Type": "application/json",
}
# 被风控挡下后的冷却期。**进程级**（D6）：同一进程里所有 BcutEngine 实例共享。
BAN_COOLDOWN_S = 90.0
_banned_until: float = 0.0


def cooldown_remaining_s(now: float | None = None) -> float:
    """距离冷却结束还有多少秒（给状态接口与测试用）。"""
    return max(0.0, _banned_until - (now if now is not None else time.monotonic()))


UPLOAD_MODEL_ID = "8"
QUERY_MODEL_ID = 7
TASK_DONE_STATE = 4
# 轮询节奏：分片都 ≤ 120s，实测 12s 音频 1s 出结果；给足余量但不无限等
POLL_INTERVAL_S = 1.5
POLL_TIMEOUT_S = 300.0


class BcutEngine:
    """必剪 ASR。句级时间戳，无密钥，因此也只把 mp3 工作副本送出去。"""

    has_timestamps = True
    max_chunk_s = None  # 服务端自己做整段识别，未发现单次时长上限

    def __init__(
        self,
        config: Config,
        model_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_timeout_s: float = POLL_TIMEOUT_S,
    ):
        self.config = config
        self.base = config.bcut_base
        self.model_id = model_id or UPLOAD_MODEL_ID
        self.name = f"bcut:{self.model_id}"
        self.max_chunk_s = None
        self._transport = transport
        self._sleep = sleep
        self._poll_timeout_s = poll_timeout_s

    def _raise_for_status(self, status: int, body: str) -> None:
        """必剪的 HTTP 状态 → 错误。412 单独处理：那是 B 站风控，不是参数错误。

        实测（2026-09-19）：`POST /task` 返回 412，JSON 体为
        `{"code":-412,"message":"request was banned"}`；同一时刻 `/resource/create`、
        分片上传、`/complete` 三步仍是 200——风控挡的是"建任务/取结果"这一步。
        换 UA / Referer / Origin 均无效；这次封禁约 40 分钟后自行解除。
        """
        global _banned_until
        if status == 412 or "request was banned" in body:
            _banned_until = time.monotonic() + BAN_COOLDOWN_S
            raise FatalError(
                "必剪接口返回 412（request was banned）：匿名接口的临时风控/限流"
                f"（实测约 40 分钟自行解除；{BAN_COOLDOWN_S:.0f}s 内不再请求）。"
                "已完成的片会保留，稍后可以续跑，或改用百炼/OpenRouter。"
            )
        raise classify_http(status, body)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        hotwords: list[str] | None = None,
        want_timestamps: bool = True,  # noqa: ARG002 - 该引擎总是返回句级时间戳
        duration_s: float | None = None,  # noqa: ARG002 - 服务端未发现单次时长上限
    ) -> TranscriptResult:
        global _banned_until
        path = Path(audio_path)
        if path.suffix.lower() != ".mp3":
            # 接口把上传物声明成 mp3，声明与实际不符时对端行为不可预期
            raise FatalError(
                f"必剪接口按 mp3 声明上传物，收到 {path.suffix or '(无后缀)'}；"
                "在线路径应使用 mp3 工作副本"
            )
        payload = path.read_bytes()
        if not payload:
            raise FatalError(f"待上传音频为空：{path.name}")
        if time.monotonic() < _banned_until:
            # 冷却期内不发请求：对着正在风控的上游继续打只会延长封禁
            _banned_until = time.monotonic() + BAN_COOLDOWN_S
            raise FatalError(
                "必剪接口仍在风控冷却期内（上一次返回 412 request was banned）。"
                "已完成的片会保留，稍后可以续跑，或改用百炼/OpenRouter。"
            )

        # 只用一个客户端：之前内层 with 遮蔽了外层参数，块结束后又拿它发请求 →
        # "Cannot send a request, as the client has been closed"（被测试抳到）
        with httpx.Client(timeout=300, transport=self._transport) as client:
            uploaded = self._upload(client, payload)
            task_id = self._create_task(client, uploaded)
            result = self._poll(client, task_id)

        segments = _parse_utterances(result)
        if not segments:
            raise FatalError("必剪返回了空结果（未解析到 utterances）")
        return TranscriptResult(
            text="".join(s.text for s in segments),
            segments=segments,
            language=language or "zh",
            audio_seconds=(segments[-1].end if segments else None),
            cost_usd=0.0,  # 免费接口
            engine=self.name,
            has_timestamps=True,
        )

    # ---------- 四步流程 ----------

    def _upload(self, client: httpx.Client, payload: bytes) -> str:
        created = self._post(
            client,
            "/resource/create",
            {
                "type": 2,
                "name": "audio.mp3",
                "size": len(payload),
                "ResourceFileType": "mp3",
                "model_id": self.model_id,
            },
        )
        data = created.get("data") or {}
        urls, per_size = data.get("upload_urls") or [], data.get("per_size")
        if not urls or not per_size:
            raise FatalError(
                f"必剪申请上传返回异常：{json.dumps(created, ensure_ascii=False)[:200]}"
            )

        etags: list[str] = []
        for index, url in enumerate(urls):
            piece = payload[index * per_size : (index + 1) * per_size]
            try:
                put = client.put(url, content=piece, headers=HEADERS)
            except httpx.HTTPError as exc:
                raise RecoverableError(f"必剪分片上传失败（网络）：{type(exc).__name__}") from exc
            if put.status_code >= 400:
                self._raise_for_status(put.status_code, put.text[:300])
            etags.append(put.headers.get("Etag", ""))

        done = self._post(
            client,
            "/resource/create/complete",
            {
                "InBossKey": data.get("in_boss_key"),
                "ResourceId": data.get("resource_id"),
                "Etags": ",".join(etags),
                "UploadId": data.get("upload_id"),
                "model_id": self.model_id,
            },
        )
        download_url = (done.get("data") or {}).get("download_url")
        if not download_url:
            raise FatalError(
                f"必剪提交上传未返回 download_url：{json.dumps(done, ensure_ascii=False)[:200]}"
            )
        return download_url

    def _create_task(self, client: httpx.Client, download_url: str) -> str:
        created = self._post(client, "/task", {"resource": download_url, "model_id": self.model_id})
        task_id = (created.get("data") or {}).get("task_id")
        if not task_id:
            raise FatalError(
                f"必剪创建任务未返回 task_id：{json.dumps(created, ensure_ascii=False)[:200]}"
            )
        return str(task_id)

    def _poll(self, client: httpx.Client, task_id: str) -> dict:
        waited = 0.0
        while waited < self._poll_timeout_s:
            try:
                resp = client.get(
                    f"{self.base}/task/result",
                    params={"model_id": QUERY_MODEL_ID, "task_id": task_id},
                    headers=HEADERS,
                )
            except httpx.HTTPError as exc:
                raise RecoverableError(f"必剪查询结果失败（网络）：{type(exc).__name__}") from exc
            if resp.status_code >= 400:
                self._raise_for_status(resp.status_code, resp.text[:300])

            body = (resp.json() or {}).get("data") or {}
            if body.get("state") == TASK_DONE_STATE:
                raw = body.get("result")
                if isinstance(raw, dict):
                    return raw
                try:
                    return json.loads(raw or "{}")
                except json.JSONDecodeError as exc:
                    raise FatalError("必剪返回的 result 不是合法 JSON") from exc
            self._sleep(POLL_INTERVAL_S)
            waited += POLL_INTERVAL_S
        # 等超时可按"上游慢"处理：重试是合理的，因为上传结果仍可复用（这里选择让上层重试）
        raise RecoverableError(
            f"必剪识别等待超过 {self._poll_timeout_s:.0f}s 仍未完成（task_id={task_id}）"
        )

    def _post(self, client: httpx.Client, path: str, body: dict) -> dict:
        try:
            resp = client.post(f"{self.base}{path}", content=json.dumps(body), headers=HEADERS)
        except httpx.HTTPError as exc:
            raise RecoverableError(f"必剪请求失败（网络）：{type(exc).__name__}") from exc
        if resp.status_code >= 400:
            self._raise_for_status(resp.status_code, resp.text[:300])
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise FatalError(f"必剪返回非 JSON：{resp.text[:200]}") from exc


def _parse_utterances(result: dict) -> list[Segment]:
    """`utterances[]` → 段落。时间戳是毫秒。"""
    segments: list[Segment] = []
    for item in result.get("utterances") or []:
        text = (item.get("transcript") or "").strip()
        if not text:
            continue
        segments.append(
            Segment(
                start=float(item.get("start_time") or 0) / 1000.0,
                end=float(item.get("end_time") or 0) / 1000.0,
                text=text,
            )
        )
    return segments
