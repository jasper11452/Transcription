# `engines` — 引擎层

承载 legacy 的 `engines/base.py` + 四个适配器。**`SPECS` 注册表是引擎 id、所需凭据、
`max_chunk_s`、成本文案的唯一真相来源**；页面/CLI 的引擎清单都从它派生。

## 架构 v2 的两条边

- **`engines → post(align)` 已砍掉。** 引擎只返回原始 `words`（或原生 `segments`），
  对齐由 `orchestrate` 调 `post.align`。因此本包只依赖 `config` 与 `domain`。
- **`engines → ingest(audio)` 已砍掉。** `transcribe` 接收调用方已经探测好的
  `duration_s`；超长拦截仍在引擎内，但不自己 probe。

## 已署名的行为变更

- **D6：bcut 的 90s 风控冷却从实例级提到进程级。** 遗留每个任务新建引擎实例，
  冷却形同虚设；两个 bcut 任务能各自去撞正在风控的上游。
- **Q3：删掉离线引擎的“时间轴兜底死分支”。** 遗留在 `build_segments` 拿不到段落时
  用同样的参数再调一次 `_whisper_words`，结果完全相同 —— 那是死分支，只会把成本翻倍。
  重建版只取一次词级时间轴，退化时由 `align` 的等比兜底报告。

## 失败分类

`classify_http` 的返回类型**就是**重试策略：408/409/425/429/5xx → `RecoverableError`，
其余 → 致命的 `UpstreamError`。每个适配器另有自己的上游错误码映射（百炼 300s /
format 为空、OpenRouter 体积超限、必剪 412 风控）。
