# 遗留测试迁移对照（Q13）

**日期**：2026-10-17
**裁定**：Q13 —— `tests/`（264 条断言）搬成新回归套件；`spikes/` 只归档，不进重建。
**性质**：Phase 6 的 exit criterion。下表逐文件说明「搬成了什么」或「为什么没搬」。

> 说明：遗留测试以 `def test_` 计有 **184 个测试函数**（264 条断言含参数化展开）。
> 新套件不追求函数一一对应，而追求**行为判据**一一对应；每条行为都标了规则 ID。

## 已迁移

| 遗留文件 | 测试函数 | 新位置 | 方式 |
|---|---:|---|---|
| `test_store.py` | 8 | `state/tests/test_state_store.py`、`test_lifecycle.py`、`test_schema_migration.py`、`test_summary_state.py` | 逐条搬运 + 增加终态/非法状态/schema 迁移 |
| `test_chunking.py` | 10 | `ingest/tests/test_rule_011_chunk_budget.py`、`test_rule_012_silence_cuts.py` | Phase 1 已搬；保留逐字节等价 |
| `test_render_glossary.py` | 18 | `post/tests/acceptance/*`（RULE-021/022/060/062/132/135/136） | Phase 1 已搬；SRT 说话人按 Q8 增加 |
| `test_align.py` | 11 | `post/tests/acceptance/test_phase3_align_merge.py` | 搬运 + 夹具 + 随机性质测试 |
| `test_merge.py` | 19 | 同上（P0-1 段） | 搬运 + 使用 §5.4 修正后的判据 |
| `test_audio.py` | 10 | `ingest/tests/test_audio_contracts.py` | 搬运；真实 ffmpeg，增加 `--` 与超时断言 |
| `test_engines_online.py` | 33 | `engines/tests/test_dashscope.py`、`test_openrouter.py`、`test_bcut.py`、`test_offline.py`、`test_registry.py` | 用录制夹具回放；不发起真实付费调用 |
| `test_pipeline.py` | 25 | `orchestrate/tests/test_p0_lifecycle.py`、`test_resume.py`、`test_artifact_selection.py`、`test_output_fallback.py`、`test_pipeline_details.py`、`test_legacy_e2e_equivalence.py` | 按行为重写；P0-2 用修正后的 6 分片场景 |
| `test_summary.py` | 6 | `summarize/tests/test_summary.py` | 搬运；Pydantic 死模型按 D10 删除 |
| `test_web.py` | 28 | `web/tests/test_app_security.py`、`test_tasks_api.py`、`test_settings_api.py`、`test_outputs_summary.py`、`test_status_credentials.py` | 按资源重写；来源校验/结构化日志是新增契约 |
| `test_frontend.py` | 6 | `web/tests/test_frontend_gate.py` | 搬运 + 源码一致性静态检查 |

## 已迁移的「人话流程」

| 流程 | 新套件覆盖 |
|---|---|
| 深夜批量整理 | `orchestrate/tests/test_legacy_e2e_equivalence.py`（真实 ffmpeg + 三产物逐字节）、`web/tests/test_tasks_api.py` |
| 边转录边校对 | `orchestrate/tests/test_p0_lifecycle.py`（分片级落库）、`state/tests/test_state_store.py`、`web/tests/test_outputs_summary.py` |
| 断点续跑 | `orchestrate/tests/test_resume.py`（两种特例 + 不重跑 + words 本地重建）、`web/tests/test_tasks_api.py` |
| 显式 Agent 总结 | `summarize/tests/test_summary.py`、`web/tests/test_outputs_summary.py` |

## 有意不迁移（逐条署名）

| 遗留测试 | 为什么 |
|---|---|
| `test_web.py::test_upload_stores_file_and_returns_path` | Q11 裁定删除 `/api/upload`；`/api/tasks` 的上传分支仍保留并有测试 |
| `test_smoke.py`（10 个） | 需要真实 MLX 模型、样例音频与在线凭据；默认套件不下载模型。等价覆盖：`test_legacy_e2e_equivalence.py`（真实 ffmpeg + 确定性引擎）、`diar/tests/test_diar_abi.py::test_real_library_smoke_when_installed`（真实 dylib）。真人听感与在线 UAT 见方案的 §6 人工验收列 |
| `tests/browser_pipeline_server.py`、`tests/frontend_server.py`、`tests/web/*` | 是浏览器测试的启动/辅助脚本，不是断言 |
| 针对旧 `create_app` 闭包内部结构的测试 | 旧层是 635 行闭包、零可测接缝；新层按资源切分，路由契约由 `web/tests` 直接覆盖 |
| 针对 workbench / 已删静态副本的断言 | Q12 裁定删除；两份副本已从仓库移除（见 `DEAD_CODE_REMOVED.md`） |

## 遗留基线里那 2 个失败

`BASELINE.md` 记录的 2 个失败测试，一个已由 Q9 修复（`artifact=txt` 不再写 `.srt`），
新套件用 `post/tests/acceptance/test_artifact_selection_rule_061.py` 与
`orchestrate/tests/test_artifact_selection.py` 双侧钉住；另一个是快照环境里的旧前端
构建断言，新前端构建门禁由 `web/tests/test_frontend_gate.py` 覆盖。
