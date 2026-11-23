"""pytest 插件：让「按规则 ID 过滤」与「列出规则覆盖」成为可执行的查询。

`-m` 的表达式语法要求标记名是合法 Python 标识符，而规则 ID 形如 `RULE-025`
（带连字符），所以 `-m 'rule(RULE-025)'` 是报错的。这里补两个选项：

    pytest --rule=RULE-025            # 只跑这条规则的验收测试
    pytest --list-rules              # 列出所有标记到的规则 ID、用例数、是否 pending

`--list-rules` 是给父级编排用的证据：哪些规则已被验收测试覆盖、哪些还是 expected-failure。
"""

from __future__ import annotations

from collections import Counter, defaultdict

import pytest

RULE_MARKER = "rule"
PENDING_MARKER = "pending_implementation"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("behavior contract")
    group.addoption(
        "--rule",
        action="append",
        default=[],
        metavar="RULE-ID",
        help="只跑带 rule(RULE-ID) 标记的验收测试；可重复。例：--rule=RULE-025",
    )
    group.addoption(
        "--list-rules",
        action="store_true",
        default=False,
        help="列出被标记的规则 ID、用例数、以及是否有 pending（预期失败/跳过）用例，然后退出。",
    )


def _rule_id_of(item: pytest.Item) -> str | None:
    for mark in item.iter_markers(name=RULE_MARKER):
        if mark.args:
            return str(mark.args[0])
        if "id" in mark.kwargs:
            return str(mark.kwargs["id"])
        return None
    return None


def _pending_rule_id_of(item: pytest.Item) -> str | None:
    for mark in item.iter_markers(name=PENDING_MARKER):
        if mark.args:
            return str(mark.args[0])
        if "rule_id" in mark.kwargs:
            return str(mark.kwargs["rule_id"])
        return None
    return None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "rule(id): 绑定行为契约规则 ID 的验收测试（如 RULE-025、RULE-059）"
    )
    config.addinivalue_line(
        "markers",
        "pending_implementation(rule_id): 规则尚未实现，预期失败/跳过，必须带规则 ID",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    wanted = set(config.getoption("--rule") or ())
    if wanted:
        kept, deselected = [], []
        for item in items:
            if _rule_id_of(item) in wanted:
                kept.append(item)
            else:
                deselected.append(item)
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
        if not kept:
            raise pytest.UsageError(
                f"--rule={sorted(wanted)} 未匹配任何用例；用 --list-rules 看可用 ID"
            )


def pytest_report_collectionfinish(
    config: pytest.Config, start_path, items: list[pytest.Item]
) -> str | None:
    if not config.getoption("--list-rules"):
        return None
    total: Counter[str] = Counter()
    pending: defaultdict[str, list[str]] = defaultdict(list)
    unmarked = 0
    for item in items:
        rid = _rule_id_of(item)
        if rid is None:
            unmarked += 1
        else:
            total[rid] += 1
        pid = _pending_rule_id_of(item)
        if pid:
            pending[pid].append(item.nodeid)
    lines = ["", "行为契约规则覆盖（按 ID）:"]
    for rid in sorted(total):
        tail = f"  ⚠ pending: {len(pending[rid])} 个用例" if pending.get(rid) else ""
        lines.append(f"  {rid}: {total[rid]} 个用例{tail}")
    for pid in sorted(set(pending) - set(total)):
        lines.append(f"  {pid}: 0 个已实现用例  ⚠ pending: {len(pending[pid])} 个用例")
    lines.append(f"  未标规则的用例: {unmarked}")
    return "\n".join(lines)
