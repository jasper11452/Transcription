"""post 在函数签名与产物契约里消费的领域词汇 —— **从 `domain` 包 re-export**。

原先本文件是一份并行声明（Word / Segment / GlossaryRule / GlossaryIssue /
Change / fmt_timestamp 六份重定义）。在四个服务已合并到同一个命名空间、
且 `domain` 包的接口已定稿之后，那份声明成了**同一个进程里同一概念的两个类对象**
—— `isinstance` 在跨包传值时静默失效。这正是架构评审 M2/M3 要防的那类问题。

现在只保留 re-export，让 post 的既有 import 路径（`.domain`）继续可用，
而类型的**唯一来源**是 `transcript_reimagined.domain`。

`GlossaryRule` 在 `domain` 里的名字是 `Rule` —— 这里给一个别名而不是改名，
因为 `Rule` 背后是「错词→正确词」这件事的公共词汇，不带 `Glossary` 前缀更准确。
"""

from __future__ import annotations

from transcript_reimagined.domain import (
    Change,
    Issue as GlossaryIssue,
    Rule as GlossaryRule,
    Segment,
    Word,
    fmt_timestamp,
)

__all__ = [
    "Change",
    "GlossaryIssue",
    "GlossaryRule",
    "Segment",
    "Word",
    "fmt_timestamp",
]
