"""测试的公共夹具与 pytest 选项。

两件事：

1. 把 ``src/`` 放进 ``sys.path``，使测试**不需要先安装包**即可运行（试点要求可复现）；
2. 补两个按规则 ID 过滤 / 清点的选项 —— ``-m`` 的表达式语法要求标记名是合法
   Python 标识符，而规则 ID 形如 ``RULE-011``（带连字符），所以 ``-m 'rule(RULE-011)'``
   是报错的。

       pytest --rule=RULE-011     # 只跑这条规则的验收测试
       pytest --list-rules       # 列出被标记的规则 ID、用例数、是否 pending

``--list-rules`` 是给父级编排用的证据：哪些规则已被验收测试覆盖、哪些还是
expected-failure。

夹具里**没有**任何来自 legacy 的凭据、路径或真实录音：切片规划是纯函数，
输入就是浮点数。若以后要加真实音频夹具，用 ``say`` 生成的样例，不用私有素材。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = Path(__file__).resolve().parents[2]

#: `transcript_reimagined` 是 PEP 420 命名空间包：`domain` 由并行脚手架的另一个
#: 服务贡献，`ingest` 由本服务贡献。把两个 `src/` 都放进 `sys.path`，命名空间
#: 片段才会**合并**成同一个顶层包。
#:
#: 注意这里**没有**引入遗留包（本仓 `.venv` 里装着 `transcript`）：等价性对比由
#: `test_equivalence_with_legacy_chunking.py` 显式按文件路径加载，不走导入系统
#: —— 否则「等价」会变成自己跟自己比。
SOURCE_ROOTS = [p for p in (ROOT / "src", SIBLINGS / "domain" / "src") if p.is_dir()]
for source_root in reversed(SOURCE_ROOTS):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

RULE_MARKER = "rule"
PENDING_MARKER = "pending_implementation"
