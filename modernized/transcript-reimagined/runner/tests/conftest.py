"""runner 的 conftest —— 只把夹具从具名模块挂进来。

夹具本体在 `_fixtures.py`（测试直接 `from _fixtures import ...`，避免与
workspace 根的 `conftest.py` 在 `importlib` 模式下同名冲突）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from _fixtures import *  # noqa: F403,E402
