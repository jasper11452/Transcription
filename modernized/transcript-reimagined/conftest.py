"""workspace 根的 conftest —— 只做两件事，且**不导出任何成员测试要用的名字**。

（成员测试会 `from conftest import ...` 取自己那份夹具；在 importlib 模式下
两份 conftest 都以 `conftest` 为模块名，所以根这份必须保持极薄，否则会遮住
成员的夹具。）

1. 把四个成员的 `src/` 放进 `sys.path` —— 见 `conftest_support.paths`。
2. 注册规则过滤插件（`--rule` / `--list-rules`）。
"""

from __future__ import annotations

from conftest_support import paths  # noqa: F401  （import 即生效）

pytest_plugins = ["conftest_support.rule_plugin"]
