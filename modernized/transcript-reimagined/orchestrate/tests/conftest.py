"""orchestrate 的 conftest：把 `_fakes.py` 所在目录放进 sys.path。

`--import-mode=importlib` 下测试文件不以包的形式导入，`from orchestrate_fakes import ...`
需要目录本身在 `sys.path` 上（与 runner/tests 的做法一致）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from orchestrate_fakes import *  # noqa: F403,E402
