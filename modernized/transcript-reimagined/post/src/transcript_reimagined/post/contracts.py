"""HTTP 边界契约的**形状**（由 `web` 层拥有，post 提供纯变换）。

`REIMAGINED_ARCHITECTURE.md` §2：`web/` **只做传输** —— 路由 + 请求校验 + SSE 转发。
但词表与产物预览这两处的**语义**住在 post：词表语法（`RULE-060`）与产物正文上限。
因此 post 暴露可被 web 直接调用的纯函数，而不是让 web 自己再实现一遍契约
（同一条契约两处实现正是 v1 评审要消灭的问题）。

对应的接口契约（`AI_NATIVE_SPEC.md` §3.1）：
- `GET /api/glossary` → `{text, rules[{wrong,right}]}`
- `PUT /api/glossary` → `{rule_count}`；400 带逐行问题；错误契约统一 `{"error": "<message>"}`
- `GET /api/tasks/{id}/output?kind=txt|srt` → `{content, path, truncated}`
- 产物落盘后的路径集合（orchestrate 决定写不写，web 只回路径）

本模块**不引 FastAPI / Pydantic**：那是 web 层的依赖，post 不碰传输框架。
这里的返回对象是普通 dataclass，web 负责序列化。落盘与读取路径由调用方给出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .domain import GlossaryIssue
from .glossary import parse_glossary, parse_glossary_report

# 产物正文 JSON 预览上限（NFR-8：200 000 字符；超过要明确告诉调用方被截断）。
MAX_OUTPUT_PREVIEW_CHARS = 200_000
# `kind` 允许值（`AI_NATIVE_SPEC.md` §3.1）。
OUTPUT_KINDS = ("txt", "srt")


@dataclass(frozen=True)
class GlossaryRuleView:
    wrong: str
    right: str


@dataclass(frozen=True)
class GlossaryResponse:
    """`GET /api/glossary` 的响应体。"""

    text: str
    rules: list[GlossaryRuleView] = field(default_factory=list)


@dataclass(frozen=True)
class GlossaryValidation:
    """`PUT /api/glossary` 的校验结果。

    `issues` 非空 → 路由返回 400，`error` 用 `describe()` 的逐行文本拼起来；
    校验通过 → 返回 `{rule_count}`，随后由 config 层做原子写（0600，Phase 2）。
    """

    rule_count: int
    issues: list[GlossaryIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def error_message(self) -> str:
        """统一错误契约 `{"error": "<message>"}` 里的 message。"""
        return "；".join(issue.describe() for issue in self.issues)


@dataclass(frozen=True)
class OutputPreview:
    """`GET /api/tasks/{id}/output` 的响应体。"""

    content: str
    path: str
    truncated: bool


def artifact_paths(out_dir: Path | str, stem: str) -> dict[str, Path]:
    """三个产物的路径集合（`orchestrate` 决定写不写；这是它回报给 web 的形状）。

    `AI_NATIVE_SPEC.md` §3.1 的 `result` 事件与 `GET /api/tasks/{id}/output` 都按
    `{txt_path, srt_path, raw_path}` 报路径 —— 这里给出唯一一份构造，避免调用点各写一遍。
    """
    out = Path(out_dir)
    return {
        "txt_path": out / f"{stem}.txt",
        "srt_path": out / f"{stem}.srt",
        "raw_path": out / f"{stem}.raw.json",
    }


def glossary_response(text: str) -> GlossaryResponse:
    """把词表原文解析成 `GET /api/glossary` 的响应。

    解析不出规则的错行在这里被静默忽略（读取路径不报错）—— 报错发生在写入路径
    `validate_glossary`；这与 legacy 的读写不对称一致。
    """
    rules = [GlossaryRuleView(r.wrong, r.right) for r in parse_glossary(text)]
    return GlossaryResponse(text=text, rules=rules)


def validate_glossary(text: str) -> GlossaryValidation:
    """`PUT /api/glossary` 的写入前校验（`RULE-060`）：有任何错行就整份拒绝。"""
    rules, issues = parse_glossary_report(text)
    return GlossaryValidation(rule_count=len(rules), issues=issues)


def output_preview(content: str, path: Path | str, *, kind: str) -> OutputPreview:
    """按 `kind` 截断产物正文用于 JSON 预览（上限 200 000 字符）。

    `truncated` 明确告诉调用方截断发生过；要看全文走整文件下载接口。
    """
    if kind not in OUTPUT_KINDS:
        raise ValueError(f"kind 只能是 {' / '.join(OUTPUT_KINDS)}，收到：{kind}")
    truncated = len(content) > MAX_OUTPUT_PREVIEW_CHARS
    return OutputPreview(
        content=content[:MAX_OUTPUT_PREVIEW_CHARS], path=str(path), truncated=truncated
    )
