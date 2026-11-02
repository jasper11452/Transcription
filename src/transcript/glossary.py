"""热词词表与转写后的确定性替换。

两种写法都收：
- 裸词：一行一个正确写法（如 `小新`）。不强制替换，只作为热词交给引擎与 Agent 总结；
- 对应关系：`错词 -> 正确词`，转写后做确定性替换。

三条路都做（spec 7.5）：
1. **传参**：引擎支持热词/prompt 时直接传，提高识别率（离线的 Qwen3-ASR 支持 hotwords）；
2. **替换**：转写后按词表做确定性替换，替换前把"将要改动的项"列出来给人看；
3. **提示**：Agent 总结时把热词写进系统提示，同音/形近错字在总结里统一成正确写法。

动机是本机真实踩过的坑：ASR 把公司名写成音近错字（艾麦/佳路/集成），
而专有名词无法从音频自证 —— 只能靠词表。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SEPARATORS = ("->", "=>", "→", "=", "\t", "|")


@dataclass(frozen=True)
class Rule:
    wrong: str
    right: str


@dataclass(frozen=True)
class GlossaryIssue:
    line: int
    message: str

    def describe(self) -> str:
        return f"第 {self.line} 行：{self.message}"


@dataclass(frozen=True)
class Change:
    wrong: str
    right: str
    count: int

    def describe(self) -> str:
        return f"{self.wrong}→{self.right} ×{self.count}"


@dataclass(frozen=True)
class HotWordGroup:
    """热词分组；`name` 为空表示没有写分组标题的旧词条。"""

    name: str
    words: tuple[str, ...]


def _strip_inline_comment(line: str) -> str:
    """去掉行内注释（`错词 -> 正确词   # 说明`）。

    只认前面有空白或位于行首的 `#`，避免误伤词条里合法的 `#`。
    """
    for i, ch in enumerate(line):
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def split_entries(text: str) -> list[tuple[int, str, str | None]]:
    """按行切分词表：返回 (行号, 左边, 右边)。右边为 None 表示裸热词。"""
    entries: list[tuple[int, str, str | None]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_inline_comment(raw_line).strip()
        if not line or line.startswith("#"):
            continue
        separator = next((sep for sep in _SEPARATORS if sep in line), None)
        if separator is None:
            entries.append((line_number, line, None))
            continue
        wrong, _, right = line.partition(separator)
        entries.append((line_number, wrong.strip(), right.strip()))
    return entries


def is_hot_word_line(raw_line: str) -> bool:
    """裸热词行：既不是注释/空行，也不含任何“错词 -> 正确词”分隔符。"""
    line = _strip_inline_comment(raw_line).strip()
    if not line or line.startswith("#"):
        return False
    return not any(sep in line for sep in _SEPARATORS)


def parse_hot_words(text: str) -> list[str]:
    """裸热词：只给正确写法，不做替换，交给引擎热词与 Agent 总结提示。"""
    words: list[str] = []
    for _, left, right in split_entries(text):
        if right is None and left not in words:
            words.append(left)
    return words


def is_hot_word_group_line(raw_line: str) -> bool:
    """`## 组名` 是热词分组标题；普通 `#` 注释不参与分组。"""
    stripped = raw_line.strip()
    if not stripped.startswith("##"):
        return False
    body = stripped[2:]
    if not body or body[0] not in " \t":
        return False
    return bool(_strip_inline_comment(body).strip())


def parse_hot_word_groups(text: str) -> list[HotWordGroup]:
    """按 `## 组名` 切分裸热词；没有标题的旧词条归入空名分组。

    分组只影响展示与编辑，`hot_word_list` 仍然把所有裸热词扁平化交给引擎。
    只有标题没有词条的分组也会返回，方便设置页保留刚建的空组。
    """
    order: list[str] = []
    grouped: dict[str, list[str]] = {}
    current = ""

    def bucket(name: str) -> list[str]:
        if name not in grouped:
            grouped[name] = []
            order.append(name)
        return grouped[name]

    for raw_line in text.splitlines():
        if is_hot_word_group_line(raw_line):
            current = _strip_inline_comment(raw_line.strip()[2:]).strip()
            bucket(current)
            continue
        if not is_hot_word_line(raw_line):
            continue
        word = _strip_inline_comment(raw_line).strip()
        words = bucket(current)
        if word not in words:
            words.append(word)

    return [HotWordGroup(name, tuple(grouped[name])) for name in order]


def load_hot_words(path: Path | str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return parse_hot_words(p.read_text(encoding="utf-8"))


def parse_glossary_report(text: str) -> tuple[list[Rule], list[GlossaryIssue]]:
    """解析词表并返回所有会被忽略的问题，供写入前阻止静默失效。

    裸热词是合法写法（不再当成“缺少分隔符”），只有真正的错行才报问题。
    """
    rules: list[Rule] = []
    issues: list[GlossaryIssue] = []
    first_lines: dict[str, int] = {}
    for line_number, wrong, right in split_entries(text):
        if right is None:
            continue  # 裸热词：合法写法，不参与替换
        if not wrong or not right:
            issues.append(GlossaryIssue(line_number, "错词和正确词都要填写"))
            continue
        if wrong == right:
            issues.append(GlossaryIssue(line_number, "错词和正确词不能相同"))
            continue
        if wrong in first_lines:
            issues.append(
                GlossaryIssue(
                    line_number,
                    f"“{wrong}”已在第 {first_lines[wrong]} 行定义",
                )
            )
            continue
        first_lines[wrong] = line_number
        rules.append(Rule(wrong, right))
    return rules, issues


def parse_glossary(text: str) -> list[Rule]:
    """解析词表：每行 `错词 -> 正确词`（也支持 => / → / = / 制表符 / |）。"""
    return parse_glossary_report(text)[0]


def dedupe_rules(rules: list[Rule]) -> list[Rule]:
    """同一错词只保留首次出现的规则（后面的不覆盖前面的，避免顺序依赖）。"""
    seen: dict[str, Rule] = {}
    for rule in rules:
        seen.setdefault(rule.wrong, rule)
    return list(seen.values())


def load_glossary(path: Path | str) -> list[Rule]:
    p = Path(path)
    if not p.exists():
        return []
    return parse_glossary(p.read_text(encoding="utf-8"))


def hotwords(
    rules: list[Rule], *, extra: list[str] | None = None, limit: int | None = None
) -> list[str]:
    """给引擎的热词列表：裸热词在最前，然后是正确写法与错词写法。"""
    words: list[str] = []
    for word in [*(extra or []), *(w for rule in rules for w in (rule.right, rule.wrong))]:
        if word and word not in words:
            words.append(word)
    return words[:limit] if limit else words


def apply_rules(text: str, rules: list[Rule]) -> tuple[str, list[Change]]:
    """确定性替换。

    - 长词优先，避免短词把长词切碎后再也匹配不上；
    - 只替换仍然存在的错词，不做任何"猜测式"改写；
    - 返回每个词表项实际改了多少处，供页面与产物注释展示。
    """
    changes: list[Change] = []
    out = text
    for rule in sorted(rules, key=lambda r: len(r.wrong), reverse=True):
        count = out.count(rule.wrong)
        if count:
            out = out.replace(rule.wrong, rule.right)
            changes.append(Change(rule.wrong, rule.right, count))
    return out, changes


def change_comment(changes: list[Change]) -> list[str]:
    """产物头部注释：保留"原文写法 → 正确写法"，原始 ASR 文本在 raw.json 里不动。"""
    if not changes:
        return []
    return ["词表替换（原始转写见 .raw.json）：" + "，".join(c.describe() for c in changes)]
