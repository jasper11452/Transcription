# PROJECT.md — acceptance adapter for Transcript

## 1. Project summary

本机网页版转录工具：音视频 → txt + srt，离线默认。FastAPI 单进程服务
（src/transcript/web/app.py，默认端口 8765，只绑 127.0.0.1）+ React 前端
（frontend/，构建产物 src/transcript/web/static/dist/）。CLI 入口
`transcript`（src/transcript/cli.py）是等价入口：run 直接转写、check 环境自检。

## 2. Environment

- **Start dev server:** `uv run transcript serve --no-browser`（端口 8765）
- **Stop dev server:** SIGINT/Ctrl-C（只停本轮启动的进程）
- **Required services:** none（单进程；离线模型从 ~/.cache/huggingface 加载）
- **Already-running detection:** `curl -s 127.0.0.1:8765/api/status`
- **Env / port resolution:** 端口是 DEFAULT_PORT=8765（src/transcript/cli.py），不另行硬编码

## 3. Auth

- **Test account(s):** n/a（本机单用户、无鉴权，刻意设计）
- **Seeding command:** n/a
- 密钥只读 ~/.config/transcript/config.env；验收轮不用真实配置

## 4. Surfaces

### CLI

- **Invocation:** `uv run transcript [--config <file>] run|check|serve`
- **Auth:** 见 §3
- **隔离运行:** 临时 config.env 可覆盖 STATE_DB / OUTPUT_DIR，避免污染真实 state.db

## 5. Project probes & quick navigation

- n/a（无 Web 面自动化工具可用；Web 面留待后续轮）

## 6. Known constraints

- 首次转录需加载本地模型（约几十秒）；在线引擎需密钥（验收轮不涉及）
- 样例音频按项目惯例用 `say -v Tingting` 生成；真实录音是私有素材，不进仓库
