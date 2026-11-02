"""错误分类：决定"能不能重试"，而不是"怎么描述失败"。

只有可恢复错误才重试；参数、格式、额度类错误必须直接暴露给用户。

`RecoverableError` / `FatalError` 的分层**就是**重试策略（`RULE-059`），
不是描述性标签 —— 重写时把它当成标签会破坏整条编排的重试语义。

零 I/O、零第三方依赖：本模块除 `__future__` 外无 import。
重建自 `legacy/transcript/src/transcript/errors.py`。
"""

from __future__ import annotations


class TranscriptError(Exception):
    """所有本工具错误的基类。"""

    recoverable = False


class FatalError(TranscriptError):
    """不可恢复：配置错误、文件损坏、参数非法、额度不足。重试只会浪费时间和钱。"""

    recoverable = False


class RecoverableError(TranscriptError):
    """可恢复：网络抖动、超时、上游 5xx/429。指数退避后重试。"""

    recoverable = True


class InputError(FatalError):
    """输入文件问题：不存在、无音轨、空音频、转码失败。"""


class UpstreamError(FatalError):
    """上游返回的错误，已带上足够定位信息（错误码 + 消息，不含密钥）。

    消息里**永不**包含凭据（NFR-4）：本类只搬运调用方给的文本，调用方负责不含密钥。
    """

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        self.status = status
        self.code = code
        super().__init__(message)


def classify_http(status: int, body: str = "") -> TranscriptError:
    """把 HTTP 状态映射成可重试/不可重试，并保留原始状态与上游错误码。

    可重试（返回 `RecoverableError`）：408 / 409 / 425 / 429，以及任何 `status >= 500`。
    其余（400 / 401 / 403 等）一律返回致命的 `UpstreamError`，**永不重试**。

    上游错误码从原始 body 里扫 `"code":"` 或 `"code": ` 得出；body 不是 JSON
    也能给出可用消息，只是没有 code。

    **返回**异常实例而不 raise —— legacy 的三个调用点（`dashscope.py:146`、
    `openrouter.py:87`、`bcut.py:88`）都写 `raise classify_http(...)`，保持一致。
    """
    code = None
    for marker in ('"code":"', '"code": "'):
        if marker in body:
            code = body.split(marker, 1)[1].split('"', 1)[0]
            break

    if status in (408, 409, 425, 429) or status >= 500:
        return RecoverableError(f"上游暂时不可用（HTTP {status}{f' {code}' if code else ''}）")
    return UpstreamError(
        f"上游拒绝请求（HTTP {status}{f' {code}' if code else ''}）", status=status, code=code
    )


# ── 重试预算（`NFR-11`）────────────────────────────────────────────────────
# 这两个数字是 legacy `config.py:105-106` 的默认值（`max_attempts = 3`,
# `backoff_base = 1.0`），在重建版里**不再可配置**：它们是「分片是唯一重试
# 单位」这条硬规则的常数，不是用户可调项。Phase 5 落地 orchestrate 时若确实
# 需要可调，再把它们搬进 `config`，而不是在这里加参数。
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 1.0


def is_recoverable(error: BaseException) -> bool:
    """这个错误该不该重试 —— 读的是错误的**类型**，不是消息文本。

    `RecoverableError` 与 `FatalError` 的分层**就是**重试策略本身（见本模块
    顶部）：参数、格式、额度类错误重试只会浪费时间与钱。
    """
    return isinstance(error, TranscriptError) and error.recoverable


def retry_delay_s(attempt: int) -> float:
    """第 `attempt` 次重试前等多久（从 1 开始计），指数退避。

    `attempt` 超出 `MAX_ATTEMPTS` 抛 `ValueError`，而不是无限退避 ——
    调用方应当先问 `MAX_ATTEMPTS` 再决定要不要重试。
    """
    if attempt < 1 or attempt > MAX_ATTEMPTS:
        raise ValueError(f"重试次数越界：attempt={attempt}（允许 1..{MAX_ATTEMPTS}）")
    return BACKOFF_BASE_S * (2 ** (attempt - 1))
