# `orchestrate` — 编排与调度

承载 legacy 的 `pipeline.py` + `web/jobs.py`（调度部分）。这是**编排脊柱**：
唯一同时看得见分片状态与落盘决策的地方。

## 两个模块

| 模块 | 职责 |
|---|---|
| `pipeline.py` | 探测 → 归一化 → VAD → 切片 → 逐片转写 → 合并 → 词表 → 渲染 → 落盘；重试与续跑；P0-2 |
| `scheduler.py` | 线程池（离线 1 / 在线 2）、事件总线（500 条重放）、取消语义、SSE、总结触发 |

## 三条结构性约束

1. **产物选择是单点决策**：`post.products.write_products_for(..., artifact=...)`。
   `artifact=txt` 只写 `.txt`，不写 `.srt`（Q9）。
2. **P0-2 出口契约**：任一分片失败 → 任务 `failed`，`.txt`/`.srt` 都不写，
   已完成分片留在 `state.db`（可续跑）。
3. **引擎只交原始 words**：对齐在这里调 `post.align.build_segments`，
   引擎层不 import `post`（架构 v2）。

## 续跑的两种特例

已完成分片默认复用，只有两种情况退回重跑：

- 缓存里的 `text` 为空（引擎对这片没出字）；
- 需要时间轴（`artifact=srt` 或 `enable_diar`）但缓存里既没有 `segments` 也没有 `words`。

有 `words` 而没有 `segments` 时，在本地重建段落，**不重新付费调用引擎**。
