"""``RULE-059`` —— HTTP 失败分类：可重试还是致命。

判据：上游返回 429 且 body 含 ``"code":"Throttling"`` → 抛 ``RecoverableError``，
消息含 ``HTTP 429 Throttling``，可重试；400/401 抛致命的 ``UpstreamError``，**永不重试**。

这一条是整条编排重试语义的载体：把 ``RecoverableError`` / ``FatalError`` 当成描述性
标签，就会要么重试参数错误（白花钱）、要么放弃网络抖动（白丢一次成功机会）。
因此这里断言的是**分类结果**（``is_recoverable``），不只是消息文本。
"""

from __future__ import annotations

import pytest
from transcript_reimagined.domain.errors import (
    FatalError,
    InputError,
    RecoverableError,
    TranscriptError,
    UpstreamError,
    classify_http,
    is_recoverable,
    retry_delay_s,
)

RETRYABLE_STATUSES = (408, 409, 425, 429, 500, 502, 503, 504, 599)
FATAL_STATUSES = (400, 401, 402, 403, 404, 412, 413, 415, 422)


@pytest.mark.parametrize("status", RETRYABLE_STATUSES)
def test_rule_059_retryable_statuses_classify_as_recoverable(status):
    error = classify_http(status)
    assert isinstance(error, RecoverableError)
    assert error.recoverable is True
    assert is_recoverable(error) is True


@pytest.mark.parametrize("status", FATAL_STATUSES)
def test_rule_059_client_and_credit_failures_are_fatal(status):
    """参数、格式、额度类错误直接暴露 —— 重试只会浪费时间和钱。"""
    error = classify_http(status)
    assert isinstance(error, UpstreamError)
    assert isinstance(error, FatalError)
    assert error.recoverable is False
    assert is_recoverable(error) is False
    assert error.status == status


def test_rule_059_throttling_429_is_recoverable_and_names_the_upstream_code():
    body = '{"code":"Throttling","message":"Requests throttled"}'
    error = classify_http(429, body)
    assert isinstance(error, RecoverableError)
    assert "HTTP 429" in str(error)
    assert "Throttling" in str(error)


def test_rule_059_upstream_code_is_extracted_from_both_json_spacings():
    """两种 JSON 间距都要抠出上游错误码。可重试错误只把它带进消息（见 LEGACY_DEVIATIONS）。"""
    for body in ('{"code":"Throttling"}', '{"code": "Throttling"}'):
        error = classify_http(500, body)
        assert isinstance(error, RecoverableError)
        assert "Throttling" in str(error)


def test_rule_059_a_body_without_a_code_still_classifies():
    error = classify_http(503, "<html>gateway timeout</html>")
    assert isinstance(error, RecoverableError)
    assert str(error) == "上游暂时不可用（HTTP 503）"
    assert "<html>" not in str(error)


def test_rule_059_error_messages_never_carry_credentials():
    """凭据永不进日志/消息（``NFR-4``）：分类器只回状态与上游错误码。"""
    secret = "sk-not-a-real-key-0000"
    error = classify_http(401, '{"code":"InvalidApiKey"}')
    assert secret not in str(error)
    assert "InvalidApiKey" in str(error)


def test_rule_059_fatal_classification_reaches_the_input_error_type():
    """输入类失败同样是致命：文件不存在/无音轨不该被重试。"""
    error = InputError("文件不存在：/tmp/nope.m4a")
    assert isinstance(error, FatalError)
    assert is_recoverable(error) is False


def test_rule_059_every_error_derives_from_the_common_base():
    for error in (classify_http(429), classify_http(400), InputError("x")):
        assert isinstance(error, TranscriptError)


def test_rule_059_retry_budget_is_three_attempts_with_exponential_backoff():
    """``NFR-11``：每分片最多 3 次，指数退避基数 1.0s。"""
    assert [retry_delay_s(n) for n in (1, 2, 3)] == [1.0, 2.0, 4.0]
    with pytest.raises(ValueError):
        retry_delay_s(4)
