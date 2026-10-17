"""本服务承载、但归属后续阶段的规则 —— 预期失败（``xfail``），按规则 ID 打标。

工作纪律：**不静默跳过**。这些规则是行为契约的一部分，只是实现阶段未到；
每个用例都写明了它会因为哪个包尚不存在而失败、以及该由哪个阶段兑现。

| 规则 | 内容 | 为什么现在不可执行 | 兑现阶段 |
|---|---|---|---|
| ``RULE-001``（P0-1） | 分片边界去重、绝不丢正文 | ``post.merge`` 属 P3 | P3 入料与后处理 |
| ``RULE-072``（P0-2） | 任务与分片生命周期；不产出残缺产物 | ``orchestrate`` 属 P5 | P5 编排与总结 |
| ``RULE-061`` 前半 | ``artifact=srt`` 且无时间戳 → 两文件都不写 | **已实现**（见 ``test_runner_end_to_end.py``），不在此列 | P1 ✅ |
| ``RULE-063`` | 提交任务前的输入校验 | ``web`` 属 P6 | P6 Web 层 |
| ``RULE-133`` | 源目录不可写时产物落到回退目录 | ``orchestrate`` 属 P5 | P5 编排 |

判据例子一律用 ``AI_NATIVE_SPEC.md`` §5.4 的**修正值**：P0-1 的重叠必须 ≥ 4 字符
（3 字符重叠不会被去重）；P0-2 的失败场景写作「分片 0-2 与 4-5 成功、分片 3 失败」。
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    strict=False,
    reason="RULE-001 / P0-1：分片边界去重住在 post.merge，属 Phase 3 —— 模块尚不存在",
)
def test_p0_1_duplicate_at_the_chunk_boundary_is_removed_only_with_enough_overlap():
    """修正后的判据：重叠 >= _MIN_OVERLAP_CHARS = 4 才剥；3 字符重叠原样保留。"""
    from transcript_reimagined.post.merge import merge_texts  # Phase 3

    previous = "我们今天讨论第一段。开会。请"
    following = "开会。请继续看第二页。"

    merged = merge_texts(previous, following)
    assert merged.endswith("请继续看第二页。")
    assert merged.count("开会。请") == 1, "≥4 字符的重叠只在边界处去掉一次"

    three_char_overlap = merge_texts("今天我们开会。", "开会。请继续。")
    assert three_char_overlap.count("开会。") == 2, "3 字符重叠检出为 0，正文原样保留"


@pytest.mark.xfail(
    strict=False,
    reason="RULE-072 / P0-2：任务与分片生命周期属 Phase 5（orchestrate）—— 模块尚不存在",
)
def test_p0_2_a_failed_chunk_leaves_no_partial_products(tmp_path):
    """修正后的判据：分片 0-2 与 4-5 成功、分片 3 失败 → 任务 failed、txt/srt 都不写。"""
    from transcript_reimagined.orchestrate import run_task  # Phase 5

    outcome = run_task(out_dir=tmp_path, failed_chunk_indexes=[3])

    assert outcome.status == "failed"
    assert not list(tmp_path.glob("*.txt"))
    assert not list(tmp_path.glob("*.srt"))
    assert sorted(outcome.completed_chunk_indexes) == [0, 1, 2, 4, 5]
    assert outcome.raw_json is None, "失败的任务不写 .raw.json"


@pytest.mark.xfail(
    strict=False,
    reason="RULE-063：提交前输入校验属 Phase 6（web）—— 模块尚不存在",
)
def test_rule_063_invalid_mode_or_artifact_is_rejected_before_any_work():
    from transcript_reimagined.web import validate_task_request  # Phase 6

    with pytest.raises(ValueError, match="mode"):
        validate_task_request(mode="stream", artifact="txt")
    with pytest.raises(ValueError, match="artifact"):
        validate_task_request(mode="offline", artifact="docx")


@pytest.mark.xfail(
    strict=False,
    reason="RULE-133：产物目录回退属 Phase 5（orchestrate）—— 模块尚不存在",
)
def test_rule_133_read_only_source_folder_falls_back_to_the_output_directory(tmp_path):
    from transcript_reimagined.orchestrate import resolve_output_dir  # Phase 5

    read_only = tmp_path / "ro"
    read_only.mkdir(mode=0o500)
    fallback_root = tmp_path / "output"
    source = read_only / "会议.m4a"

    resolved = resolve_output_dir(source, fallback_root=fallback_root)
    assert resolved == fallback_root / "会议"
