"""错误分类：决定"能不能重试"，而不是"怎么描述失败"。

只有可恢复错误才重试；参数、格式、额度类错误必须直接暴露给用户。
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
    """上游返回的错误，已带上足够定位信息（错误码 + 消息，不含密钥）。"""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        self.status = status
        self.code = code
        super().__init__(message)


def classify_http(status: int, body: str = "") -> TranscriptError:
    """把 HTTP 状态映射成可重试/不可重试，并保留原始状态与上游错误码。"""
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
