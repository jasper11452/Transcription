"""`RULE-059` — HTTP 失败分类：可重试还是致命（`transcript_reimagined.domain.errors`）。

规则卡（`AI_NATIVE_SPEC.md` §5.2）：
    上游返回 429 且 body 含 `"code":"Throttling"` → 抛 `RecoverableError`，
    消息含 `HTTP 429 Throttling`，可重试；400/401 抛致命的 `UpstreamError`，
    **永不重试**。

人裁定：`RecoverableError` / `FatalError` 的分层**就是**重试策略，不是描述性标签
（`REIMAGINED_ARCHITECTURE.md` §2 的 `domain/` 行）。所以这里既断言映射表，
也断言 `recoverable` 旗标的继承关系。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.domain import (
    FatalError,
    InputError,
    RecoverableError,
    TranscriptError,
    UpstreamError,
    classify_http,
)

pytestmark = pytest.mark.rule("RULE-059")

RETRYABLE_STATUSES = [408, 409, 425, 429, 500, 501, 502, 503, 504, 520, 599]
FATAL_STATUSES = [400, 401, 402, 403, 404, 405, 410, 413, 418, 422, 451, 499]


@pytest.mark.parametrize("status", RETRYABLE_STATUSES)
def test_rule_059_retryable_statuses_map_to_recoverable_error(status: int) -> None:
    err = classify_http(status)
    assert isinstance(err, RecoverableError)
    assert err.recoverable is True
    assert f"HTTP {status}" in str(err)


@pytest.mark.parametrize("status", FATAL_STATUSES)
def test_rule_059_other_statuses_map_to_fatal_upstream_error(status: int) -> None:
    err = classify_http(status)
    assert isinstance(err, UpstreamError)
    assert isinstance(err, FatalError)
    assert err.recoverable is False
    assert err.status == status
    assert f"HTTP {status}" in str(err)


def test_rule_059_429_with_throttling_code_keeps_status_and_code_in_message() -> None:
    """规则卡给定的判据：429 + `"code":"Throttling"`。"""
    err = classify_http(429, '{"code":"Throttling","message":"Requests are too frequent"}')
    assert isinstance(err, RecoverableError)
    assert "HTTP 429 Throttling" in str(err)
    assert err.recoverable is True


def test_rule_059_code_extraction_accepts_both_spacing_variants() -> None:
    assert "HTTP 429 Throttling" in str(classify_http(429, '{"code": "Throttling"}'))
    assert "HTTP 429 Throttling" in str(classify_http(429, '{"code":"Throttling"}'))


def test_rule_059_fatal_upstream_error_carries_status_and_code() -> None:
    """400/401 必须带 status 与 code —— 「永不重试」的错误要能定位。"""
    err = classify_http(400, '{"code":"InvalidParameter","message":"bad format"}')
    assert isinstance(err, UpstreamError)
    assert err.status == 400
    assert err.code == "InvalidParameter"
    assert err.recoverable is False
    assert "HTTP 400 InvalidParameter" in str(err)

    err401 = classify_http(401, '{"code":"InvalidApiKey"}')
    assert isinstance(err401, UpstreamError)
    assert err401.status == 401
    assert err401.code == "InvalidApiKey"


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_rule_059_classify_http_returns_an_instance_and_does_not_raise(status: int) -> None:
    """契约：**返回**异常实例，由调用方 `raise classify_http(...)`。

    legacy 三个调用点都这么写（`dashscope.py:146`、`openrouter.py:87`、`bcut.py:88`），
    所以这是对外契约的一部分，不能改成 raise。
    """
    err = classify_http(status, "{}")
    assert isinstance(err, TranscriptError)


def test_rule_059_body_without_json_still_yields_a_usable_message() -> None:
    """body 不是 JSON 也要有可用消息，只是没有上游 code。"""
    err = classify_http(503, "<html>502 Bad Gateway</html>")
    assert isinstance(err, RecoverableError)
    assert str(err) == "上游暂时不可用（HTTP 503）"
    assert not str(err).endswith(" ")

    fatal = classify_http(400, "not json")
    assert isinstance(fatal, UpstreamError)
    assert fatal.status == 400
    assert fatal.code is None


def test_rule_059_message_never_echoes_body_secrets() -> None:
    """NFR-4：凭据永不进消息 / 产物 / 日志。

    只允许从 body 里取 code 字段的值。这里用的是假值（非 legacy 真实凭据），
    与 legacy 凭据无对应关系。
    """
    fake_key = "sk-FAKE-NOT-A-REAL-KEY-0000"
    body = f'{{"code":"InvalidApiKey","message":"key {fake_key} is invalid"}}'
    for status in (400, 401, 429, 500):
        message = str(classify_http(status, body))
        assert fake_key not in message


def test_rule_059_recoverable_flag_is_the_retry_policy() -> None:
    """分层即策略：只有 RecoverableError 可重试，其余一律不可。"""
    assert TranscriptError.recoverable is False
    assert FatalError.recoverable is False
    assert RecoverableError.recoverable is True
    assert InputError.recoverable is False  # 输入问题继承 FatalError
    assert UpstreamError.recoverable is False
    assert issubclass(InputError, FatalError)
    assert issubclass(UpstreamError, FatalError)
    assert issubclass(FatalError, TranscriptError)
    assert issubclass(RecoverableError, TranscriptError)
    assert not issubclass(RecoverableError, FatalError)


def test_rule_059_upstream_error_status_and_code_are_keyword_only_and_optional() -> None:
    err = UpstreamError("上游拒绝请求")
    assert err.status is None
    assert err.code is None
    assert isinstance(err, FatalError)
    with pytest.raises(TypeError):
        UpstreamError("m", 400)  # type: ignore[misc]  # 位置传入必须被拒绝
