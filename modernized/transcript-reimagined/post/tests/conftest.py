"""测试的公共夹具与 pytest 选项。

三件事：

1. 把 ``src/`` 放进 ``sys.path``，使测试**不需要先安装包**即可运行（试点要求可复现）；
2. 补两个按规则 ID 过滤 / 清点的选项 —— ``-m`` 的表达式语法要求标记名是合法
   Python 标识符，而规则 ID 形如 ``RULE-060``（带连字符），所以 ``-m 'rule(RULE-060)'``
   是报错的：

       pytest --rule=RULE-060     # 只跑这条规则的验收测试
       pytest --list-rules        # 列出被标记的规则 ID、用例数、是否有 pending

3. 声明 ``rule(id)`` 与 ``pending_implementation(rule_id)`` 两个标记，让
   「每条规则被哪些用例覆盖」「哪些还是预期失败」变成可清点的事实，而不是靠读文件名。

夹具里**没有**任何来自 legacy 的凭据、真实路径或真实录音：本服务的输入是
文本、时间戳与词表原文，测试数据全部是假名与浮点数。若以后要加真实音频夹具，
用 ``say`` 生成的样例，不用私有素材。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

RULE_MARKER = "rule"
PENDING_MARKER = "pending_implementation"
