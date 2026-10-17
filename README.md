# Transcript

本机网页版转录工具：把音视频文件变成 `txt` + `srt`。**离线为默认，在线需显式开启。**

```
浏览器 (127.0.0.1)  ─┬─ 本机路径 / 上传
                     ├─ 离线 | 在线 × 引擎选择
                     └─ 进度 · 字幕 / 文稿 / 总结工作台
                             │
                    FastAPI（单进程，模型常驻 lifespan）
                     ffmpeg 归一化 → silero-vad 切片
                       ├─ 离线：Qwen3-ASR(文本) + mlx-whisper(词级时间戳) → 对齐
                       └─ 在线（可选引擎）：
                            auto  = txt→百炼 ／ srt→OpenRouter
                            百炼 qwen-audio-3.1-asr-flash（字级时间戳，≤5 分钟/次）
                            OpenRouter microsoft/mai-transcribe-2
                            必剪 bcut（匿名免费，音频会上传 B 站存储）
                     → 词表替换 → 分片合并 → 原名.txt / 原名.srt
```

## 引擎对照（实测）

| 引擎 | 时间戳 | 标点 | 费用 | 需要密钥 |
| --- | --- | --- | --- | --- |
| 离线（Qwen3-ASR + whisper 对齐） | 词级 | 有 | 0 | 否 |
| 百炼 `qwen-audio-3.1-asr-flash` | 字级 | 有 | 按秒 | 是 |
| OpenRouter `microsoft/mai-transcribe-2` | 段级 | 有 | ≈$0.1/小时 | 是 |
| 必剪 bcut | 字/句级 | 无 | 免费 | **否** |

单次上限（如百炼 300s）由引擎声明，切片会自动收紧。

## 快速开始

```bash
uv sync
(cd frontend && npm ci && npm run build)   # 源码运行需要 Node 22.12+；首次安装依赖
uv run transcript            # 起服务并自动打开浏览器
```

首次加载模型时，底层模型库可能下载缺失权重；网页尚无专门的模型下载进度。在线功能需要 `~/.config/transcript/config.env`：

```env
OPENROUTER_API_KEY=...
DASHSCOPE_API_KEY=...
SUMMARY_MODEL=z-ai/glm-5.3-flash
OPENROUTER_BASE=https://openrouter.ai/api/v1
```
```bash
chmod 600 ~/.config/transcript/config.env
```

密钥只从这个文件读取，不读 shell 环境里的同名变量；页面与日志只显示掩码尾号，永不回显明文。

详情页把字幕、TXT 文稿和 Agent 总结放在同一组标签中，切换时复用同一内容面板；转录中按分片实时追加已经完成的字幕和文稿。完成后可下载字幕或文稿；已配置 OpenRouter 时，还可以显式开启 Agent 总结，生成项目标题、主旨、要点和待办。启用后会把转录文字、当前提示词和 API 密钥发送到配置的 Base URL，不上传音频。

在任务详情的独立「设置」标签里，可填写自定义 Base URL、API Key 和模型 ID，并编辑总结提示词。支持 OpenRouter 与 OpenAI 兼容服务；API Key 留空保留已有密钥，保存后清空输入框，只显示掩码状态。控制台与详情页共用左侧栏：字标、深浅模式开关都在栏里，历史项目也列在栏内（最近 50 条，按 今天 / 昨天 / 本周 / 更早 分组，栏内独立滚动）；主题选择跨页面和刷新保留。模型 ID 既能直接输入，也能从下拉清单里挑：点右侧箭头看全部模型（含上下文长度、是否支持思考、每百万 token 单价），输入关键字就即时过滤。清单来自 `GET /api/summary-models`，按 Base URL 缓存 10 分钟，拉取失败仍可手填。模型名与 Base URL 写入 `~/.config/transcript/config.env`；Base URL 与 OpenRouter 在线转录共用。提示词保存在同目录的 `summary-prompt.txt`。两个配置文件的权限都设为 `600`。保存不会发起模型请求；只有显式开启或重新生成总结时才会联网。

总结按流式读取：正文（标题、主旨、要点、待办）边生成边显示；模型返回的思考过程放在默认折叠的「思考过程」里，不会挡住正文。默认模型是 `z-ai/glm-5.3-flash`；若某个模型被上游拒绘（例如 HTTP 403），设置里换一个模型后直接重试即可。

同一个面板里还有热词——直接写正确写法就行（例如 `小新`），不必写成 `小心=小新`，回车或逗号分隔。热词保存在 `~/.config/transcript/glossary.txt`，两处生效：Agent 总结的系统提示会带上它们以统一专名写法；转录时也作为引擎热词提示。原有的 `错词 -> 正确词` 规则继续生效，保存热词不会覆盖这些规则。

## 前端开发、测试与打包

源码在 `frontend/`：React + TypeScript + Vite + Tailwind 3 + CLI 安装的 shadcn/ui（Radix / radix-nova）。
两个页面各自有构建入口；FastAPI 服务 `static/dist/index.html` 和 `task.html`，资源只挂在 `/static/dist/`。
不运行 Node 服务、不加载 CDN/远程字体；旧 `static/*.html/js/css` 暂留以保护未合并的实验改动，但不再被服务或装进 wheel。

```bash
# 后端保持运行；另一个终端开发前端（只绑定 127.0.0.1:5173，API 代理到 8765）
cd frontend
npm run dev
# 提交前/运行 pytest 前
npm run build
cd ..
uv run pytest
```

`uv run transcript` 在源码 checkout 中检查构建产物和源码时间，缺失/过期时自动运行本地 `npm run build`（120 秒上限）。
启动不联网安装依赖；缺 npm/依赖、构建失败或产物不完整时会停止并提示修复命令，不退回旧页面。
直接调用 `create_app()`（如 pytest/自定义 ASGI）只校验产物，不触发构建。

```bash
# wheel 必须在前端构建完成后打包；安装 wheel 后运行不需要 Node
(cd frontend && npm ci && npm run build)
uv build --wheel
```

`package-lock.json` 固定 npm 依赖；`node_modules/`、前端构建产物与浏览器测试截图不入库。
Python 测试覆盖 API、入口与构建资源；Vitest 覆盖纯函数（格式化、SRT 解析）与组件/hook（toast、任务流 SSE 生命周期、产物加载与过期丢弃）；Playwright 覆盖生产资源的实际渲染与交互。

测试分布与隔离：

| 层 | 位置 | 说明 |
| --- | --- | --- |
| Python | `tests/` | 接口契约、构建产物契约、JobManager 生命周期；每个用例一个临时 SQLite |
| 组件 | `frontend/src/**/*.test.ts` | 时间码解析、SRT 容错、状态文案 |
| 浏览器 | `frontend/e2e/` | 真跑服务 + 真 Chromium，读页面可见文本断言 |

E2E 用临时 SQLite、临时配置文件和 12 秒合成音频，禁用引擎调用与 Finder 副作用：
`frontend/e2e/serve_e2e.py` 造完隔离环境后原地起服务（端口 8876，只绑 127.0.0.1），
任务号写在 `frontend/e2e/.state.json`（不入库）。因此 e2e 不读 `~/.config/transcript/config.env`，
也不碰 `~/Documents/Transcript/state.db`，与正在使用本机服务的窗口可以同时开着。

## 命令

```bash
uv run transcript                          # 服务 + 自动开浏览器
uv run transcript serve --no-browser       # 只起服务
uv run transcript run <文件> --mode online --online-engine bcut   # 不起服务直接跑
uv run transcript check                    # 环境自检（含可选引擎与上限）
uv run transcript check --probe <音频>      # 用真实音频验证在线引擎还能用
uv run pytest                              # 单元 + 集成
uv run pytest -m smoke                     # 真实模型端到端
uv run ruff check . && uv run ruff format --check .
```

## 文档

- `PRODUCT.md` —— 产品范围、隐私边界与已实现能力。
- `AGENTS.md` —— 给 Agent 的入口、架构约束、边界与验证要求。

## 输出

- 默认与原文件同目录：`原名.txt`、`原名.srt`，另有 `原名.raw.json`（分片级文本/时间戳/状态）。详情页的字幕、文稿和总结共用标签内容区；转录中按分片实时追加已完成内容，完成后可下载字幕或文稿。
- 同目录不可写时回退到 `~/Documents/Transcript/output/<任务名>/`，页面会提示已改落点。
- 原文件只读；16k wav / 64k mp3 工作副本任务结束即删。
