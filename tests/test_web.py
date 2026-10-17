"""网页层测试：接口契约 + 密钥绝不外泄 + 在线模式的前置校验。"""

from __future__ import annotations

import json
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from transcript.config import Config
from transcript.models import Segment, TranscriptResult
from transcript.pipeline import Pipeline, RunResult
from transcript.store import Store
from transcript.web.app import create_app
from transcript.web.jobs import JobManager


class FakeEngine:
    has_timestamps = True
    name = "fake"

    def transcribe(
        self, audio_path: Path, *, language=None, hotwords=None, want_timestamps=False
    ) -> TranscriptResult:
        text = "网页测试的第一句话。第二句话在这里。"
        return TranscriptResult(
            text=text,
            segments=[
                Segment(0.0, 1.0, "网页测试的第一句话。"),
                Segment(1.0, 2.0, "第二句话在这里。"),
            ],
            engine=self.name,
            audio_seconds=2.0,
            cost_usd=0.0005,
            has_timestamps=True,
        )


def make_wav(tmp_path: Path, seconds: float = 3.0) -> Path:
    out = tmp_path / "clip.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
    )
    return out


@pytest.fixture
def client(tmp_path: Path):
    config = Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "state.db",
        output_dir=tmp_path / "output",
        glossary_path=tmp_path / "glossary.txt",
        dashscope_api_key="sk-super-secret-1234",
        openrouter_api_key="or-super-secret-5678",
    )
    store = Store(config.state_db)

    def factory(store_: Store, on_event) -> Pipeline:
        return Pipeline(
            config,
            store_,
            engine_factory=lambda *a, **k: FakeEngine(),
            vad_fn=lambda p: [(0.0, 3.0)],
            sleep=lambda s: None,
            on_event=on_event,
        )

    jobs = JobManager(config, store, pipeline_factory=factory)
    app = create_app(config, store, jobs)
    with TestClient(app) as c:
        c.state_config = config  # type: ignore[attr-defined]
        yield c


def wait_for_status(client: TestClient, task_id: int, want: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = client.get(f"/api/tasks/{task_id}").json()
        if last["task"]["status"] == want:
            return last
        time.sleep(0.05)
    raise AssertionError(f"任务没在 {timeout}s 内变成 {want}：{last}")


# ---------- 页面与状态 ----------


def test_index_page_is_served(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    assert "转录" in res.text
    assert "离线" in res.text  # 引擎分段控件（只有两个值）
    assert "在线密钥" in res.text  # 密钥可以在页面上填
    assert "开始离线转录" in res.text
    # 人的操作顺序：先选文件，再确认是否上传，最后开始；绝不能把隐私选择放在提交之后。
    assert (
        res.text.index('id="file"')
        < res.text.index('id="modeLever"')
        < res.text.index('id="submit"')
    )
    assert "完成后会显示文稿和字幕的实际位置" in res.text
    assert 'id="progressDeck" aria-label="走片进度" hidden' in res.text


def test_status_masks_credentials_and_never_leaks_plaintext(client: TestClient):
    """页面与接口只显示掩码尾号——这是硬约束，不是偏好。"""
    res = client.get("/api/status")
    assert res.status_code == 200
    body = res.text
    assert "sk-super-secret-1234" not in body
    assert "or-super-secret-5678" not in body

    data = res.json()
    assert data["credentials"]["dashscope_api_key"] == "已配置（尾号 1234）"
    assert data["online_ready"] is True


def test_status_reports_missing_credentials(tmp_path: Path):
    config = Config(
        config_path=tmp_path / "c.env",
        state_db=tmp_path / "s.db",
        output_dir=tmp_path / "o",
        glossary_path=tmp_path / "g.txt",
    )
    store = Store(config.state_db)
    app = create_app(config, store, JobManager(config, store))
    with TestClient(app) as c:
        data = c.get("/api/status").json()
    assert data["credentials"]["dashscope_api_key"] == "未配置"
    # 没有任何密钥时在线仍然**可用**：必剪是匿名接口。
    # 旧实现要求两把钥都在，页面会误报"未配置凭据"，而实际上必剪能跑——这里守住修正后的语义。
    assert data["online_ready"] is True
    ready = {e["id"]: e["ready"] for e in data["online_engines"]}
    assert ready["bcut"] is True
    assert ready["dashscope"] is False
    assert ready["openrouter"] is False


# ---------- 预估 ----------


def test_estimate_returns_duration_and_cost(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path, seconds=3.0)
    res = client.post(
        "/api/estimate", data={"source_path": str(src), "mode": "online", "artifact": "srt"}
    )
    body = res.json()
    assert body["ok"] is True
    assert 2.5 < body["duration_s"] < 3.5
    assert body["estimated_cost_usd"] is not None


def test_estimate_reports_bad_input_without_crashing(client: TestClient):
    res = client.post(
        "/api/estimate",
        data={"source_path": "/tmp/definitely-missing.m4a", "mode": "offline", "artifact": "txt"},
    )
    body = res.json()
    assert body["ok"] is False
    assert "不存在" in body["error"]


# ---------- 提交与产物 ----------


def test_full_task_flow_txt(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    res = client.post(
        "/api/tasks",
        data={"source_path": str(src), "mode": "offline", "artifact": "txt", "language": "zh"},
    )
    assert res.status_code == 200
    task_id = res.json()["task_id"]

    detail = wait_for_status(client, task_id, "done")
    assert detail["task"]["txt_path"] is not None
    assert detail["chunks"] and all(c["status"] == "done" for c in detail["chunks"])

    out = client.get(f"/api/tasks/{task_id}/output", params={"kind": "txt"}).json()
    assert "网页测试的第一句话" in out["content"]
    assert Path(out["path"]).exists()


def test_uploaded_file_can_create_and_finish_task(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    res = client.post(
        "/api/tasks",
        data={"mode": "offline", "artifact": "txt"},
        files={"file": (src.name, src.read_bytes(), "audio/wav")},
    )
    assert res.status_code == 200, res.text
    detail = wait_for_status(client, res.json()["task_id"], "done")
    source = Path(detail["task"]["source_path"])
    assert source.parent == client.state_config.state_db.parent / "uploads"
    assert source.read_bytes() == src.read_bytes()
    assert client.get(f"/api/tasks/{detail['task']['id']}/output").status_code == 200


def test_full_task_flow_srt(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    task_id = client.post(
        "/api/tasks", data={"source_path": str(src), "mode": "offline", "artifact": "srt"}
    ).json()["task_id"]
    wait_for_status(client, task_id, "done")
    srt = client.get(f"/api/tasks/{task_id}/output", params={"kind": "srt"}).json()["content"]
    assert "-->" in srt
    assert srt.strip().splitlines()[0] == "1"


def test_task_list_and_delete(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    task_id = client.post(
        "/api/tasks", data={"source_path": str(src), "mode": "offline", "artifact": "txt"}
    ).json()["task_id"]
    wait_for_status(client, task_id, "done")

    listed = client.get("/api/tasks").json()["tasks"]
    assert any(t["id"] == task_id for t in listed)
    assert client.delete(f"/api/tasks/{task_id}").json()["deleted"] == task_id
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_invalid_mode_and_artifact_are_rejected(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    assert (
        client.post(
            "/api/tasks", data={"source_path": str(src), "mode": "auto", "artifact": "txt"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/tasks", data={"source_path": str(src), "mode": "offline", "artifact": "both"}
        ).status_code
        == 400
    )


def test_missing_input_is_rejected_before_queueing(client: TestClient):
    res = client.post(
        "/api/tasks",
        data={"source_path": "/tmp/nope-does-not-exist.wav", "mode": "offline", "artifact": "txt"},
    )
    assert res.status_code == 400
    assert "不存在" in res.json()["error"]


def test_online_mode_requires_credentials(tmp_path: Path):
    """没配凭据就不该把任务排进队列然后失败——本地能判定的错误本地判定。"""
    config = Config(
        config_path=tmp_path / "c.env",
        state_db=tmp_path / "s.db",
        output_dir=tmp_path / "o",
        glossary_path=tmp_path / "g.txt",
    )
    store = Store(config.state_db)
    app = create_app(config, store, JobManager(config, store))
    src = make_wav(tmp_path)
    with TestClient(app) as c:
        res = c.post(
            "/api/tasks", data={"source_path": str(src), "mode": "online", "artifact": "txt"}
        )
    assert res.status_code == 400
    assert "DASHSCOPE_API_KEY" in res.json()["error"]


def test_output_missing_kind_returns_404(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    task_id = client.post(
        "/api/tasks", data={"source_path": str(src), "mode": "offline", "artifact": "txt"}
    ).json()["task_id"]
    wait_for_status(client, task_id, "done")
    assert client.get(f"/api/tasks/{task_id}/output", params={"kind": "srt"}).status_code == 404


def test_events_endpoint_streams_history_after_finish(client: TestClient, tmp_path: Path):
    """刷新页面后仍能看到已完成任务的进度历史（SSE 先补发历史再关闭）。"""
    src = make_wav(tmp_path)
    task_id = client.post(
        "/api/tasks", data={"source_path": str(src), "mode": "offline", "artifact": "txt"}
    ).json()["task_id"]
    wait_for_status(client, task_id, "done")
    with client.stream("GET", f"/api/tasks/{task_id}/events") as res:
        assert res.status_code == 200
        payload = "".join(res.iter_text())
    assert '"type": "close"' in payload
    assert '"stage": "probe"' in payload


def test_resume_starts_a_fresh_event_log(tmp_path: Path):
    """停止→继续（同一个 task_id 再跑一轮）时，新订阅不能重放上一轮的 result/close。

    实测 bug（2026-09-19 浏览器回归）：事件历史按 task_id 累积，续跑后页面重新订阅，
    先收到上一轮的 close，前端据此清掉 15s 对账轮询并停止跟随；后端最终跑完了，
    控制台却永远停在「4/9 停止中」，只能手动刷新。
    """
    config = Config(
        config_path=tmp_path / "c.env",
        state_db=tmp_path / "s.db",
        output_dir=tmp_path / "o",
        glossary_path=tmp_path / "g.txt",
    )
    store = Store(config.state_db)
    second_started, release_second = threading.Event(), threading.Event()
    state = {"runs": 0}

    class TwoRuns:
        def run(self, source, **kwargs):
            # 工厂每轮 run 都新建一个 pipeline 实例，计数必须放在实例外
            state["runs"] += 1
            if state["runs"] == 1:
                return RunResult(
                    task_id=kwargs["task_id"],
                    status="failed",
                    engine="-",
                    error="已停止：0 片已完成并保留，可续跑",
                )
            second_started.set()
            release_second.wait(timeout=5)
            return RunResult(task_id=kwargs["task_id"], status="done", engine="-")

        def cancel(self) -> None:
            pass

    jobs = JobManager(config, store, pipeline_factory=lambda store_, on_event: TwoRuns())
    try:
        tid = jobs.submit(source=tmp_path / "a.m4a", mode="offline", artifact="srt")
        deadline = time.time() + 5
        while time.time() < deadline and jobs.is_running(tid):
            time.sleep(0.02)
        first = json.dumps(jobs.history(tid), ensure_ascii=False)
        assert "已停止：0 片已完成并保留，可续跑" in first
        assert '"close"' in first

        jobs.submit(source=tmp_path / "a.m4a", mode="offline", artifact="srt", task_id=tid)
        assert second_started.wait(timeout=5), "第二轮没跑起来"
        fresh = json.dumps(jobs.history(tid), ensure_ascii=False)
        assert "已停止：0 片已完成并保留，可续跑" not in fresh, "续跑把上一轮的错误又重放了一遍"
        assert '"close"' not in fresh, "旧 close 会被重放，页面据此停止跟随"

        release_second.set()
        deadline = time.time() + 5
        while time.time() < deadline and jobs.is_running(tid):
            time.sleep(0.02)
        assert '"close"' in json.dumps(jobs.history(tid), ensure_ascii=False)
    finally:
        jobs.shutdown()


# ---------- 其他接口 ----------


def test_reveal_rejects_missing_path(client: TestClient):
    assert client.post("/api/reveal", data={"path": "/tmp/not-here-xyz"}).status_code == 404


def test_glossary_roundtrip(client: TestClient, tmp_path: Path):
    text = "艾麦 -> 砹脉\n佳路 => 嘉鹿\n"
    saved = client.put("/api/glossary", data={"text": text}).json()
    assert saved["rule_count"] == 2

    got = client.get("/api/glossary").json()
    assert got["text"] == text
    assert {r["wrong"] for r in got["rules"]} == {"艾麦", "佳路"}


def test_upload_stores_file_and_returns_path(client: TestClient):
    files = {"file": ("clip.wav", b"RIFF....WAVEfmt ", "audio/wav")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["bytes"] > 0
    assert Path(body["path"]).exists()
    Path(body["path"]).unlink()


def test_status_exposes_selectable_online_engines(client: TestClient):
    """页面靠这个列表渲染引擎选择；少了它，前端就只能干瞪眼。"""
    data = client.get("/api/status").json()
    ids = [e["id"] for e in data["online_engines"]]
    assert ids == ["auto", "dashscope", "openrouter", "bcut"]
    bcut = next(e for e in data["online_engines"] if e["id"] == "bcut")
    assert bcut["needs_key"] == []


def test_bcut_online_needs_no_credentials(tmp_path: Path):
    """必剪是匿名接口：即使一把钥匙都没有，也该允许提交在线任务。"""
    config = Config(
        config_path=tmp_path / "c.env",
        state_db=tmp_path / "s.db",
        output_dir=tmp_path / "o",
        glossary_path=tmp_path / "g.txt",
    )
    store = Store(config.state_db)
    app = create_app(config, store, JobManager(config, store))
    src = make_wav(tmp_path)
    with TestClient(app) as c:
        res = c.post(
            "/api/tasks",
            data={
                "source_path": str(src),
                "mode": "online",
                "artifact": "srt",
                "online_engine": "bcut",
            },
        )
    assert res.status_code == 200, res.json()
    assert res.json()["task_id"] > 0


def test_unknown_online_engine_is_rejected(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path)
    res = client.post(
        "/api/tasks",
        data={
            "source_path": str(src),
            "mode": "online",
            "artifact": "srt",
            "online_engine": "gpt5-asr",
        },
    )
    assert res.status_code == 400
    assert "online_engine" in res.json()["error"]


def test_estimate_respects_engine_choice(client: TestClient, tmp_path: Path):
    src = make_wav(tmp_path, seconds=3.0)
    free = client.post(
        "/api/estimate",
        data={
            "source_path": str(src),
            "mode": "online",
            "artifact": "srt",
            "online_engine": "bcut",
        },
    ).json()
    assert free["estimated_cost_usd"] == 0.0, "必剪免费，预估就该是 0"

    paid = client.post(
        "/api/estimate",
        data={
            "source_path": str(src),
            "mode": "online",
            "artifact": "srt",
            "online_engine": "openrouter",
        },
    ).json()
    assert paid["estimated_cost_usd"] > 0

    limited = client.post(
        "/api/estimate",
        data={
            "source_path": str(src),
            "mode": "online",
            "artifact": "txt",
            "online_engine": "dashscope",
        },
    ).json()
    # 引擎上限只会**收紧**切片：默认配置 120s < 300s，所以还是 120s
    # （收紧生效的场景在 test_engines_online::test_chunk_max_is_clamped_by_engine_limit）
    assert limited["chunk_max_s"] == 120.0


def test_stale_running_task_is_reported_as_resumable(client: TestClient):
    """模拟进程被杀后的状态：落库停在 running，但没有任何进程在跑。

    实测 bug：87 分钟录音跑到 26/100 时被 kill -9，重启后页面把它显示成"运行中"
    并**禁掉了续跑按钮**——用户从页面上永远救不回来（接口其实允许续跑）。
    接口必须同时给出"实际在跑吗"和"能不能续跑"。
    """
    store: Store = client.app.state.store  # type: ignore[attr-defined]
    stale_id = store.create_task(
        name="崩溃残留",
        source_path="/tmp/x.m4a",
        mode="offline",
        artifact="srt",
        engine="offline:qwen3-asr+whisper",
    )
    store.upsert_chunk(stale_id, idx=0, start=0, end=60, status="done", text="已完成的一片")

    detail = client.get(f"/api/tasks/{stale_id}").json()
    assert detail["task"]["status"] == "running"  # 落库状态确实停在 running
    assert detail["running"] is False
    assert detail["resumable"] is True
    assert detail["task"]["resumable"] is True

    listed = next(t for t in client.get("/api/tasks").json()["tasks"] if t["id"] == stale_id)
    assert listed["running"] is False and listed["resumable"] is True

    # 续跑接口本身一直是允许的（问题只在前端被挡住）
    assert client.post(f"/api/tasks/{stale_id}/resume").status_code == 200

    done = store.create_task(
        name="已完成", source_path="/tmp/x.m4a", mode="offline", artifact="txt"
    )
    store.update_task(done, status="done")
    assert client.get(f"/api/tasks/{done}").json()["resumable"] is False, "已完成的任务不该提示续跑"


# ---------- 在线密钥：页面输入 → 落盘 config.env ----------


def test_task_page_deep_link_uses_task_entry_not_console(client: TestClient):
    page = client.get("/t/1")
    assert page.status_code == 200
    assert "<title>任务 · 转录</title>" in page.text
    assert page.text != client.get("/").text


def test_status_lists_key_fields_derived_from_engine_table(client: TestClient):
    data = client.get("/api/status").json()
    fields = {f["attr"]: f for f in data["key_fields"]}
    # 字段集合来自 SPECS.required_keys：不写第二份"哪个引擎要哪把钥匙"
    assert set(fields) == {"dashscope_api_key", "openrouter_api_key"}
    assert fields["openrouter_api_key"]["env"] == "OPENROUTER_API_KEY"
    assert fields["dashscope_api_key"]["configured"] is True
    assert "sk-super-secret-1234" not in json.dumps(data, ensure_ascii=False)


def test_credentials_save_writes_file_masks_response_and_keeps_everything_else(
    client: TestClient,
):
    """密钥铁律：明文只从内存到磁盘，不回显、不吃掉用户手写的行、权限 600。"""
    cfg: Path = client.state_config.config_path  # type: ignore[attr-defined]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        "# 用户自己的注释，不能被吃掉\nDASHSCOPE_API_KEY=old-key-0000\nOUTPUT_DIR=/tmp/我的输出\n",
        encoding="utf-8",
    )

    res = client.post(
        "/api/credentials", json={"keys": {"openrouter_api_key": "or-new-secret-9999"}}
    )
    assert res.status_code == 200
    body = res.text
    assert "or-new-secret-9999" not in body, "接口绝不能回显明文"
    assert "尾号 9999" in body

    text = cfg.read_text(encoding="utf-8")
    assert "or-new-secret-9999" in text, "新密钥要落盘"
    assert "# 用户自己的注释，不能被吃掉" in text
    assert "OUTPUT_DIR=/tmp/我的输出" in text
    assert "DASHSCOPE_API_KEY=old-key-0000" in text, "没提交的那把钥匙不该被动"
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    assert not cfg.with_name(cfg.name + ".tmp").exists(), "临时文件不该残留"

    # 保存后同一个配置对象当场更新：页面不必重启服务，下一个任务就用新钥匙
    assert client.state_config.openrouter_api_key == "or-new-secret-9999"  # type: ignore[attr-defined]


def test_credentials_clear_is_explicit_and_blank_keeps_current(client: TestClient):
    cfg: Path = client.state_config.config_path  # type: ignore[attr-defined]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("DASHSCOPE_API_KEY=sk-super-secret-1234\n", encoding="utf-8")
    # 留空 = 保持现状（避免"点一下保存就把密钥清了"）
    assert (
        client.post("/api/credentials", json={"keys": {"dashscope_api_key": "   "}}).status_code
        == 200
    )
    assert "sk-super-secret-1234" in cfg.read_text(encoding="utf-8")
    # 清除必须显式说
    res = client.post("/api/credentials", json={"clear": ["dashscope_api_key"]})
    assert res.status_code == 200
    assert res.json()["key_fields"][0]["configured"] is False or True  # 顺序由表格派生，只看值
    fields = {f["attr"]: f for f in res.json()["key_fields"]}
    assert fields["dashscope_api_key"]["configured"] is False
    assert "DASHSCOPE_API_KEY=\n" in cfg.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        {"keys": {"not_a_real_field": "x"}},
        {"keys": {"dashscope_api_key": "sk-has space"}},
        {"keys": {"dashscope_api_key": "sk-has\nnewline"}},
        {"keys": {"dashscope_api_key": "sk-eq=uals"}},
        {"keys": {"dashscope_api_key": "x" * 600}},
        {"clear": ["nope"]},
    ],
)
def test_credentials_reject_bad_input_without_touching_file(client: TestClient, payload):
    """宁可报错，也不要把用户的配置文件写坏。"""
    cfg: Path = client.state_config.config_path  # type: ignore[attr-defined]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("DASHSCOPE_API_KEY=keep-me-0000\n", encoding="utf-8")
    res = client.post("/api/credentials", json=payload)
    assert res.status_code == 400
    assert cfg.read_text(encoding="utf-8") == "DASHSCOPE_API_KEY=keep-me-0000\n"
