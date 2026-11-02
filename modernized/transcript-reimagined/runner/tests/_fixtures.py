"""runner 的测试夹具（具名模块）。

为什么不放在 `conftest.py` 里让测试直接 `from conftest import ...`：从
workspace 根跑 `pytest` 时，根的 `conftest.py` 与成员的 `conftest.py` 在
`importlib` 模式下同名，成员测试会拿到根那份。具名模块没有这个歧义。
"""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DATA = Path(__file__).resolve().parent / "data"

#: 一次运行的基线元数据（300s、两段语音、1.2s 静音、三个段落、一个说话人切换）
BASE_METADATA: dict = {
    "task_id": 42,
    "path": "audio/2026-10-17 会议.m4a",
    "duration_s": 300.0,
    "spans": [[0.0, 60.0], [61.2, 300.0]],
    "merged_text": "我们把集成做完了。请确认艾麦的报价。",
    "segments": [
        {"start": 0.0, "end": 20.0, "text": "我们把集成做完了。请", "speaker": "speaker_1"},
        {"start": 20.0, "end": 40.0, "text": "确认艾麦的报价。", "speaker": "speaker_1"},
        {"start": 40.0, "end": 60.0, "text": "好的。", "speaker": "speaker_2"},
    ],
    "chunk": {"min_s": 30.0, "max_s": 120.0, "overlap_s": 0.5},
    "engine": "dashscope",
    "has_timestamps": True,
    "artifact": "srt",
    "mode": "online",
}

#: 同形状的**假**词表内容（公司名是假名，不来自 legacy 配置）
GLOSSARY_TEXT = "小新\n集成 -> 集诚\n艾麦 -> 集诚\n成 -> 诚\n"


def metadata_doc(**overrides) -> dict:
    """基线元数据的深拷贝，可覆盖任意字段。"""
    doc = copy.deepcopy(BASE_METADATA)
    doc.update(overrides)
    return doc


def metadata_json(**overrides) -> str:
    return json.dumps(metadata_doc(**overrides), ensure_ascii=False)


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """每个用例一个真实临时输出目录。"""
    target = tmp_path / "out"
    target.mkdir()
    return target


@pytest.fixture
def glossary_file(tmp_path: Path) -> Path:
    """真实写盘的同形状假词表。"""
    path = tmp_path / "glossary.txt"
    path.write_text(GLOSSARY_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def metadata_file(tmp_path: Path) -> Path:
    path = tmp_path / "metadata.json"
    path.write_text(metadata_json(), encoding="utf-8")
    return path
