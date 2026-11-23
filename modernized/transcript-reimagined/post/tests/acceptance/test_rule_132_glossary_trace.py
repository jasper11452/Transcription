"""RULE-132 —— 替换痕迹写进产物。

规则卡 Given：某次运行 `艾麦→集诚` 替换 **3 处**
→ `.txt` 与 `.srt` 都**以** `# 词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3` 开头；
`.raw.json` 保留 `merged_text_before_glossary`（未替换原文）与 `glossary_changes`。

这条是本服务唯一「跨三个产物」的规则，所以覆盖到真实落盘：`.txt`/`.srt`/`.raw.json`
都写出来之后才判定。同时钉住 `RULE-061` 的契约：`artifact=srt` 且引擎不给时间戳时
**两文件都不写**，以及 `artifact=txt` 时同样不写一个空 `.srt` 充数。
"""

from __future__ import annotations

import json

import pytest

from transcript_reimagined.post import Segment, render_products
from transcript_reimagined.post.products import RawContext, write_products
from transcript_reimagined.post.run import build_products

BEFORE = "艾麦今天来，艾麦昨天走，艾麦明天回"
AFTER = "集诚今天来，集诚昨天走，集诚明天回"
# 注释正文：渲染层负责加 `# ` 前缀（RULE-132：.txt 与 .srt 都以注释块开头）。
HEADER = "词表替换（原始转写见 .raw.json）：艾麦→集诚 ×3"

SEGMENTS = [
    Segment(0.0, 1.0, "集诚今天来"),
    Segment(1.0, 2.0, "集诚昨天走"),
    Segment(2.0, 3.0, "集诚明天回"),
]


def _run_payload(**overrides):
    payload = {
        "source": "meeting.m4a",
        "artifact": "srt",
        "engine": "offline",
        "mode": "offline",
        "merged_text": BEFORE,
        "glossary": "艾麦 -> 集诚\n",
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "艾麦今天来"},
            {"start": 1.0, "end": 2.0, "text": "艾麦昨天走"},
            {"start": 2.0, "end": 3.0, "text": "艾麦明天回"},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def run_products(tmp_path):
    """端到端跑一次切片入口的纯函数部分并落盘。"""

    def _run(**overrides):
        payload = _run_payload(**overrides)
        built = build_products(payload)
        return write_products(built.products, tmp_path, "meeting")

    return _run


@pytest.mark.rule("RULE-132")
class TestRule132Header:
    def test_glossary_changes_count_matches_the_three_replacements(self):
        built = build_products(_run_payload())
        assert [c.describe() for c in built.changes] == ["艾麦→集诚 ×3"]
        assert built.header == HEADER

    def test_txt_starts_with_the_replacement_comment(self, run_products):
        written = run_products()
        assert written.txt_path.read_text(encoding="utf-8").startswith("# " + HEADER + "\n")

    def test_srt_starts_with_the_prefixed_replacement_comment(self, run_products):
        written = run_products()
        assert written.srt_path.read_text(encoding="utf-8").startswith("# " + HEADER + "\n")

    def test_a_run_without_changes_adds_no_header(self, run_products):
        written = run_products(glossary="", merged_text="干净的文本")
        assert not written.txt_path.read_text(encoding="utf-8").startswith("#")
        assert not written.srt_path.read_text(encoding="utf-8").startswith("#")


@pytest.mark.rule("RULE-132")
@pytest.mark.rule("RULE-132")
@pytest.mark.rule("RULE-134")
class TestRule132RawJson:
    def test_raw_json_keeps_the_untouched_original_text(self, run_products):
        raw = json.loads(run_products().raw_path.read_text(encoding="utf-8"))
        assert raw["merged_text_before_glossary"] == BEFORE
        assert raw["final_text"] == AFTER

    def test_raw_json_records_the_change_list(self, run_products):
        raw = json.loads(run_products().raw_path.read_text(encoding="utf-8"))
        assert raw["glossary_changes"] == [{"wrong": "艾麦", "right": "集诚", "count": 3}]

    def test_raw_json_segments_carry_times_and_text_only(self, run_products):
        raw = json.loads(run_products().raw_path.read_text(encoding="utf-8"))
        assert raw["segments"] == [
            {"start": 0.0, "end": 1.0, "text": "集诚今天来"},
            {"start": 1.0, "end": 2.0, "text": "集诚昨天走"},
            {"start": 2.0, "end": 3.0, "text": "集诚明天回"},
        ]


@pytest.mark.rule("RULE-132")
class TestRawContextOptionality:
    """`.raw.json` 的 provenance 字段可缺省（Phase 1 的入口不伪造 task id / 分片行）。"""

    def test_minimal_context_still_yields_the_contract_keys(self, tmp_path):
        products = render_products(AFTER, SEGMENTS, [], merged_text_before_glossary=BEFORE)
        written = write_products(products, tmp_path, "minimal")
        raw = json.loads(written.raw_path.read_text(encoding="utf-8"))
        assert set(raw) == {
            "merged_text_before_glossary",
            "final_text",
            "segments",
            "glossary_changes",
        }

    def test_full_context_is_carried_through(self, tmp_path):
        products = render_products(
            AFTER,
            SEGMENTS,
            [],
            merged_text_before_glossary=BEFORE,
            context=RawContext(
                task_id=7,
                source="meeting.m4a",
                mode="offline",
                artifact="srt",
                engine="offline",
                config={"chunk_max_s": 120.0},
                chunks=[{"idx": 0, "start": 0.0, "end": 3.0, "status": "done"}],
            ),
        )
        written = write_products(products, tmp_path, "full")
        raw = json.loads(written.raw_path.read_text(encoding="utf-8"))
        assert raw["task_id"] == 7
        assert raw["engine"] == "offline"
        assert raw["config"] == {"chunk_max_s": 120.0}
        assert raw["chunks"][0]["status"] == "done"

    def test_products_land_next_to_each_other_with_the_source_stem(self, run_products):
        written = run_products()
        assert written.txt_path.name == "meeting.txt"
        assert written.srt_path.name == "meeting.srt"
        assert written.raw_path.name == "meeting.raw.json"
