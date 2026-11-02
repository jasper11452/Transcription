"""模型连接设置：隔离配置、只用假密钥，禁止保存动作访问上游。

密钥只有一条写入口（`POST /api/credentials`）；`PUT /api/summary-settings` 只管
Base URL / 模型 / 提示词 / 热词，收到 `api_key` 直接 400。
"""

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


def save_key(client, secret):
    return client.post("/api/credentials", json={"keys": {"openrouter_api_key": secret}})


def test_save_custom_connection_persists_and_masks_key(client, config, monkeypatch):
    config.config_path = config.config_path.parent / "new-directory" / "config.env"
    config.dashscope_api_key = "other-provider-key"
    network = Mock(side_effect=AssertionError("saving must not call upstream"))
    monkeypatch.setattr(httpx, "get", network)
    monkeypatch.setattr(httpx, "post", network)
    secret = "fixture-summary-key-9753"

    assert save_key(client, secret).status_code == 200
    response = client.put("/api/summary-settings", json=connection())
    assert response.status_code == 200
    body = response.json()
    assert body["base_url"] == "http://127.0.0.1:9999/v1"
    assert body["model"] == "custom-model"
    # 密钥状态只在凭据接口里：这里不再回显任何密钥信息
    assert secret not in client.get("/api/summary-settings").text
    fields = {f["attr"]: f for f in client.get("/api/status").json()["key_fields"]}
    assert fields["openrouter_api_key"]["masked"].endswith("9753")
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


def test_summary_settings_rejects_the_removed_key_field(client, config):
    """密钥已经只走凭据接口：旧调用方传 api_key 必须报错，而不是被静默忽略。"""
    save_key(client, "fixture-key-1234")
    response = client.put("/api/summary-settings", json=connection(api_key="fixture-new-key"))
    assert response.status_code == 400
    assert config.openrouter_api_key == "fixture-key-1234"


def test_summary_settings_keeps_existing_key_and_comments(client, config):
    config.config_path.write_text(
        "# keep this comment\nDASHSCOPE_API_KEY=other-fake-key\n", encoding="utf-8"
    )
    save_key(client, "fixture-key-1234")
    response = client.put("/api/summary-settings", json=connection())
    assert response.status_code == 200
    assert "api_key" not in response.json()
    assert config.openrouter_api_key == "fixture-key-1234"
    saved = config.config_path.read_text(encoding="utf-8")
    assert "# keep this comment" in saved
    assert "DASHSCOPE_API_KEY=other-fake-key" in saved


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/config",
        "https://key@example.com/v1",
        "https://example.com/?key=test",
        "not-a-url",
    ],
)
def test_invalid_base_is_rejected_without_touching_the_saved_key(client, config, url):
    save_key(client, "fixture-key")
    before = config.config_path.read_text(encoding="utf-8")
    response = client.put("/api/summary-settings", json=connection(base_url=url))
    assert response.status_code == 400
    assert config.config_path.read_text(encoding="utf-8") == before


def test_model_list_uses_new_key_and_drops_stale_cache(client, config, monkeypatch):
    """换密钥后模型清单必须重新拉：旧密钥的失败结果不能被缓存 10 分钟继续误导人。"""
    requests = []

    def get(url, *, headers, timeout):
        requests.append((url, headers["Authorization"]))
        return httpx.Response(
            200,
            json={"data": [{"id": f"model-{len(requests)}"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)
    save_key(client, "fixture-old-key")
    assert client.put("/api/summary-settings", json=connection()).status_code == 200
    assert client.get("/api/summary-models").json()["models"]
    assert client.get("/api/summary-models").json()["cached"]

    save_key(client, "fixture-new-key")
    body = client.get("/api/summary-models").json()
    assert body["models"]
    assert not body["cached"]
    assert requests == [
        ("http://127.0.0.1:9999/v1/models", "Bearer fixture-old-key"),
        ("http://127.0.0.1:9999/v1/models", "Bearer fixture-new-key"),
    ]
