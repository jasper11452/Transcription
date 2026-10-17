# Q8 接口面缺口清单（说话人分离）

**日期**：2026-10-17
**裁定**：`MODERNIZATION_BRIEF.md` §7c Q8 —— 接通成端到端功能，但**仅离线路径**。
**性质**：Phase 3 的 entry criterion (b)。实现可以分阶段落，但缺口必须逐条闭合。

## 现状（legacy）

| 面 | 现状 | 缺口 |
|---|---|---|
| `config` | `ENABLE_DIAR` 只能手改 `config.env`；`diar_lib` / `diar_model` 有默认路径 | 只能手改，页面无入口 |
| `pipeline` | `pipeline.py:331` 仅在 `mode == "offline"` 且 `enable_diar` 时调用 `diarize`，随后 `assign_speaker` 写 `Segment.speaker` | 已存在，需原样搬运 |
| API | 没有任何路由读写 `ENABLE_DIAR`；`/api/status` 不返回分离状态 | 缺开关与状态 |
| UI | 没有任何开关或提示 | 缺入口 |
| `txt` | `to_txt` 渲染 `[speaker_N]` 前缀 | 已存在 |
| `srt` | `to_srt` **完全忽略** `speaker` | **缺**：两个产物必须一致输出 |

## 闭合点

| # | 缺口 | 落点 | 验收 |
|---|---|---|---|
| 1 | config 暴露 `enable_diar`，默认 `False` | `config` 包（已完成） | `Config.load` 解析 `ENABLE_DIAR`；默认关闭 |
| 2 | 离线编排调用 `diarize` + `assign_speaker` | Phase 5 `orchestrate` | 仅 `mode == "offline"`；在线路径 `speaker` 全为 `None` 有测试 |
| 3 | `srt` 输出说话人 | `post/render.py` | `[speaker_N]` 前缀在 `.srt` 文本行里同样存在，与 `.txt` 一致 |
| 4 | API 读/写开关 | Phase 6 `web` | `GET /api/status` 返回 `diar_enabled`；`PUT` 路由写 `config.env`（原子、0600） |
| 5 | UI 开关 | Phase 6 `ui` | 设置页可开/关；明确标注「仅离线」 |
| 6 | ABI 验证 | `diar/tests/test_diar_abi.py`（已完成） | stub dylib 真跑 ctypes；真实库存在时 smoke；构建哈希被钉住 |

## 明确不做

- 在线路径的说话人分离 —— 四个在线引擎都不提供说话人信息；做它等于新增能力，不是重建。
- 说话人身份识别 / 命名 —— 只输出 `speaker_N` 泛型编号，同一文件内稳定，不代表身份。
