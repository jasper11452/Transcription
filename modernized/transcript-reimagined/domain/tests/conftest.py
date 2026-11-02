"""domain 的测试夹具（规则过滤插件在 workspace 根注册，见根 conftest.py）。

夹具里没有任何来路不明的数据：本服务只处理浮点数与字符串。
"""

from __future__ import annotations

RULE_MARKER = "rule"
PENDING_MARKER = "pending_implementation"
