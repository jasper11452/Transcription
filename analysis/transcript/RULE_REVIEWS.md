# 业务规则裁定 — transcript

共 12 条规则经人裁定：**5 条确认**、**7 条判为不对**、0 条待讨论。

判为「不对」或「待讨论」的规则**不算落定**：`brief` 会把它们列为开放问题，不会拿它们构建行为契约；`transform` 与 `reimagine` 不会把判错的规则钉成判据，遇到仍在讨论中的 P0 规则会停下。

本文件由 `/code-modernization:modernize-review` 写出，与进度面板的裁定台（`RULE_REVIEWS.json`）同源。**未改动 `BUSINESS_RULES.md`。**

| 规则 | 裁定 | 时间 | 标题 | 备注 |
|---|---|---|---|---|
| RULE-001 | Right（对，就这么做） | 2026-10-17T15:19:18+08:00 | Deduplicate only at chunk boundaries and never drop content | 对，就这么做 |
| RULE-007 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Only completed chunks feed the live subtitle/text view | 不对，这是缺陷。已完成分片同时带 segments 与 text 时 text 被静默丢弃 |
| RULE-031 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Model list filtering and display cap of 60 | 不对，这是缺陷。60 条上限在计数之前生效，匹配项可能滚不到 |
| RULE-040 | Right（对，就这么做） | 2026-10-17T15:19:18+08:00 | Saving secrets: a blank field keeps the stored secret and a masked preview is n… | 对，保持现状。api.ts 这层设计正确，是 main.tsx 绕过了它 |
| RULE-042 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Audio source is required and an attached file beats a typed path | 不对，这是缺陷。前端缺守卫，没来源的误提交要多跑一趟服务端 |
| RULE-043 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Credential save/clear payload: empty input still saves an empty key | 不对，这是缺陷。空输入应当是无操作，不是写入空值 |
| RULE-061 | Right（对，就这么做） | 2026-10-17T15:19:18+08:00 | An srt task is refused when the engine cannot supply timestamps | 对，但顺手补齐。artifact=txt 时不该写 .srt |
| RULE-072 | Right（对，就这么做） | 2026-10-17T15:19:18+08:00 | Task and chunk status lifecycle; no partial products | 对，就这么做 |
| RULE-081 | Right（对，就这么做） | 2026-10-17T15:19:18+08:00 | A running task with no live process is reported as interrupted, not as running | 对，但需去重。同一套推导在三个地方重复，重写时只留一处 |
| RULE-093 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Stop is not applied optimistically; row state changes only on the next poll | 不对，这是缺陷。点击到反馈之间没有任何回应，且与 task.tsx 不一致 |
| RULE-105 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Configuration precedence and legacy settings compatibility | 不对，这是缺陷。数值解析吞 ValueError，CHUNK_MAX_S=12O 这类手误静默回退默认值 |
| RULE-129 | Wrong（不对 / 不要） | 2026-10-17T15:19:18+08:00 | Offline fallback when no timeline can be produced re-runs the same call and is… | 不对，这是死分支。重写时词级时间轴只算一次，让 align 报告退化原因 |
