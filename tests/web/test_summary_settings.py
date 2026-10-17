"""模型连接设置：隔离配置、只用假密钥，禁止保存动作访问上游。"""

from unittest.mock import Mock

import httpx
import pytest

from transcript.config import Config


def connection(**changes):
    return {
        "model": "custom-model",
        "base_url": "http://127.0.0.1:9999/v1/",
        "prompt": "只归纳材料中明确的信息。",
        **changes,
    }


def test_save_custom_connection_persists_and_masks_key(client, config, monkeypatch):
    config.config_path = config.config_path.parent / "new-directory" / "config.env"
    config.dashscope_api_key = "other-provider-key"
    network = Mock(side_effect=AssertionError("saving must not call upstream"))
    monkeypatch.setattr(httpx, "get", network)
    monkeypatch.setattr(httpx, "post", network)
    secret = "fixture-summary-key-9753"
    response = client.put("/api/summary-settings", json=connection(api_key=secret))
    assert response.status_code == 200
    body = response.json()
    assert body["base_url"] == "http://127.0.0.1:9999/v1"
    assert body["model"] == "custom-model"
    assert body["api_key_configured"] is True
    assert body["api_key_masked"].endswith("9753")
    assert secret not in response.text
    assert secret not in client.get("/api/summary-settings").text
    assert secret not in client.get("/").text
    assert config.openrouter_api_key == secret
    assert config.dashscope_api_key == "other-provider-key"
    assert config.config_path.stat().st_mode & 0o777 == 0o600
    loaded = Config.load(config.config_path)
    assert loaded.openrouter_api_key == secret
    assert loaded.openrouter_base == body["base_url"]
    assert loaded.summary_model == "custom-model"
    network.assert_not_called()


def test_blank_or_omitted_key_preserves_existing_and_comments(client, config):
    config.config_path.write_text(
        "# keep this comment\nDASHSCOPE_API_KEY=other-fake-key\n", encoding="utf-8"
    )
    client.put("/api/summary-settings", json=connection(api_key="fixture-key-1234"))
    for extra in ({}, {"api_key": "  "}):
        response = client.put("/api/summary-settings", json=connection(**extra))
        assert response.status_code == 200
        assert response.json()["api_key_masked"].endswith("1234")
        assert config.openrouter_api_key == "fixture-key-1234"
    saved = config.config_path.read_text(encoding="utf-8")
    assert "# keep this comment" in saved
    assert "DASHSCOPE_API_KEY=other-fake-key" in saved


@pytest.mark.parametrize("key", [None, [], 7, "bad\nkey", "bad\0key", "x" * 513, "bad=value"])
def test_invalid_key_is_rejected_without_writes_or_echo(client, config, key):
    response = client.put("/api/summary-settings", json=connection(api_key=key))
    assert response.status_code == 400
    assert "API Key" in response.json()["error"]
    assert not config.config_path.exists()
    assert not config.openrouter_api_key


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/config",
        "https://key@example.com/v1",
        "https://example.com/?key=test",
        "not-a-url",
    ],
)
def test_invalid_base_is_rejected_without_saving_key(client, config, url):
    response = client.put(
        "/api/summary-settings", json=connection(base_url=url, api_key="fixture-key")
    )
    assert response.status_code == 400
    assert not config.config_path.exists()


def test_model_list_uses_saved_base_and_new_key_not_stale_cache(client, config, monkeypatch):
    requests = []

    def get(url, *, headers, timeout):
        requests.append((url, headers["Authorization"]))
        return httpx.Response(
            200,
            json={"data": [{"id": f"model-{len(requests)}"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)
    for secret in ("fixture-old-key", "fixture-new-key"):
        assert (
            client.put("/api/summary-settings", json=connection(api_key=secret)).status_code == 200
        )
        body = client.get("/api/summary-models").json()
        assert body["models"]
        assert not body["cached"]
        assert client.get("/api/summary-models").json()["cached"]
    assert requests == [
        ("http://127.0.0.1:9999/v1/models", "Bearer fixture-old-key"),
        ("http://127.0.0.1:9999/v1/models", "Bearer fixture-new-key"),
    ]
