"""任务资源：校验、创建、列表、详情、取消、续跑、删除（RULE-063 / RULE-082 / RULE-089）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from transcript_reimagined.domain import AudioInfo


def audio_info(path: Path, duration: float = 12.0) -> AudioInfo:
    return AudioInfo(
        path=path,
        duration=duration,
        size_bytes=path.stat().st_size if path.exists() else 1,
        codec="pcm_s16le",
        sample_rate=16_000,
        channels=1,
        has_audio=True,
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "meeting.wav"
    path.write_bytes(b"audio")
    return path


@pytest.fixture(autouse=True)
def fake_probe(monkeypatch):
    from transcript_reimagined.web.routes import status, tasks

    def probe(path):
        p = Path(path)
        if not p.exists():
            raise OSError(f"文件不存在：{p}")
        return audio_info(p)

    monkeypatch.setattr(tasks.audio_mod, "probe", probe)
    monkeypatch.setattr(status.audio_mod, "probe", probe)


@pytest.mark.rule("RULE-063")
@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [("mode", "stream", "mode"), ("artifact", "docx", "artifact"), ("online_engine", "whisper", "online_engine")],
)
def test_invalid_submission_is_rejected(client, source, field, value, needle):
    form = {"source_path": str(source), "mode": "offline", "artifact": "txt", "online_engine": "auto"}
    form[field] = value
    response = client.post("/api/tasks", data=form)
    assert response.status_code == 400
    assert needle in response.json()["error"]


def test_missing_source_is_rejected(client):
    response = client.post("/api/tasks", data={"source_path": "", "mode": "offline", "artifact": "txt"})
    assert response.status_code == 400
    assert "文件或路径" in response.json()["error"]


def test_offline_task_is_created_and_submitted(client, env, source):
    response = client.post(
        "/api/tasks",
        data={"source_path": str(source), "mode": "offline", "artifact": "txt", "language": "zh"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    task = env.store.get_task(payload["task_id"])
    assert task is not None and task.mode == "offline" and task.artifact == "txt"
    assert env.jobs.submitted[-1]["task_id"] == payload["task_id"]


def test_online_task_without_credentials_is_rejected(client, source):
    response = client.post(
        "/api/tasks",
        data={"source_path": str(source), "mode": "online", "artifact": "txt", "online_engine": "dashscope"},
    )
    assert response.status_code == 400
    assert "DASHSCOPE_API_KEY" in response.json()["error"]


def test_uploaded_file_is_stored_and_submitted(client, env, tmp_path):
    response = client.post(
        "/api/tasks",
        data={"mode": "offline", "artifact": "txt"},
        files={"file": ("clip.wav", b"uploaded-bytes", "audio/wav")},
    )
    assert response.status_code == 200
    submitted = env.jobs.submitted[-1]
    assert "uploads" in str(submitted["source"])
    assert Path(submitted["source"]).read_bytes() == b"uploaded-bytes"


def test_list_and_detail_flags(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    env.store.upsert_chunk(tid, idx=0, start=0, end=1, status="done", text="正文")

    listing = client.get("/api/tasks")
    assert listing.status_code == 200
    assert listing.json()["tasks"][0]["id"] == tid

    detail = client.get(f"/api/tasks/{tid}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["task"]["id"] == tid
    assert payload["chunks"][0]["text"] == "正文"
    # 数据库是 running、但本进程没有活 job → 服务端给 interrupted（Q10）
    assert payload["interrupted"] is True
    assert payload["running"] is False
    assert payload["resumable"] is True

    env.jobs.running.add(tid)
    live = client.get(f"/api/tasks/{tid}").json()
    assert live["running"] is True and live["interrupted"] is False


def test_cancel_requires_a_running_task(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    assert client.post(f"/api/tasks/{tid}/cancel").status_code == 409
    env.jobs.running.add(tid)
    response = client.post(f"/api/tasks/{tid}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelling"
    assert tid in env.jobs.cancelled


@pytest.mark.rule("RULE-082")
def test_resume_keeps_the_recorded_engine(client, env):
    tid = env.store.create_task(
        name="n", source_path="/tmp/a.wav", mode="online", artifact="srt", engine="dashscope:m"
    )
    env.store.update_task(tid, status="failed")
    response = client.post(f"/api/tasks/{tid}/resume")
    assert response.status_code == 200
    assert env.jobs.submitted[-1]["online_engine"] == "dashscope"
    assert env.store.get_task(tid).status == "pending"


def test_delete_refuses_running_tasks(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    env.jobs.running.add(tid)
    assert client.delete(f"/api/tasks/{tid}").status_code == 409
    env.jobs.running.discard(tid)
    assert client.delete(f"/api/tasks/{tid}").status_code == 200
    assert env.store.get_task(tid) is None


def test_estimate_reports_cost_and_chunk_cap(client, source):
    response = client.post(
        "/api/estimate",
        data={"source_path": str(source), "mode": "online", "artifact": "srt"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["duration_s"] == 12.0
    assert payload["estimated_cost_usd"] > 0
    assert payload["chunk_max_s"] == 120.0
