"""合并去重单测。切片留了重叠，合并写错就会出重复段落或丢字。"""

from __future__ import annotations

from transcript.merge import longest_overlap, merge_results, merge_segments, merge_texts
from transcript.models import Segment, TranscriptResult


def test_merge_texts_removes_exact_overlap():
    assert (
        merge_texts("今天讨论三件事。", "三件事。第一，离线转写。")
        == "今天讨论三件事。第一，离线转写。"
    )


def test_merge_texts_no_overlap_concatenates():
    assert merge_texts("第一段。", "第二段。") == "第一段。第二段。"


def test_merge_texts_fuzzy_overlap():
    """跨切点的转写不会逐字一致，模糊匹配也要能去重。"""
    prev = "第三，专有名词需要校对，例如冒烟测试"
    new = "专有名词需耍校对，例如冒烟测试和分片合并。"
    merged = merge_texts(prev, new)
    assert merged.count("冒烟测试") == 1
    assert merged.endswith("和分片合并。")


def test_merge_texts_never_drops_content():
    """宁可有重复，也不能吃掉内容。"""
    prev = "甲" * 50
    new = "乙" * 50
    assert len(merge_texts(prev, new)) == 100


def test_longest_overlap_is_conservative_for_short_matches():
    """两三个字的偶然相同不算重叠：宁可留重复，也不能吃掉正文。"""
    assert longest_overlap("……专有名词", "名词需要校对") == 0
    assert longest_overlap("甲甲甲甲甲", "甲甲乙乙乙") == 0


def test_longest_overlap_detects_meaningful_overlap():
    assert longest_overlap("前面的话到这里结束", "到这里结束后面继续") == 5


def test_common_prefix_char_is_not_an_overlap():
    """共同的第一个字（“第一段。” vs “第二段。”）不是重叠，不能吃掉后半句。"""
    assert longest_overlap("第一段。", "第二段。") == 0
    assert merge_texts("第一段。", "第二段。") == "第一段。第二段。"


def test_longest_overlap_requires_anchoring_at_tail():
    """new 的开头若在 prev 中间出现（不是接续），不能当成重叠。"""
    assert longest_overlap("开场白提到冒烟测试然后结束了", "冒烟测试又是另一个话题的开头") == 0


def test_template_sentences_are_not_treated_as_overlap():
    """模板化重复文本（每句只差数字）不能用套话连成长重叠。

    实测（2026-09-19，55 分钟合成录音 / 79 片 / dashscope）：相邻两片是
    “第 268 段…”与“第 271 段…”，套话把匹配块在 new 一侧连成一串，
    真正不同的数字留在 prev 一侧的大缝里；旧判据误判成 54 字重叠，
    整句正文被删——79 片里 10 个边界共丢掉 36 句（440 → 404）。
    """
    prev_tail = (
        "这是第 268 段测试语音，用来验证长音频的在线转写。"
        "这是第 269 段测试语音，用来验证长音频的在线转写。"
        "这是第 270 段测试语音，用来验证长音频的在线转写。"
    )
    new_head = (
        "这是第 271 段测试语音，用来验证长音频的在线转写。"
        "这是第 272 段测试语音，用来验证长音频的在线转写。"
    )
    assert longest_overlap(prev_tail, new_head) == 0
    merged = merge_texts(prev_tail, new_head)
    assert merged.count("第 271 段") == 1
    assert merged.count("第 272 段") == 1


def test_merge_segments_trims_overlap_at_chunk_boundary():
    """跨分片边界（两组）的重复要去掉，并把上一段的时间收窄。"""
    chunk1 = [Segment(0.0, 5.0, "前一片的话到这里")]
    chunk2 = [Segment(4.5, 9.0, "到这里，后一片接着说话")]
    out = merge_segments([chunk1, chunk2])
    assert len(out) == 2
    assert out[0].end <= out[1].start + 1e-6
    assert "到这里" in out[1].text


def test_merge_segments_drops_fully_duplicated_next_chunk_head():
    """下一片开头整段都是重复时，那一段不该留下（否则字幕会重一遍）。"""
    out = merge_segments([[Segment(0.0, 5.0, "同一句话")], [Segment(5.0, 6.0, "同一句话")]])
    assert len(out) == 1
    assert out[0].text == "同一句话"


def test_merge_segments_does_not_dedup_inside_one_chunk():
    """同一片内部的重复（口头禅、强调）必须保留：重复只可能来自切片重叠。

    实测教训：对每个句子边界（1476 处）都去重时，SRT 比 TXT 少了 111 字。
    """
    out = merge_segments([[Segment(0.0, 3.0, "对对对"), Segment(3.0, 6.0, "对对对，这个没问题")]])
    assert len(out) == 2
    assert out[1].text == "对对对，这个没问题"


def test_merge_segments_orders_within_a_chunk():
    out = merge_segments([[Segment(5.0, 6.0, "后"), Segment(0.0, 1.0, "前")]])
    assert [s.text for s in out] == ["前", "后"]


def test_merge_results_sums_cost_but_does_not_fabricate_a_duration():
    """费用求和；时长**不**求和。

    旧行为是"把各分片的音频秒数相加"，实测在续跑后得到 1225s —— 而源音频是 5243s
    （离线分片不报秒数，只有续跑恢复的分片带了 chunk.duration，求和成了部分和）。
    任务时长应由源文件的 ffprobe 结果决定，那条契约在
    tests/test_pipeline.py::test_source_duration_is_recorded_even_after_resume。
    """
    a = TranscriptResult(
        text="第一段。",
        audio_seconds=60.0,
        cost_usd=0.001,
        engine="a",
        segments=[Segment(0.0, 1.0, "第一段。")],
    )
    b = TranscriptResult(
        text="第一段。第二段。",
        audio_seconds=60.0,
        cost_usd=0.002,
        engine="a",
        segments=[Segment(60.0, 61.0, "第二段。")],
    )
    merged = merge_results([a, b])
    assert abs(merged.cost_usd - 0.003) < 1e-9
    assert merged.audio_seconds is None, "不要把分片秒数当成整段音频时长"
    assert merged.text.count("第一段") == 1
    assert "第二段" in merged.text


def test_merge_results_empty_is_safe():
    assert merge_results([]).text == ""


def test_merge_segments_dedups_text_even_when_times_do_not_overlap():
    """实测反例：分片边界上会出现"文本重复但时间不重叠"。

    87 分钟真实录音里出现 4 处、共 54 字重复（对齐把上一段的结束时间留在了切点之前）。
    去重判据必须是**文本**，只看时间重叠会让 SRT 重复而 TXT 不重复——两条产物必须一致。
    """
    chunk1 = [Segment(0.0, 10.0, "好的让我们再次感谢齐飞的分享啊")]
    chunk2 = [Segment(10.2, 20.0, "好的让我们再次感谢齐飞的分享啊那呃齐飞刚刚也为我们分享了")]
    out = merge_segments([chunk1, chunk2])
    joined = "".join(s.text for s in out)
    assert joined.count("好的让我们再次感谢齐飞的分享啊") == 1
    assert "那呃齐飞刚刚也为我们分享了" in joined
    assert out[0].end <= out[1].start + 1e-6


def test_merge_segments_keeps_genuine_repetition_within_a_segment():
    """同一段里的口头重复不能被动：去重只处理"上一段尾 = 下一段头"。"""
    out = merge_segments([[Segment(0.0, 5.0, "对对对对，这个没问题。")]])
    assert out[0].text == "对对对对，这个没问题。"


def test_merge_results_text_and_segments_agree():
    """不变量：合并后的 txt 与所有 segment 拼起来的内容必须一致（同一条去重规则）。"""
    from transcript.align import normalize_for_compare as norm

    a = TranscriptResult(
        text="前面的话到这里结束",
        segments=[Segment(0.0, 10.0, "前面的话到这里结束")],
        engine="x",
        cost_usd=0.001,
    )
    b = TranscriptResult(
        text="到这里结束后面继续。",
        segments=[Segment(10.3, 20.0, "到这里结束后面继续。")],
        engine="x",
        cost_usd=0.002,
    )
    merged = merge_results([a, b])
    from_segments = norm("".join(s.text for s in merged.segments))
    assert norm(merged.text) == from_segments
    assert "到这里结束后面继续" in merged.text
    assert merged.text.count("到这里结束") == 1


def test_merge_results_records_zero_cost_for_free_engines():
    """免费引擎报 0.0 要如实记 0，不能因为 falsy 就变成 None（那是"未知"）。"""
    free = TranscriptResult(text="甲", segments=[Segment(0, 1, "甲")], engine="bcut", cost_usd=0.0)
    unknown = TranscriptResult(
        text="乙", segments=[Segment(1, 2, "乙")], engine="dashscope", cost_usd=None
    )
    assert merge_results([free]).cost_usd == 0.0
    assert merge_results([unknown]).cost_usd is None
    assert merge_results([free, unknown]).cost_usd == 0.0
