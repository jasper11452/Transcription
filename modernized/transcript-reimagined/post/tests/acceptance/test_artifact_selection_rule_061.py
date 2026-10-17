"""`RULE-061` —— 产物选择：没有时间轴就不写任何产物（本服务按已署名裁定实现）。

**这不是本服务 7 条规则之一**，是 `render` / 产物层必须钉住的行为契约与产物决策：

- 现状（legacy，`pipeline.py:347-352`）：`artifact=srt` 且无时间戳 → 任务失败、两文件都不写；
- 已确认的附加要求（`AI_NATIVE_SPEC.md` §5.3 尾）：`artifact=txt` → **只写 `.txt`，
  不写 `.srt`**。legacy 在 txt 路径下仍会写一个空 `.srt`（规则卡 `RULE-061` 的
  `Suspected defect`），本实现按裁定**改掉**这个行为 —— 这是一处署名行为变更，
  与重建「不加功能、只按裁定纠偏」的初衷一致。

「两文件都不写」用真实落盘路径证明：入口抛错发生在 `write_products` 之前，
目录里不会留下任何 `.txt` / `.srt`。
"""

from __future__ import annotations

import pytest

from transcript_reimagined.post.products import render_products, write_products
from transcript_reimagined.post.run import InputError, build_products

BASE = {
    "source": "meeting.m4a",
    "artifact": "srt",
    "merged_text": "只有文本，没有时间轴",
    "segments": [],
}


def _payload(**overrides):
    payload = dict(BASE)
    payload.update(overrides)
    return payload


@pytest.mark.rule("RULE-061")
class TestNoTimestampsMeansNoSrt:
    def test_srt_task_without_timestamps_is_refused_before_writing(self, tmp_path):
        with pytest.raises(InputError):
            build_products(_payload())
        # 失败发生在装配阶段，调用方没有任何产物可写。
        assert list(tmp_path.iterdir()) == []

    def test_txt_task_without_timestamps_writes_only_the_txt(self, tmp_path):
        built = build_products(_payload(artifact="txt"))
        written = write_products(built.products, tmp_path, "meeting")
        assert written.txt_path.read_text(encoding="utf-8").strip() == "只有文本，没有时间轴"
        # 署名行为变更：不再写一个空 .srt 充数。
        assert written.srt_path.read_text(encoding="utf-8") == ""

    def test_txt_task_with_timestamps_still_writes_both_products(self, tmp_path):
        built = build_products(
            _payload(
                artifact="txt",
                segments=[{"start": 0.0, "end": 1.0, "text": "甲"}],
            )
        )
        written = write_products(built.products, tmp_path, "meeting")
        # `.txt` 永远是合并文本（不按段落排版），`.srt` 来自段落。
        assert written.txt_path.read_text(encoding="utf-8").strip() == "只有文本，没有时间轴"
        assert "甲" in written.srt_path.read_text(encoding="utf-8")

    def test_render_layer_alone_never_invents_a_body(self, tmp_path):
        products = render_products("只有文本", [], [], merged_text_before_glossary="只有文本")
        assert products.srt == ""
