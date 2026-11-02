"""引擎注册表：`SPECS` 是唯一真相来源（RULE-014 / RULE-052 / RULE-053 / RULE-082 / RULE-107）。

这些测试不发起任何网络请求：只检查解析、上限、凭据与目录派生。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.config import Config

from transcript_reimagined.engines import (
    AUTO_BY_ARTIFACT,
    ONLINE_ENGINES,
    SPECS,
    build_engine,
    chunk_max_for,
    engine_catalog,
    engine_kind_from_name,
    online_ready,
    required_key_attrs,
    resolve_kind,
    spec_for,
)


def test_registry_is_the_only_source_of_engine_metadata():
    assert [spec.id for spec in SPECS] == ["offline", "dashscope", "openrouter", "bcut"]
    assert spec_for("dashscope").max_chunk_s == 300.0
    assert spec_for("dashscope").required_keys == ("dashscope_api_key",)
    assert spec_for("openrouter").required_keys == ("openrouter_api_key",)
    assert spec_for("bcut").required_keys == ()
    with pytest.raises(ValueError, match="未知引擎"):
        spec_for("whisper")


@pytest.mark.rule("RULE-107")
def test_resolve_kind_offline_and_auto():
    cfg = Config()
    assert resolve_kind(cfg, mode="offline", artifact="srt", online_engine="bcut") == "offline"
    assert resolve_kind(cfg, mode="online", artifact="txt", online_engine="auto") == "dashscope"
    assert resolve_kind(cfg, mode="online", artifact="srt", online_engine="auto") == "openrouter"
    assert resolve_kind(cfg, mode="online", artifact="txt", online_engine="bcut") == "bcut"


@pytest.mark.rule("RULE-107")
def test_auto_mapping_is_exactly_txt_dashscope_srt_openrouter():
    assert AUTO_BY_ARTIFACT == {"txt": "dashscope", "srt": "openrouter"}
    assert ONLINE_ENGINES == ("auto", "dashscope", "openrouter", "bcut")


@pytest.mark.rule("RULE-107")
def test_unknown_online_engine_is_rejected():
    with pytest.raises(ValueError, match="未知的在线引擎"):
        resolve_kind(Config(), mode="online", artifact="txt", online_engine="whisper")


@pytest.mark.rule("RULE-014")
def test_chunk_max_is_the_smaller_of_config_and_engine_limit():
    cfg = Config(chunk_max_s=120.0)
    assert chunk_max_for(cfg, mode="online", artifact="txt") == 120.0
    assert chunk_max_for(cfg, mode="online", artifact="srt") == 120.0
    big = Config(chunk_max_s=500.0)
    assert chunk_max_for(big, mode="online", artifact="txt") == 300.0  # 百炼硬限
    assert chunk_max_for(big, mode="offline", artifact="srt") == 500.0
    assert chunk_max_for(big, mode="online", artifact="srt") == 500.0  # OpenRouter 无时长上限


@pytest.mark.rule("RULE-052")
def test_required_keys_follow_the_resolved_engine():
    cfg = Config()
    assert required_key_attrs(cfg, mode="offline", artifact="txt") == ()
    assert required_key_attrs(cfg, mode="online", artifact="txt") == ("dashscope_api_key",)
    assert required_key_attrs(cfg, mode="online", artifact="srt") == ("openrouter_api_key",)
    assert required_key_attrs(cfg, mode="online", artifact="txt", online_engine="bcut") == ()


@pytest.mark.rule("RULE-053")
def test_online_ready_needs_only_one_engine_without_credentials():
    assert online_ready(Config()) is True  # 必剪匿名可用
    catalog = engine_catalog(Config())
    bcut = next(entry for entry in catalog if entry["id"] == "bcut")
    dashscope = next(entry for entry in catalog if entry["id"] == "dashscope")
    assert bcut["ready"] is True
    assert dashscope["ready"] is False
    assert dashscope["max_chunk_s"] == 300.0
    assert "¥" in dashscope["cost"]


@pytest.mark.rule("RULE-053")
def test_catalog_readiness_follows_configured_keys():
    cfg = Config(dashscope_api_key="sk", openrouter_api_key="sk2")
    catalog = {entry["id"]: entry for entry in engine_catalog(cfg)}
    assert catalog["dashscope"]["ready"] is True
    assert catalog["openrouter"]["ready"] is True
    assert catalog["auto"]["ready"] is True


@pytest.mark.rule("RULE-082")
def test_resume_uses_the_recorded_engine_family():
    assert engine_kind_from_name("dashscope:qwen-audio-3.1-asr-flash") == "dashscope"
    assert engine_kind_from_name("bcut:8") == "bcut"
    assert engine_kind_from_name("offline:qwen3-asr+whisper") == "offline"
    assert engine_kind_from_name("auto") is None
    assert engine_kind_from_name(None) is None


def test_build_engine_accepts_model_override():
    engine = build_engine("dashscope:custom-model", Config(dashscope_api_key="sk"), artifact="txt")
    assert engine.name == "dashscope:custom-model"
    assert engine.max_chunk_s == 300.0
