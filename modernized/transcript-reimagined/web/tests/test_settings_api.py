"""设置资源：总结设置、模型清单、词表、凭据（RULE-039 / 040 / 051 / 065 / 066）。"""

from __future__ import annotations

import stat
from types import SimpleNamespace

import pytest
from transcript_reimagined.config import save_credentials


def test_summary_settings_payload_shape(client):
    payload = client.get("/api/summary-settings").json()
    assert payload["model"]
    assert payload["default_model"]
    assert payload["max_prompt_chars"] == 12_000
    assert payload["max_hot_words"] == 80
    assert "api_key_masked" in payload


@pytest.mark.rule("RULE-039")
def test_put_summary_settings_writes_atomically_and_preserves_rules(client, env, tmp_path):
    env.config.glossary_path.write_text(
        "# 用户规则\n集成 -> 集诚\n小新\n", encoding="utf-8"
    )
    body = {
        "model": "z-ai/glm-5.3-flash",
        "base_url": "https://openrouter.ai/api/v1/",
        "prompt": "新的总结要求",
        "hot_words": ["集诚", "小新"],
        "api_key": "sk-new-key",
    }
    response = client.put("/api/summary-settings", json=body)
    assert response.status_code == 200
    assert response.json()["model"] == "z-ai/glm-5.3-flash"

    config_text = env.config.config_path.read_text(encoding="utf-8")
    assert "SUMMARY_MODEL=z-ai/glm-5.3-flash" in config_text
    assert "OPENROUTER_BASE=https://openrouter.ai/api/v1" in config_text
    assert "OPENROUTER_API_KEY=sk-new-key" in config_text
    assert stat.S_IMODE(env.config.config_path.stat().st_mode) == 0o600

    prompt_path = env.config.summary_prompt_path
    assert prompt_path.read_text(encoding="utf-8") == "新的总结要求"
    assert stat.S_IMODE(prompt_path.stat().st_mode) == 0o600

    glossary = env.config.glossary_path.read_text(encoding="utf-8")
    assert "# 用户规则" in glossary and "集成 -> 集诚" in glossary
    assert "集诚" in glossary and "小新" in glossary


@pytest.mark.rule("RULE-040")
def test_blank_api_key_keeps_the_stored_secret(client, env):
    save_credentials(env.config.config_path, {"OPENROUTER_API_KEY": "sk-old"})
    env.config.openrouter_api_key = "sk-old"
    response = client.put(
        "/api/summary-settings",
        json={
            "model": "m",
            "base_url": "https://example.test/api",
            "prompt": "p",
            "api_key": "",
        },
    )
    assert response.status_code == 200
    assert env.config.openrouter_api_key == "sk-old"
    assert "OPENROUTER_API_KEY=sk-old" in env.config.config_path.read_text(encoding="utf-8")


@pytest.mark.rule("RULE-065")
@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ({"model": "bad model", "base_url": "https://x.test", "prompt": "p"}, "模型 ID"),
        ({"model": "m", "base_url": "ftp://x.test", "prompt": "p"}, "HTTP(S)"),
        ({"model": "m", "base_url": "https://x.test?q=1", "prompt": "p"}, "查询参数"),
        ({"model": "m", "base_url": "https://x.test", "prompt": "x" * 12_001}, "12000"),
        (
            {"model": "m", "base_url": "https://x.test", "prompt": "p", "hot_words": ["有 空格"]},
            "热词",
        ),
        ({"model": "m", "base_url": "https://x.test", "prompt": "p", "extra": 1}, "需要提供"),
    ],
)
def test_invalid_summary_settings_are_rejected(client, body, needle):
    response = client.put("/api/summary-settings", json=body)
    assert response.status_code == 400
    assert needle in response.json()["error"]


@pytest.mark.rule("RULE-040")
def test_empty_credential_keeps_existing_and_clear_list_wipes(client, env):
    save_credentials(env.config.config_path, {"DASHSCOPE_API_KEY": "sk-dash"})
    env.config.dashscope_api_key = "sk-dash"

    keep = client.post("/api/credentials", json={"keys": {"dashscope_api_key": ""}})
    assert keep.status_code == 200
    assert env.config.dashscope_api_key == "sk-dash"

    clear = client.post("/api/credentials", json={"keys": {}, "clear": ["dashscope_api_key"]})
    assert clear.status_code == 200
    assert env.config.dashscope_api_key == ""
    assert "DASHSCOPE_API_KEY=\n" in env.config.config_path.read_text(encoding="utf-8")


@pytest.mark.rule("RULE-051")
def test_credential_validation_rejects_unknown_and_dangerous_values(client, env):
    unknown = client.post("/api/credentials", json={"keys": {"nope": "x"}})
    assert unknown.status_code == 400 and "未知" in unknown.json()["error"]
    bad = client.post("/api/credentials", json={"keys": {"dashscope_api_key": "a b"}})
    assert bad.status_code == 400


def test_diar_setting_roundtrip(client, env):
    assert client.get("/api/diar-settings").json()["enabled"] is False

    enabled = client.put("/api/diar-settings", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json() == {"enabled": True, "available": True, "scope": "offline"}
    assert "ENABLE_DIAR=true" in env.config.config_path.read_text(encoding="utf-8")
    assert env.config.enable_diar is True

    disabled = client.put("/api/diar-settings", json={"enabled": False})
    assert disabled.status_code == 200
    assert "ENABLE_DIAR=false" in env.config.config_path.read_text(encoding="utf-8")
    assert env.config.enable_diar is False

    assert client.put("/api/diar-settings", json={}).status_code == 400
    assert client.put("/api/diar-settings", json={"enabled": "yes"}).status_code == 400


def test_glossary_read_write_and_validation(client, env):
    env.config.glossary_path.write_text("集成 -> 集诚\n", encoding="utf-8")
    read = client.get("/api/glossary")
    assert read.status_code == 200
    assert read.json()["rules"] == [{"wrong": "集成", "right": "集诚"}]

    written = client.put("/api/glossary", data={"text": "集成 -> 集诚\n小新\n"})
    assert written.status_code == 200 and written.json()["rule_count"] == 1
    assert stat.S_IMODE(env.config.glossary_path.stat().st_mode) == 0o600

    bad = client.put("/api/glossary", data={"text": "-> 集诚\n"})
    assert bad.status_code == 400
    assert "第 1 行" in bad.json()["error"]


def test_summary_models_requires_a_key(client):
    payload = client.get("/api/summary-models").json()
    assert payload["models"] == []
    assert "API Key" in payload["error"]


@pytest.mark.rule("RULE-034")
def test_summary_models_are_sorted_and_cached(client, env, monkeypatch):
    from transcript_reimagined.web.routes import settings

    env.config.openrouter_api_key = "sk"
    settings._model_cache.clear()
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {"id": "b/model", "name": "B", "context_length": 1000,
                     "pricing": {"prompt": "0.000001"}},
                    {"id": "a/model", "name": "A", "supported_parameters": ["reasoning"]},
                    {"id": "c/model", "name": "C"},
                ]
            },
        )

    monkeypatch.setattr(settings.httpx, "get", fake_get)
    first = client.get("/api/summary-models").json()
    assert [m["id"] for m in first["models"]] == ["a/model", "b/model", "c/model"]
    assert first["models"][1]["price_per_million_prompt"] == pytest.approx(1.0)
    assert first["models"][0]["reasoning"] is True
    assert first["cached"] is False

    second = client.get("/api/summary-models").json()
    assert second["cached"] is True
    assert len(calls) == 1

    client.get("/api/summary-models?refresh=true")
    assert len(calls) == 2


def test_summary_models_failure_degrades_to_empty_list(client, env, monkeypatch):
    from transcript_reimagined.web.routes import settings

    env.config.openrouter_api_key = "sk"
    settings._model_cache.clear()

    def boom(*_a, **_k):
        raise settings.httpx.ConnectError("down")

    monkeypatch.setattr(settings.httpx, "get", boom)
    payload = client.get("/api/summary-models").json()
    assert payload["models"] == []
    assert "失败" in payload["error"]
