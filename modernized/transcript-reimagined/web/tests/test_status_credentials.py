"""状态、凭据掩码、引擎目录与深链页面（RULE-106 / RULE-053 / RULE-140）。"""

from __future__ import annotations

import pytest
from transcript_reimagined.domain import AudioInfo

from transcript_reimagined.web.routes import status as status_route


def test_status_never_leaks_plaintext_keys(client, env):
    env.config.dashscope_api_key = "sk-dashscope-secret-XY9Z"
    env.config.openrouter_api_key = "sk-openrouter-secret-ABCD"
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.text
    assert "sk-dashscope-secret" not in body
    assert "sk-openrouter-secret" not in body
    payload = response.json()
    assert payload["credentials"]["dashscope_api_key"] == "已配置（尾号 XY9Z）"
    assert payload["credentials"]["openrouter_api_key"] == "已配置（尾号 ABCD）"


def test_status_key_fields_are_derived_from_the_engine_registry(client):
    payload = client.get("/api/status").json()
    assert [f["attr"] for f in payload["key_fields"]] == [
        "dashscope_api_key",
        "openrouter_api_key",
    ]
    assert payload["key_fields"][0]["env"] == "DASHSCOPE_API_KEY"


@pytest.mark.rule("RULE-053")
def test_status_engine_catalog_readiness(client, env):
    payload = client.get("/api/status").json()
    assert payload["online_ready"] is True  # 必剪匿名可用
    entries = {e["id"]: e for e in payload["online_engines"]}
    assert entries["bcut"]["ready"] is True
    assert entries["dashscope"]["ready"] is False
    assert entries["dashscope"]["max_chunk_s"] == 300.0
    assert entries["auto"]["ready"] is False

    env.config.dashscope_api_key = "sk"
    env.config.openrouter_api_key = "sk2"
    refreshed = {e["id"]: e for e in client.get("/api/status").json()["online_engines"]}
    assert refreshed["dashscope"]["ready"] is True
    assert refreshed["auto"]["ready"] is True


@pytest.mark.rule("RULE-026")
def test_estimate_respects_the_engine_choice(client, tmp_path, monkeypatch):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    info = AudioInfo(source, 3600.0, 1, "wav", 16000, 1, True)
    monkeypatch.setattr(status_route.audio_mod, "probe", lambda _p: info)

    def call(engine: str):
        return client.post(
            "/api/estimate",
            data={"source_path": str(source), "mode": "online", "artifact": "txt",
                  "online_engine": engine},
        ).json()

    assert call("bcut")["estimated_cost_usd"] == 0.0
    assert call("dashscope")["estimated_cost_usd"] is None
    assert call("openrouter")["estimated_cost_usd"] == pytest.approx(0.1)
    assert call("auto")["estimated_cost_usd"] is None  # txt → 百炼，不猜


def test_task_page_deep_link_boots_the_task(client, env):
    tid = env.store.create_task(name="n", source_path="/tmp/a.wav", mode="offline", artifact="txt")
    response = client.get(f"/t/{tid}")
    assert response.status_code == 200
    assert f'"id": {tid}' in response.text
    assert '"task":' in response.text

    missing = client.get("/t/9999")
    assert missing.status_code == 200
    assert '"task": null' in missing.text


def test_invalid_credentials_do_not_touch_the_file(client, env):
    env.config.config_path.write_text("DASHSCOPE_API_KEY=old\n", encoding="utf-8")
    before = env.config.config_path.read_text(encoding="utf-8")
    response = client.post("/api/credentials", json={"keys": {"dashscope_api_key": "a b"}})
    assert response.status_code == 400
    assert env.config.config_path.read_text(encoding="utf-8") == before
