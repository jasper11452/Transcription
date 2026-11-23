"""Phase 1 纵向切片的入口：音频元数据 JSON → 分片规划 → 词表替换 → 渲染 → 真实落盘。

它存在的唯一目的是验证「重写一个模块的标准动作」：真实文件 I/O + 真实跨包 import。
**不含 config、不含 store、不含 pipeline、不含 web** —— 那些属 Phase 2/5/6。

依赖方向：``runner → {ingest, post} → domain``（``pyproject.toml`` 的 lint contract 强制）。
"""

from .products import ProductPaths, write_products
from .run import RunRequest, RunResult, run

__all__ = ["ProductPaths", "RunRequest", "RunResult", "run", "write_products"]
