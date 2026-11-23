"""把各成员的 `src/` 放进 `sys.path`，让它们在**不安装**的前提下互相可导入。

`transcript_reimagined` 是 PEP 420 命名空间包：每个成员的
`src/transcript_reimagined/` 片段在这些路径上**合并**成同一个顶层包。没有这一步，
从 workspace 根跑 `pytest` 时跨成员导入会失败，而逐个成员跑又各自正常 —— 那种
「单跑绿、合跑红」正是脚手架阶段被结构逼出 736 行复制的原因。

不用 `[tool.pytest.ini_options] pythonpath`：它相对 rootdir 解析，而 rootdir
在「成员各自声明配置」时会被抢走，注入会静默失效。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBER_SRC = [
    ROOT / m / "src"
    for m in (
        "domain",
        "config",
        "state",
        "ingest",
        "post",
        "diar",
        "engines",
        "summarize",
        "orchestrate",
        "web",
        "runner",
    )
]

for _src in reversed([p for p in MEMBER_SRC if p.is_dir()]):
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
