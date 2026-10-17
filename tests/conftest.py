"""共享测试夹具。

原则：**测试不碰用户真实数据**。
- 每个用例一个临时 SQLite（`tmp_path/state.db`），不打开 `~/Documents/Transcript/state.db`；
- 配置对象直接构造，不读 `~/.config/transcript/config.env`（那份文件里有真密钥）；
- 页面测试只读构建产物 `static/dist`，不触发 `npm run build`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript.config import Config
from transcript.store import Store


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """全默认 + 全部路径指向 tmp_path 的配置。"""
    return Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "state.db",
        output_dir=tmp_path / "output",
        glossary_path=tmp_path / "glossary.txt",
    )


@pytest.fixture
def store(config: Config) -> Store:
    return Store(config.state_db)


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    """放"原文件"的目录；产物按需在用例里写到 output_dir。"""
    path = tmp_path / "uploads"
    path.mkdir()
    return path
