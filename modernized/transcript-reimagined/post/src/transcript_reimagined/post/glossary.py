"""词表：语法与校验 · 热词组成与上限 · 确定性替换与计数 · 替换留痕。

承载的规则（`AI_NATIVE_SPEC.md` §5.2）：
- `RULE-060` 词表语法与条目校验（`split_entries` `parse_glossary_report` `parse_glossary`）
- `RULE-021` 热词列表组成与上限（`hotwords` `cap_hot_words_for_summary`）
- `RULE-022` 替换顺序与变更计数（`apply_rules`）
- `RULE-132` 替换痕迹写进产物（`change_comment` `change_header_line`，落盘见 `products.py`）

本模块是纯函数：不读文件、不写文件、不碰网络。路径读取（`config` 的地盘）与
落盘（`orchestrate` 的单点决策）都不在这里 —— 见 `REIMAGINED_ARCHITECTURE.md` §2。
"""

from __future__ import annotations

from pathlib import Path

from .domain import Change, GlossaryIssue, GlossaryRule

# 分隔符按序尝试，先匹配到的赢（`RULE-060`）。
SEPARATORS: tuple[str, ...] = ("->", "=>", "→", "=", "\t", "|")

# 给总结用的上限（`RULE-021`；NFR-8：热词 ≤80 词 × ≤40 字符 —— 实现时不得放宽）。
SUMMARY_MAX_HOT_WORDS = 80
SUMMARY_MAX_HOT_WORD_CHARS = 40


def _strip_inline_comment(line: str) -> str:
    """去掉行内注释：只认行首或前面有空白（含制表符）的 `#`。

    词条内部紧贴字符的 `#` 属于词条本身（`RULE-060` 的边界情形）。
    """
    for i, ch in enumerate(line):
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def split_entries(text: str) -> list[tuple[int, str, str | None]]:
    """按行切分词表：返回 `(行号, 左边, 右边)`；右边为 `None` 表示裸热词。

    空行与注释行跳过（`RULE-060`）。行号从 1 起，供报错定位。
    """
    entries: list[tuple[int, str, str | None]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_inline_comment(raw_line).strip()
        if not line or line.startswith("#"):
            continue
        separator = next((sep for sep in SEPARATORS if sep in line), None)
        if separator is None:
            entries.append((line_number, line, None))
            continue
        wrong, _, right = line.partition(separator)
        entries.append((line_number, wrong.strip(), right.strip()))
    return entries


def is_hot_word_line(raw_line: str) -> bool:
    """裸热词行：既不是注释/空行，也不含任何「错词 -> 正确词」分隔符。"""
    line = _strip_inline_comment(raw_line).strip()
    if not line or line.startswith("#"):
        return False
    return not any(sep in line for sep in SEPARATORS)


def parse_hot_words(text: str) -> list[str]:
    """裸热词：只给正确写法，不做替换；去重保首次出现顺序。"""
    words: list[str] = []
    for _, left, right in split_entries(text):
        if right is None and left not in words:
            words.append(left)
    return words


def parse_glossary_report(text: str) -> tuple[list[GlossaryRule], list[GlossaryIssue]]:
    """解析词表并返回所有会被忽略的问题，供写入前阻止静默失效。

    规则（`RULE-060`）：
    - 裸热词是合法写法，不报问题、不参与替换；
    - 缺一边（`-> 集诚`）报「错词和正确词都要填写」；
    - 两边相同（`集诚 = 集诚`）报「错词和正确词不能相同」；
    - 重复错词报「…已在第 N 行定义」，且**首次定义生效**（后面的不覆盖前面的）。

    已知的判定顺序（保留 legacy 语义，见 `RULE-060` 的 `Parameters`）：缺边与同词
    的检查先于重复检查，因此「第 6 行的 `艾麦 => 艾麦科技`」报的是与第 2 行重复，
    而不是与 5 行前那次定义重复。改这个优先级属于行为变更，需先回规格。
    """
    rules: list[GlossaryRule] = []
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
                GlossaryIssue(line_number, f"“{wrong}”已在第 {first_lines[wrong]} 行定义")
            )
            continue
        first_lines[wrong] = line_number
        rules.append(GlossaryRule(wrong, right))
    return rules, issues


def parse_glossary(text: str) -> list[GlossaryRule]:
    """解析词表并丢弃问题清单（写入/校验路径请用 `parse_glossary_report`）。"""
    return parse_glossary_report(text)[0]


def dedupe_rules(rules: list[GlossaryRule]) -> list[GlossaryRule]:
    """同一错词只保留首次出现的规则（后面的不覆盖前面的，避免顺序依赖）。"""
    seen: dict[str, GlossaryRule] = {}
    for rule in rules:
        seen.setdefault(rule.wrong, rule)
    return list(seen.values())


def hotwords(
    rules: list[GlossaryRule], *, extra: list[str] | None = None, limit: int | None = None
) -> list[str]:
    """引擎热词列表（`RULE-021`）：裸热词在最前，随后每条规则的**正确写法在前、错词在后**。

    去重保首次出现顺序；`limit` 从尾部截断（`None` 表示不截）。

    注意：`extra` 是裸热词注入通道 —— legacy 的调用点是
    `hotwords(rules, extra=load_hot_words(path))`（`pipeline.py:432`），
    裸词与规则都在这一张列表里。
    """
    words: list[str] = []
    for word in [*(extra or []), *(w for rule in rules for w in (rule.right, rule.wrong))]:
        if word and word not in words:
            words.append(word)
    return words[:limit] if limit else words


def cap_hot_words_for_summary(words: list[str]) -> list[str]:
    """总结用的热词：每词截到 40 字符、最多 80 词（`RULE-021`、NFR-8）。

    截断与「静默丢弃第 51 个词」都是 legacy 的既有行为，按规格保留。
    """
    return [word[:SUMMARY_MAX_HOT_WORD_CHARS] for word in words if word.strip()][
        :SUMMARY_MAX_HOT_WORDS
    ]


def load_glossary(path: str | Path) -> list[GlossaryRule]:
    """从文件读词表；文件不存在返回空列表（不报错）—— 与 legacy 一致。

    `RULE-060` 的边界：缺失文件不是错误，用户不写词表是正常用法。
    """
    p = Path(path)
    if not p.exists():
        return []
    return parse_glossary(p.read_text(encoding="utf-8"))


def load_hot_words(path: str | Path) -> list[str]:
    """只读词表里的**裸热词**（不含规则的正确写法）。

    与 `load_glossary` 分开：裸词是给引擎的提示词，规则是确定性替换；
    `hotwords()` 负责把两者拼成最终列表（RULE-021）。
    """
    p = Path(path)
    if not p.exists():
        return []
    return parse_hot_words(p.read_text(encoding="utf-8"))


def apply_rules(text: str, rules: list[GlossaryRule]) -> tuple[str, list[Change]]:
    """确定性替换（`RULE-022`）。

    - 错词长度降序排序：长词先替，避免短词把长词切碎后再也匹配不上；
    - 替换是普通 `str.replace`，一次替换掉全部出现处；
    - 只记录实际发生替换的项，`count` 是**实际替换处数**；
    - 同一文本绝不重复套用同一规则。

    计数权威：只有针对**整段合并文本**的这一次调用计入产物（`RULE-132` 的注释与
    `.raw.json`）；逐段落各自的替换调用不产生对外计数。
    """
    changes: list[Change] = []
    out = text
    for rule in sorted(rules, key=lambda r: len(r.wrong), reverse=True):
        count = out.count(rule.wrong)
        if count:
            out = out.replace(rule.wrong, rule.right)
            changes.append(Change(rule.wrong, rule.right, count))
    return out, changes


def change_header_line(changes: list[Change]) -> str:
    """产物头部的替换留痕行（`RULE-132`）：

    `词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3`

    多条变更用「，」连接；无变更时返回空串。
    """
    if not changes:
        return ""
    return "词表替换（原始转写见 .raw.json）：" + "，".join(c.describe() for c in changes)


def change_comment(changes: list[Change]) -> list[str]:
    """`render.to_txt` / `render.to_srt` 的 `comment_lines` 入参：无变更时为空列表。

    渲染层负责加 `#` 前缀（`RULE-132`：`.txt` 与 `.srt` 都以注释块开头）。
    """
    line = change_header_line(changes)
    return [line] if line else []

# legacy 的名字（`summary.py:24-25`）—— 规则卡 RULE-021 与人裁定都按这两个
# 旧名引用它们，保留同义词，避免「等价性测试按旧名写、实现按新名写」的错位。
MAX_HOT_WORDS = SUMMARY_MAX_HOT_WORDS
MAX_HOT_WORD_CHARS = SUMMARY_MAX_HOT_WORD_CHARS
