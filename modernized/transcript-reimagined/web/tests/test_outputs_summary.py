"""产物、音频、reveal、SSE 与总结路由。"""

from __future__ import annotations

from pathlib import Path

import pytest


def _task_with_products(env, tmp_path: Path, *, text: str = "正文内容") -> int:
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="srt")
    txt = tmp_path / "meeting.txt"
    srt = tmp_path / "meeting.srt"
    txt.write_text(text, encoding="utf-8")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n正文\n", encoding="utf-8")
    env.store.update_task(tid, status="done", txt_path=str(txt), srt_path=str(srt))
    return tid


@pytest.mark.rule("RULE-139")
def test_output_preview_and_truncation(client, env, tmp_path):
    long_text = "字" * 200_001
    tid = _task_with_products(env, tmp_path, text=long_text)
    payload = client.get(f"/api/tasks/{tid}/output?kind=txt").json()
    assert payload["truncated"] is True
    assert len(payload["content"]) == 200_000
    assert payload["path"].endswith("meeting.txt")


def test_output_file_is_served_byte_exact(client, env, tmp_path):
    tid = _task_with_products(env, tmp_path, text="完整正文")
    response = client.get(f"/api/tasks/{tid}/output/file?kind=txt")
    assert response.status_code == 200
    assert response.content.decode("utf-8") == "完整正文"
    assert response.headers["cache-control"] == "no-store"


def test_missing_product_is_404(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    assert client.get(f"/api/tasks/{tid}/output?kind=txt").status_code == 404
    assert client.get(f"/api/tasks/{tid}/output?kind=srt").status_code == 404
    assert client.get("/api/tasks/999/output?kind=txt").status_code == 404


def test_original_audio_is_served(client, env, tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"audio-bytes")
    tid = env.store.create_task(name="n", source_path=str(source), mode="offline", artifact="txt")
    response = client.get(f"/api/tasks/{tid}/audio")
    assert response.status_code == 200
    assert response.content == b"audio-bytes"
    assert response.headers["content-type"].startswith("audio/mp4")


def test_reveal_requires_an_existing_path(client, env, tmp_path, monkeypatch):
    from transcript_reimagined.web.routes import outputs

    called: list[list[str]] = []
    monkeypatch.setattr(outputs.subprocess, "run", lambda cmd, **_: called.append(cmd))
    target = tmp_path / "x.txt"
    target.write_text("x", encoding="utf-8")

    assert client.post("/api/reveal", data={"path": str(target)}).status_code == 200
    assert called and called[0][:2] == ["open", "-R"]
    assert client.post("/api/reveal", data={"path": str(tmp_path / "nope")}).status_code == 404


def test_events_router_forwards_sse(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    response = client.get(f"/api/tasks/{tid}/events")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert '"type": "close"' in response.text
    assert client.get("/api/tasks/999/events").status_code == 404


@pytest.mark.rule("RULE-088")
def test_summary_routes(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    assert client.get("/api/tasks/999/summary").status_code == 404

    # 没有密钥时不可用（FakeSummaries 的 available 是 True，这里换成一个会拒绝的替身）
    class Rejecting:
        def payload(self, _tid):
            return {}

        def enable(self, _tid):
            raise ValueError("请先配置 API Key")

    old = env.jobs.summaries
    env.jobs.summaries = Rejecting()
    try:
        assert client.post(f"/api/tasks/{tid}/summary").status_code == 400
    finally:
        env.jobs.summaries = old

    response = client.post(f"/api/tasks/{tid}/summary")
    assert response.status_code == 200
    assert response.json()["status"] == "waiting"
    assert tid in env.jobs.summaries.enabled
    assert client.get(f"/api/tasks/{tid}/summary").json()["status"] == "waiting"
