# BASELINE — transcript（重建前的行为基准）

**日期**：2026-10-17
**基准快照**：`legacy/transcript/`（工作区内的真实目录，非符号链接；由 `git archive HEAD` @ `e0e29c0` 导出）

本文件是 **Phase 1 的 entry criterion 之一**（「`BASELINE.md` 已记录快照测试套件在 `legacy/transcript` 上的运行结果，以及那 2 个失败的测试名」）。
重建后的新系统必须在 §1 的相同输入下重现 §2 的通过集合，并在 §3 中每一条上给出明确结论。

---

## 1. 记录的基线（本次实测）

运行方式（**只读**，不写入 `legacy/`）：

```bash
cd /Users/jasper/Documents/Transcript
.venv/bin/python -m pytest legacy/transcript/tests \
  -m "not smoke and not online" -p no:cacheprovider \
  -o testpaths= --rootdir=legacy/transcript
```

| 项目 | 结果 |
|---|---|
| 通过 | **264** |
| 失败 | **2** |
| 跳过（deselected） | 10 |
| 墙钟 | **8.9 s** |
| 解释器 | Python 3.12.11（`.venv`，与 `requires-python = ">=3.12,<3.13"` 一致） |
| 副作用核对 | `legacy/` 下无 `__pycache__`、无 `.pytest_cache` —— 快照未被改动 |

前端：

| 命令 | 结果 |
|---|---|
| `node --test tests/*.test.mjs` | **11/11 通过** |
| `npx tsc --noEmit` | 干净（退出码 0） |

后端静态检查：

| 项目 | 结果 |
|---|---|
| `ruff` 0.16.7 | 已配置（`pyproject.toml`：`E,F,I,UP,B,SIM`，忽略 `E501`） |
| 54 个 `.py` 全部 AST 解析 | 0 语法错误 |

---

## 2. 全部通过的测试文件（264 项，按文件）

| 测试文件 | 覆盖的行为 |
|---|---|
| `tests/test_align.py` | 文本到词级时间轴的对齐、单调时间不变量、弃句分组 |
| `tests/test_audio.py` | ffprobe 探测、归一化契约校验（不靠「ffmpeg 没报错」推断） |
| `tests/test_chunking.py` | 分片规划与 `duration <= max_s` 不变量 |
| `tests/test_engines_online.py` | 在线引擎的请求构造、失败分类、凭据不外泄（夹具回放，不发起真实调用） |
| `tests/test_frontend.py` | 前端构建产物契约（`validate_dist` 的门禁语义） |
| `tests/test_merge.py` | 分片合并与重叠去重（**含 P0 行为的既有断言**） |
| `tests/test_render_glossary.py` | txt/srt 渲染、热词解析与确定性替换 |
| `tests/test_store.py` | SQLite schema、任务/分片状态、终态集合、凭据不入库 |
| `tests/test_summary.py` | 总结的输出契约、流式解析、失败独立性 |
| `tests/web/*` | 路由契约、任务调度、前端契约、总结设置、任务标题 |

> 重建后，上表每一行都必须有对应的新断言，或每一处省略都要署名并说明理由（Phase 6 的 exit criterion）。

---

## 3. 2 个失败的测试 —— 它们是基线的**已知偏移**，不是环境问题

```
FAILED tests/test_pipeline.py::test_txt_run_does_not_emit_srt
FAILED tests/test_web.py::test_output_missing_kind_returns_404
```

**同一件事的两个角度**，都断言 `artifact=txt` 的任务不该产出 `.srt`：

| 测试 | 断言 | 实际 |
|---|---|---|
| `test_pipeline.py:174`（文档字符串：「txt 任务不该产出半成品 srt（没有时间戳就没资格给 srt）」） | `result.srt_path is None` | `PosixPath('.../input.srt')` |
| `test_web.py:298` | `GET /api/tasks/{id}/output?kind=srt` 返回 404 | 返回 200 |

**根因**：`src/transcript/pipeline.py:366` **无条件**写 srt ——

```python
txt_path = self._write(out_dir / f"{stem}.txt", to_txt(...))
srt_path = self._write(out_dir / f"{stem}.srt", to_srt(...))   # ← 没有 artifact == "srt" 判断
```

同一文件第 347 行**有** `artifact == "srt"` 判断（时间戳缺失时拒绝），第 469 行也按 `artifact` 决定要不要时间戳 —— 说明分支意识是有的，只是落盘这一处漏了。

**这不是测试写错**：两个独立测试从两个角度断言同一件事，且断言方向一致。

### 重建时如何看待这 2 个失败

**它们不是「要重现的基线」，是要修掉的缺陷。** 按 `RULE_REVIEWS.json` 中 `pipeline.py:347-352` 的裁定（「**对，但顺手补齐**」）：

- 保留的部分：`artifact=srt` 且引擎无时间戳 → 任务失败，两个文件都不写。
- **补齐的部分**：`artifact=txt` → **只写 `.txt`，不写 `.srt`**。

因此基线判据是：

- [ ] 新回归套件中，这两个用例**断言的方向与旧测试一致**（`srt_path is None` / 404），且**通过**
- [ ] `artifact=srt` 的路径行为不变（仍写两个文件）
- [ ] 若新实现在这一点上的行为与旧实现不同，该差异必须**署名**并归因到本缺陷的修复

---

## 4. 被排除在基线之外

| 排除项 | 原因 |
|---|---|
| `-m smoke`（10 项被跳过中的全部或绝大多数） | 需要样例音频与本地 MLX 模型权重，属于环境依赖的端到端冒烟 |
| `-m online` | 需要网络与云端凭证，会产生真实费用 |
| `tests/` 与 `spikes/` 的规则挖掘 | 本次 `extract-rules` 按人选择只跑了 9 个产品分片（见 brief Q13） |
| `.venv` 之外的 Python 3.15 | 项目硬钉 `>=3.12,<3.13`；基线只在 3.12.11 上记录 |

---

## 5. 本文件不声称的事

- 不含任何工期或成本估算。
- 264 这个数字**不是覆盖率**，是「可运行的断言条数」。没有覆盖率测量（未装 `coverage`/`pytest-cov`）。
- 10 个被跳过的测试**未被执行**，因此不构成任何行为证据。