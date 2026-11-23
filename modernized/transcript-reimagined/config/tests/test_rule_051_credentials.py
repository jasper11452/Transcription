"""RULE-051：凭据写入的校验、保留与原子性。

注意语义边界：`save_credentials` 把空串当作「清空这一项」；「空值 = 保留」是
API 层在调用前过滤输入（`RULE-040`），不在这里实现。
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from transcript_reimagined.config import MAX_CREDENTIAL_CHARS, save_credentials


def test_replaces_only_the_target_line_and_preserves_comments(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text(
        "# 用户手写注释\nDASHSCOPE_API_KEY=old\nONLINE_ENGINE=bcut\n", encoding="utf-8"
    )
    save_credentials(target, {"DASHSCOPE_API_KEY": " new-value "})
    text = target.read_text(encoding="utf-8")
    assert "# 用户手写注释" in text
    assert "ONLINE_ENGINE=bcut" in text
    assert "DASHSCOPE_API_KEY=new-value" in text
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_appends_missing_key(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text("A=1\n", encoding="utf-8")
    save_credentials(target, {"OPENROUTER_API_KEY": "sk-x"})
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines == ["A=1", "OPENROUTER_API_KEY=sk-x"]


def test_empty_value_clears_the_entry(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text("DASHSCOPE_API_KEY=secret\n", encoding="utf-8")
    save_credentials(target, {"DASHSCOPE_API_KEY": ""})
    assert target.read_text(encoding="utf-8") == "DASHSCOPE_API_KEY=\n"


def test_none_value_also_clears(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text("DASHSCOPE_API_KEY=secret\n", encoding="utf-8")
    save_credentials(target, {"DASHSCOPE_API_KEY": None})
    assert target.read_text(encoding="utf-8") == "DASHSCOPE_API_KEY=\n"


@pytest.mark.rule("RULE-051")
@pytest.mark.parametrize("value", ["has space", "a=b", "tab\there", "line\nbreak"])
def test_rejects_dangerous_values(tmp_path: Path, value: str):
    target = tmp_path / "config.env"
    with pytest.raises(ValueError, match="不允许"):
        save_credentials(target, {"DASHSCOPE_API_KEY": value})
    assert not target.exists()


@pytest.mark.rule("RULE-051")
def test_rejects_overlong_value(tmp_path: Path):
    target = tmp_path / "config.env"
    with pytest.raises(ValueError, match=str(MAX_CREDENTIAL_CHARS)):
        save_credentials(target, {"DASHSCOPE_API_KEY": "x" * (MAX_CREDENTIAL_CHARS + 1)})


@pytest.mark.rule("RULE-051")
def test_rejects_invalid_env_name(tmp_path: Path):
    target = tmp_path / "config.env"
    with pytest.raises(ValueError, match="名称"):
        save_credentials(target, {"BAD-NAME": "x"})


@pytest.mark.rule("RULE-051")
def test_write_is_atomic_and_owner_only(tmp_path: Path):
    target = tmp_path / "config.env"
    save_credentials(target, {"DASHSCOPE_API_KEY": "sk-secret"})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["config.env"]


@pytest.mark.rule("RULE-051")
def test_all_updates_are_validated_before_any_write(tmp_path: Path):
    target = tmp_path / "config.env"
    target.write_text("A=1\n", encoding="utf-8")
    before = target.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        save_credentials(target, {"GOOD": "ok", "BAD": "has space"})
    assert target.read_text(encoding="utf-8") == before
