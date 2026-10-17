# 重建版的有意行为变更

每一处都写明：改了什么、为什么、在哪测试。**未署名的差异视为失败**（方案书 §6）。

| # | 变更 | 原行为 | 为什么 | 测试 |
|---|---|---|---|---|
| D1 | 短密钥不显示尾部 | `secret[-4:]` 对 ≤4 位密钥会把密钥整个打印 | NFR-4：页面只能出现掩码；短密钥的「尾号」就是全部 | `config/tests/test_rule_106_masking.py` |
| D2 | 数值配置解析失败在启动时抛 `ConfigError` | `contextlib.suppress(ValueError)` 静默回退默认值 | `RULE-105` 的人裁定：`CHUNK_MAX_S=12O` 必须可见 | `config/tests/test_rule_105_precedence.py` |
| D3 | 新增配置范围校验 | 只解析、不校验；`CHUNK_OVERLAP_S >= CHUNK_MIN_S` 会让切片不变量失效 | 配置错误属于「不可重试」，应在启动时拦住 | `config/tests/test_rule_105_precedence.py` |
| D4 | `update_task` / `upsert_chunk` 拒绝非法状态值 | 任意字符串都能写进 `status` | 终态集合与生命周期是产品契约，写错应立刻暴露 | `state/tests/test_lifecycle.py` |
| D5 | 分片 payload 的 `segments[]` 带 `speaker` | legacy 的 `as_payload` 丢掉 `speaker` | C8 经人裁定接通；`srt`/`txt` 双产物都要说话人 | `state/tests/test_store.py` |
| D6 | `bcut` 的 90s 风控冷却从实例级提到进程级 | 每个任务新建引擎实例，冷却形同虚设 | 真实 bug：两个 bcut 任务能各自去撞正在风控的上游 | Phase 4 |
| D7 | `to_srt` 输出 `[speaker_N]` 标签 | legacy 的 `to_srt` 完全忽略 `speaker` | Q8 裁定 `srt`/`txt` 双产物一致输出说话人 | `post/tests/acceptance/test_rule_136_speaker_srt.py`、`runner/tests/test_legacy_equivalence.py` |
| D8 | `TranscriptResult` 末尾新增 `words` 字段 | legacy 的引擎自己调 `align` 生成 `segments`，不在结果里带原始词 | 架构 v2 砍掉 `engines → post` 边：引擎只交原始 words，由 `orchestrate` 对齐 | `domain/tests/test_equivalence_with_legacy.py`、`engines/tests/` |
| D9 | ffmpeg/ffprobe 位置参数前加 `--`，并给外部命令加超时 | legacy 无 `--`、无超时 | CWE-88 加固 + NFR-9 超时；不可达但一旦 CLI 能传相对名就可利用 | `ingest/tests/test_audio_contracts.py` |
| D10 | 删除从未实例化的 Pydantic `SummaryContent` | 输出契约同时有 Pydantic 模型与手写 `[:80]`/`[:2000]` 两份实现 | 同一契约两处实现；只保留手写归一化，上限只有一套数字 | `summarize/tests/test_summary.py` |
| D11 | 分片 payload 有 `segments` 时把 `text` 置空 | legacy 同时返回两份正文 | Q4 裁定：以 segments 为准，去掉冗余 text 以免歧义 | `state/tests/test_state_store.py` |
| D12 | `Engine.transcribe` 新增 `duration_s` 入参，引擎不再自己 probe | legacy 的 dashscope 适配器直接调 `audio.probe` | 架构 v2 砍掉 `engines → ingest` 边；时长由 orchestrate 传入 | `engines/tests/test_dashscope.py` |
