"""RULE-106：凭据只以掩码出现。

规则卡：``analysis/transcript/BUSINESS_RULES.md`` `RULE-106`。重建版收紧了一处
边角：长度 ≤8 的密钥不显示尾部（见 `../../DEVIATIONS.md` D1）。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.config import Config, mask, mask_preview


@pytest.mark.rule("RULE-106")
def test_long_secret_shows_only_last_four():
    secret = "sk-or-v1-0123456789XY9Z"
    assert "XY9Z" in mask(secret)
    assert secret not in mask(secret)
    assert mask_preview(secret).endswith("XY9Z")
    assert secret not in mask_preview(secret)


@pytest.mark.rule("RULE-106")
def test_short_secret_is_never_echoed():
    for secret in ("a", "abcd", "12345678"):
        assert secret not in mask(secret)
        assert secret not in mask_preview(secret)


@pytest.mark.rule("RULE-106")
def test_unset_secret_renders_as_not_configured():
    assert mask("") == "未配置"
    assert mask(None) == "未配置"
    assert mask_preview("") == ""
    assert mask_preview(None) == ""


@pytest.mark.rule("RULE-106")
def test_credential_status_has_no_plaintext():
    cfg = Config(
        dashscope_api_key="sk-dashscope-secret-XY9Z",
        openrouter_api_key="sk-openrouter-secret-ABCD",
    )
    status = cfg.credential_status()
    assert status["dashscope_api_key"] == "已配置（尾号 XY9Z）"
    assert status["openrouter_api_key"] == "已配置（尾号 ABCD）"
    joined = " ".join(status.values())
    assert "sk-dashscope-secret" not in joined
    assert "sk-openrouter-secret" not in joined
