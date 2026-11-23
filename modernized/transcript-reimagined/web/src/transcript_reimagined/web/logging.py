"""结构化日志：每次失败都能用 `request_id` / `task_id` / `code` 对上。

旧 `src/` 里 `import logging` 命中数为 0，失败只有一行插值后的异常文本；
重建版用 stdlib logging + 一个带上下文字段的 formatter，不引第三方日志库。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
task_id_var: ContextVar[str] = ContextVar("task_id", default="-")

_LOGGER_NAME = "transcript"


class _ContextFormatter(logging.Formatter):
    """把 request/task/code 三个字段并入格式化输出；缺失时用上下文默认值。"""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = getattr(record, "request_id", request_id_var.get())
        record.task_id = getattr(record, "task_id", task_id_var.get())
        record.code = getattr(record, "code", "-")
        return super().format(record)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """配置一次根 handler；重复调用幂等。"""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            _ContextFormatter(
                "%(asctime)s %(levelname)s %(message)s "
                "request_id=%(request_id)s task_id=%(task_id)s code=%(code)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def log_failure(
    message: str,
    *,
    code: str,
    task_id: int | str | None = None,
    level: int = logging.WARNING,
) -> None:
    """记录一次失败：消息是给人看的，`code` 是给机器对账的。"""
    get_logger().log(
        level,
        message,
        extra={"code": code, "task_id": "-" if task_id is None else str(task_id)},
    )
