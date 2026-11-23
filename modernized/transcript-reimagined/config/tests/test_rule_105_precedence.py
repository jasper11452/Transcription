"""RULE-105：配置优先级、旧版兼容与数值手误可见性。

规则卡：``analysis/transcript/BUSINESS_RULES.md`` `RULE-105`。人裁定为缺陷的是
「数值解析静默吞 ValueError」，其余优先级语义保持 legacy。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcript_reimagined.config import Config, ConfigError


def write_env(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.rule("RULE-105")
def test_missing_file_uses_builtin_defaults(tmp_path: Path):
    cfg = Config.load(tmp_path / "config.env")
    assert cfg.chunk_min_s == 30.0
    assert cfg.chunk_max_s == 120.0
    assert cfg.chunk_overlap_s == 0.5
    assert cfg.online_concurrency == 4
    assert cfg.dashscope_api_key == ""


@pytest.mark.rule("RULE-105")
def test_config_env_wins_over_defaults(tmp_path: Path):
    path = write_env(
        tmp_path / "config.env",
        "DASHSCOPE_API_KEY=sk-test\n"
        "CHUNK_MAX_S=90\n"
        "OPENROUTER_BASE=https://example.test/api/v1/\n"
        "ENABLE_DIAR=YES\n",
    )
    cfg = Config.load(path)
    assert cfg.dashscope_api_key == "sk-test"
    assert cfg.chunk_max_s == 90.0
    assert cfg.openrouter_base == "https://example.test/api/v1"
    assert cfg.enable_diar is True


@pytest.mark.rule("RULE-105")
def test_numeric_typo_is_visible_at_load(tmp_path: Path):
    """CHUNK_MAX_S=12O 必须报错，不能静默回退 120。"""
    path = write_env(tmp_path / "config.env", "CHUNK_MAX_S=12O\n")
    with pytest.raises(ConfigError) as excinfo:
        Config.load(path)
    message = str(excinfo.value)
    assert "CHUNK_MAX_S" in message
    assert "12O" in message


@pytest.mark.rule("RULE-105")
def test_all_numeric_problems_reported_together(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "CHUNK_MAX_S=12O\nBACKOFF_BASE=fast\n")
    with pytest.raises(ConfigError) as excinfo:
        Config.load(path)
    message = str(excinfo.value)
    assert "CHUNK_MAX_S" in message and "BACKOFF_BASE" in message


@pytest.mark.rule("RULE-105")
def test_empty_numeric_value_falls_back_to_default(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "CHUNK_MAX_S=\n")
    assert Config.load(path).chunk_max_s == 120.0


@pytest.mark.rule("RULE-105")
def test_out_of_range_values_are_fatal(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "CHUNK_MIN_S=200\nCHUNK_MAX_S=120\n")
    with pytest.raises(ConfigError, match="CHUNK_MIN_S"):
        Config.load(path)


@pytest.mark.rule("RULE-105")
def test_legacy_summary_settings_adopted_when_new_settings_absent(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "DASHSCOPE_API_KEY=sk\n")
    (tmp_path / "summary-settings.json").write_text(
        json.dumps({"model": "legacy/model", "prompt": "旧版提示词"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.summary_model == "legacy/model"
    assert cfg.summary_prompt == "旧版提示词"


@pytest.mark.rule("RULE-105")
def test_prompt_file_wins_over_legacy_prompt(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "")
    (tmp_path / "summary-prompt.txt").write_text("新提示词", encoding="utf-8")
    (tmp_path / "summary-settings.json").write_text(
        json.dumps({"model": "legacy/model", "prompt": "旧提示词"}), encoding="utf-8"
    )
    cfg = Config.load(path)
    assert cfg.summary_prompt == "新提示词"
    assert cfg.summary_model == "legacy/model"  # 模型仍从旧版补


@pytest.mark.rule("RULE-105")
def test_summary_model_in_config_env_wins_over_legacy(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "SUMMARY_MODEL=new/model\n")
    (tmp_path / "summary-settings.json").write_text(
        json.dumps({"model": "legacy/model", "prompt": "旧提示词"}), encoding="utf-8"
    )
    cfg = Config.load(path)
    assert cfg.summary_model == "new/model"
    assert cfg.summary_prompt == "旧提示词"  # 提示词文件缺失，仍从旧版补


@pytest.mark.rule("RULE-105")
def test_unreadable_legacy_file_is_fatal(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "")
    (tmp_path / "summary-settings.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="无法读取"):
        Config.load(path)


@pytest.mark.rule("RULE-105")
def test_non_object_legacy_file_is_fatal(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "")
    (tmp_path / "summary-settings.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="格式不正确"):
        Config.load(path)


@pytest.mark.rule("RULE-105")
def test_wrong_type_legacy_model_is_fatal(tmp_path: Path):
    path = write_env(tmp_path / "config.env", "")
    (tmp_path / "summary-settings.json").write_text('{"model": 42}', encoding="utf-8")
    with pytest.raises(ConfigError, match="模型配置无效"):
        Config.load(path)


@pytest.mark.rule("RULE-106")
def test_credentials_are_never_read_from_shell_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "from-shell-must-not-be-used")
    cfg = Config.load(write_env(tmp_path / "config.env", ""))
    assert cfg.dashscope_api_key == ""


@pytest.mark.rule("RULE-105")
def test_config_error_is_also_value_error(tmp_path: Path):
    """兼容遗留调用方：旧代码捕获 ValueError，新异常也必须能被它接住。"""
    path = write_env(tmp_path / "config.env", "CHUNK_MAX_S=12O\n")
    with pytest.raises(ValueError):
        Config.load(path)
