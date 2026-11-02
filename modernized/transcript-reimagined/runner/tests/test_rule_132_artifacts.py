"""``RULE-132`` —— 替换痕迹写进产物。

判据：某次运行 ``艾麦→集诚`` 替换 3 处 → ``.txt`` 与 ``.srt`` 都**以** ``# 词表替换…``
开头；``.raw.json`` 保留 ``merged_text_before_glossary``（未替换原文）与
``glossary_changes``。

这是**在真实文件上**验证的：一次 ``run()`` 真的写出三个文件，测试再把它们读回来断言。
"""

from __future__ import annotations

import json

import pytest

from _fixtures import metadata_doc, metadata_json
from transcript_reimagined.runner.run import RunRequest, run


def _run(out_dir, glossary_file, **overrides):
    return run(
        RunRequest(
            metadata_text=metadata_json(**overrides),
            out_dir=out_dir,
            glossary_path=glossary_file,
        )
    )


def test_rule_132_both_products_start_with_the_glossary_header(out_dir, glossary_file):
    result = _run(out_dir, glossary_file)
    assert result.paths.txt is not None and result.paths.srt is not None
    txt_lines = result.paths.txt.read_text(encoding="utf-8").splitlines()
    srt_lines = result.paths.srt.read_text(encoding="utf-8").splitlines()
    for lines, name in ((txt_lines, "txt"), (srt_lines, "srt")):
        assert lines[0].startswith("# 词表替换"), f"{name} 缺头部注释"
        assert "集成→集诚 ×1" in lines[0], name
        assert "艾麦→集诚 ×1" in lines[0], name
    # SRT：注释块之后空行，再接编号 1
    assert srt_lines[1] == ""
    assert srt_lines[2] == "1"
    # TXT：注释行之后紧接着正文，文件以换行结束
    assert txt_lines[1].startswith("[speaker_")
    assert result.paths.txt.read_text(encoding="utf-8").endswith("\n")


def test_rule_132_three_replacements_are_counted_as_three(out_dir, glossary_file):
    result = _run(out_dir, glossary_file, merged_text="艾麦来了。艾麦走了。还是艾麦。")
    assert [(c.wrong, c.right, c.count) for c in result.changes] == [("艾麦", "集诚", 3)]
    assert "艾麦→集诚 ×3" in result.paths.txt.read_text(encoding="utf-8").splitlines()[0]


def test_rule_132_raw_json_keeps_the_untouched_text_and_the_change_list(out_dir, glossary_file):
    result = _run(out_dir, glossary_file)
    raw = json.loads(result.paths.raw_json.read_text(encoding="utf-8"))
    assert raw["merged_text_before_glossary"] == metadata_doc()["merged_text"]
    assert "集成" in raw["merged_text_before_glossary"]
    assert "集成" not in raw["final_text"]
    assert raw["glossary_changes"] == [
        {"wrong": "集成", "right": "集诚", "count": 1},
        {"wrong": "艾麦", "right": "集诚", "count": 1},
    ]


def test_rule_132_raw_json_records_the_traceability_fields(out_dir, glossary_file):
    result = _run(out_dir, glossary_file)
    raw = json.loads(result.paths.raw_json.read_text(encoding="utf-8"))
    assert raw["source"] == metadata_doc()["path"]
    assert raw["engine"] == "dashscope"
    assert raw["mode"] == "online"
    assert raw["artifact"] == "srt"
    assert raw["chunk_count"] == len(result.chunks)
    assert raw["chunk_params"] == {"min_s": 30.0, "max_s": 120.0, "overlap_s": 0.5}
    assert len(raw["chunks"]) == len(result.chunks)
    assert raw["segments"] == [
        {"start": 0.0, "end": 20.0, "text": "我们把集诚做完了。请"},
        {"start": 20.0, "end": 40.0, "text": "确认集诚的报价。"},
        {"start": 40.0, "end": 60.0, "text": "好的。"},
    ]


def test_rule_132_a_run_without_glossary_changes_has_no_header(out_dir, tmp_path):
    empty = tmp_path / "empty-glossary.txt"
    empty.write_text("# 只有注释\n", encoding="utf-8")
    result = _run(out_dir, empty)
    assert result.changes == []
    assert not result.paths.txt.read_text(encoding="utf-8").startswith("#")
    assert result.paths.srt.read_text(encoding="utf-8").startswith("1\n")


def test_rule_132_the_original_text_is_never_rewritten_in_place(out_dir, glossary_file):
    """产物注释说的是「原始转写见 .raw.json」，那就必须真的还在那里。"""
    result = _run(out_dir, glossary_file)
    raw = json.loads(result.paths.raw_json.read_text(encoding="utf-8"))
    assert raw["merged_text_before_glossary"] != raw["final_text"]
    assert raw["final_text"] == "我们把集诚做完了。请确认集诚的报价。"


@pytest.mark.parametrize("key", ["api_key", "DASHSCOPE_API_KEY", "secret", "access_token"])
def test_no_credentials_allowed_in_the_run_input(out_dir, glossary_file, key):
    """``NFR-4``：凭据永不进任务输入。同形状的假值也必须被拒绝。"""
    from transcript_reimagined.runner.metadata import MetadataError

    with pytest.raises(MetadataError):
        _run(out_dir, glossary_file, **{key: "sk-fake-not-a-real-key-0000"})
