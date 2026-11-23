# `web` — 传输层

**只做传输**：路由 + 请求校验 + SSE 转发。旧层是单个 635 行闭包、25 条路由、
零可测接缝；新层按资源切分，每个 router 可独立构造并测试。

## 路由模块

| 模块 | 资源 |
|---|---|
| `routes/pages.py` | `/`、`/t/{id}`（构建产物 + 内联 `__BOOT__`） |
| `routes/status.py` | `/api/status`、`/api/estimate` |
| `routes/tasks.py` | `/api/tasks` 的创建/列表/详情/取消/续跑/删除 |
| `routes/outputs.py` | 产物预览/下载、原音频、`/api/reveal` |
| `routes/settings.py` | 总结设置、模型清单、词表、凭据 |
| `routes/summaries.py` | 任务的总结状态与显式开启 |
| `routes/events.py` | `/api/tasks/{id}/events`（SSE） |

## 安全

- **来源校验中间件**（NFR-6）：`Host` 必须是白名单；非 GET 请求若带
  `Sec-Fetch-Site` 或 `Origin`，必须是同源。浏览器跨站 POST 一定会带其中之一，
  所以「缺失头就放行」不会留下 CSRF 缺口，同时保证 curl/CLI 可用。
- **`/api/upload` 已删除**（Q11）：它不校验大小与后缀，且没有任务记录指向它。
- **凭据写入**统一走 `config.save_credentials`（0600 原子替换、保留用户注释）；
  空值 = 保留是**路由层**的语义（`RULE-040`），不是写文件层的。
- 页面与日志只出现掩码尾号（`mask` / `mask_preview`）。

## 结构化日志

每次失败都有 `request_id` / `task_id` / `code` 三个字段，而不是一行插值异常文本。
`X-Request-ID` 会回给调用方，便于把页面错误与服务端日志对上。
