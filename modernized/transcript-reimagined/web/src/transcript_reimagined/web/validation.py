"""请求校验：纯函数，不依赖 FastAPI，错误消息可直接作为 400 的正文。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from transcript_reimagined.engines import ONLINE_ENGINES
from transcript_reimagined.summarize import MAX_HOT_WORD_CHARS, MAX_HOT_WORDS, MAX_PROMPT_CHARS

SUMMARY_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}")
MAX_CREDENTIAL_CHARS = 512


def validate_task_request(*, mode: str, artifact: str, online_engine: str) -> None:
    """提交任务前的输入校验（RULE-063）。消息里带上字段名，前端可直接展示。"""
    if mode not in ("offline", "online"):
        raise ValueError(f"mode 只能是 offline / online，收到：{mode}")
    if artifact not in ("txt", "srt"):
        raise ValueError(f"artifact 只能是 txt / srt，收到：{artifact}")
    if online_engine not in ONLINE_ENGINES:
        raise ValueError(
            f"online_engine 只能是 {', '.join(ONLINE_ENGINES)}，收到：{online_engine}"
        )


def validate_credential_value(attr: str, value: str) -> str:
    """凭据值：去空白；空值返回空串由路由层决定「保留」；非法值直接报错。"""
    clean = (value or "").strip()
    if not clean:
        return ""
    if (
        len(clean) > MAX_CREDENTIAL_CHARS
        or any(ch.isspace() or ord(ch) < 0x20 for ch in clean)
        or "=" in clean
    ):
        raise ValueError(f"{attr} 的值含有非法字符（空格、换行、控制字符或 =）")
    return clean


def validate_base_url(value: str) -> str:
    """Base URL：HTTP(S)、无凭据、无查询/片段、端口合法。"""
    if not isinstance(value, str):
        raise ValueError("Base URL 必须是字符串")
    base_url = value.strip().rstrip("/")
    if any(ch.isspace() for ch in base_url) or len(base_url) > 500:
        raise ValueError("Base URL 格式无效")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Base URL 格式无效") from exc
    valid = (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and (port is None or 1 <= port <= 65535)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise ValueError("Base URL 必须是无凭据、无查询参数的 HTTP(S) 地址")
    return base_url


def parse_hot_words(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_HOT_WORDS:
        raise ValueError(f"热词必须是最多 {MAX_HOT_WORDS} 个的列表")
    cleaned: list[str] = []
    for word in value:
        if not isinstance(word, str):
            raise ValueError("热词必须是字符串")
        word = word.strip()
        if not word:
            continue
        if (
            len(word) > MAX_HOT_WORD_CHARS
            or any(ch.isspace() for ch in word)
            or "=" in word
        ):
            raise ValueError(
                f"热词“{word}”无效：不能含空白或 =，最多 {MAX_HOT_WORD_CHARS} 字"
            )
        if word not in cleaned:
            cleaned.append(word)
    return cleaned


@dataclass(frozen=True)
class SummarySettings:
    model: str
    base_url: str
    prompt: str
    hot_words: list[str] | None
    api_key: str


def parse_summary_settings(body: object) -> SummarySettings:
    """`PUT /api/summary-settings` 的校验（RULE-039 / RULE-065 / RULE-066）。"""
    required = {"model", "base_url", "prompt"}
    allowed = required | {"hot_words", "api_key"}
    if not isinstance(body, dict) or not required <= set(body) or set(body) - allowed:
        raise ValueError("需要提供 model、base_url、prompt，可选 hot_words、api_key")

    model = body["model"]
    if not isinstance(model, str):
        raise ValueError("模型 ID 必须是字符串")
    model = model.strip()
    if not SUMMARY_MODEL_RE.fullmatch(model):
        raise ValueError("模型 ID 格式无效，请填写服务提供的模型 ID（不含空白）")

    base_url = validate_base_url(body["base_url"])

    prompt = body["prompt"]
    if not isinstance(prompt, str):
        raise ValueError("提示词必须是字符串")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"提示词不能超过 {MAX_PROMPT_CHARS} 个字符")
    if "\x00" in prompt:
        raise ValueError("提示词包含不支持的空字符")

    api_key = body.get("api_key", "")
    if not isinstance(api_key, str):
        raise ValueError("API Key 必须是字符串")
    api_key = validate_credential_value("OPENROUTER_API_KEY", api_key)

    hot_words = body.get("hot_words")
    cleaned_hot = None if hot_words is None else parse_hot_words(hot_words)

    return SummarySettings(
        model=model,
        base_url=base_url,
        prompt=prompt,
        hot_words=cleaned_hot,
        api_key=api_key,
    )
