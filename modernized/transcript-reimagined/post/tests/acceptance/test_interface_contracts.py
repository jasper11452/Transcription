"""HTTP 边界契约的形状（`AI_NATIVE_SPEC.md` §3.1；`REIMAGINED_ARCHITECTURE.md` §2）。

`web` 只做传输，但词表语法与产物预览上限的**语义**住在 post。这里钉住 post 提供给
web 的纯函数与它们返回的形状，使得 web 侧不需要把同一条契约实现第二遍
（这正是架构评审要消灭的「同一契约两处实现」）。

被钉住的契约：
- `GET /api/glossary` → `{text, rules[{wrong,right}]}`
- `PUT /api/glossary` → `{rule_count}`，有错行则整份拒绝并带逐行问题；统一错误契约
  `{"error": "<message>"}`
- `GET /api/tasks/{id}/output?kind=txt|srt` → `{content, path, truncated}`，上限 200 000 字符

不以 HTTP 断言覆盖的点（属 `web` 服务的验收面）：路由表本身、SSE 端点、
`POST /api/upload` 的删除（`AI_NATIVE_SPEC.md` §3.1 的 Q11 裁定 —— **本服务不提供任何
上传契约**，也不得有人以「顺带」的名义把它加回来）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript_reimagined.post import render_products
from transcript_reimagined.post.contracts import (
    MAX_OUTPUT_PREVIEW_CHARS,
    OUTPUT_KINDS,
    OutputPreview,
    artifact_paths,
    glossary_response,
    output_preview,
    validate_glossary,
)
from transcript_reimagined.post.products import write_products

GLOSSARY_TEXT = "# 专名表\n小新\n艾麦 -> 集诚\n艾麦 -> 集成\n# 上面这行会报「已在第 3 行定义」"


@pytest.mark.rule("RULE-060")
class TestGetGlossaryContract:
    def test_response_shape_is_text_plus_rules(self):
        response = glossary_response(GLOSSARY_TEXT)
        assert response.text == GLOSSARY_TEXT
        assert [(r.wrong, r.right) for r in response.rules] == [("艾麦", "集诚")]

    def test_reading_does_not_report_problem_lines(self):
        # 读取路径静默忽略错行（与 legacy 的读写不对称一致）：报错只发生在写入路径。
        assert glossary_response(GLOSSARY_TEXT).rules  # 不抛错即为通过

    def test_missing_or_empty_text_yields_an_empty_rule_list(self):
        assert glossary_response("").rules == []


@pytest.mark.rule("RULE-060")
class TestPutGlossaryContract:
    def test_valid_text_returns_the_rule_count(self):
        result = validate_glossary("# 专名表\n小新\n集成\n艾麦 -> 集诚\n")
        assert result.ok
        assert result.rule_count == 1

    def test_any_problem_line_rejects_the_whole_file(self):
        result = validate_glossary("小新\n-> 集诚\n集诚 = 集诚\n")
        assert not result.ok
        assert result.rule_count == 0

    def test_error_message_names_every_line_with_its_problem(self):
        result = validate_glossary("-> 集诚\n集诚 = 集诚\n")
        message = result.error_message()
        assert "第 1 行" in message
        assert "第 2 行" in message
        assert "错词和正确词都要填写" in message
        assert "错词和正确词不能相同" in message

    def test_bare_hot_words_alone_are_a_valid_file(self):
        result = validate_glossary("小新\n选号侠\n")
        assert result.ok
        assert result.rule_count == 0


@pytest.mark.rule("NFR-8")
class TestOutputPreviewContract:
    def test_preview_shape_is_content_path_truncated(self):
        preview = output_preview("正文", "/tmp/x.txt", kind="txt")
        assert isinstance(preview, OutputPreview)
        assert (preview.content, preview.path, preview.truncated) == ("正文", "/tmp/x.txt", False)

    def test_preview_cap_matches_nfr_8(self):
        assert MAX_OUTPUT_PREVIEW_CHARS == 200_000

    def test_content_beyond_the_cap_is_cut_and_flagged(self):
        preview = output_preview("甲" * (MAX_OUTPUT_PREVIEW_CHARS + 1), "/tmp/x.txt", kind="srt")
        assert len(preview.content) == MAX_OUTPUT_PREVIEW_CHARS
        assert preview.truncated is True

    def test_content_exactly_at_the_cap_is_not_flagged(self):
        preview = output_preview("甲" * MAX_OUTPUT_PREVIEW_CHARS, "/tmp/x.txt", kind="txt")
        assert preview.truncated is False

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValueError):
            output_preview("正文", "/tmp/x.txt", kind="raw")

    def test_only_txt_and_srt_are_valid_kinds(self):
        assert OUTPUT_KINDS == ("txt", "srt")


@pytest.mark.rule("RULE-134")
class TestArtifactPathContract:
    """`result` 事件与产物接口共用的路径形状（`AI_NATIVE_SPEC.md` §3.1）。"""

    def test_paths_are_stem_based_next_to_each_other(self):
        paths = artifact_paths("/tmp/out", "meeting")
        assert paths == {
            "txt_path": Path("/tmp/out/meeting.txt"),
            "srt_path": Path("/tmp/out/meeting.srt"),
            "raw_path": Path("/tmp/out/meeting.raw.json"),
        }

    def test_write_products_lands_on_exactly_those_paths(self, tmp_path):
        products = render_products("正文", [], [], merged_text_before_glossary="正文")
        written = write_products(products, tmp_path, "meeting")
        expected = artifact_paths(tmp_path, "meeting")
        assert written.txt_path == expected["txt_path"]
        assert written.srt_path == expected["srt_path"]
        assert written.raw_path == expected["raw_path"]


@pytest.mark.rule("SPEC-3.1")
class TestRemovedUploadSurface:
    """`POST /api/upload` 已按裁定删除（未认证、无上限的写入路径）。"""

    def test_post_contracts_expose_no_upload_entry_point(self):
        import transcript_reimagined.post.contracts as contracts

        public = {name for name in dir(contracts) if not name.startswith("_")}
        assert not any("upload" in name.lower() for name in public)
