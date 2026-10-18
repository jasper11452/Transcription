# CLAUDE.md — transcript-reimagined

**这份文件是新系统的持久上下文。** 它随代码提交，所以**连接信息与凭据只写环境变量名**，不写值。

---

## 这是什么

`transcript`（本机单人转录工具）的**重建版**。不是移植，是**从提取出的意图重建**：
遗留系统是**规格来源**，不是结构模板。

**这是一次保域换壳，不是推平重来。** 领域层在遗留系统里已经具备模块化单体该有的形状，
搬运并加固；Web 层与前端两层壳按新边界重写。

**当前进度**：Phase 1–6 全部落地。**816 个断言**、13 条分层契约、前端的启动硬门槛
与真实构建产物都在仓库里。剩余的人工项只有真实模型/在线上游的 UAT（见方案书 §6）。

---

## 三条不可违反的约定

1. **顶层名是 `transcript_reimagined`，不是 `transcript`。** 后者会解析到 `.venv` 里遗留的
   `site-packages/transcript/` —— **静默跑旧代码而不报错**。
2. **`domain` 不依赖任何东西。** 零 I/O、零第三方、不 import 同仓其他包。由
   `domain/tests/test_zero_dependency_contract.py`（AST 扫描）与 `lint-imports` 双重强制。
3. **重建，不包装。** 重建版永不 import 遗留的 `transcript`。由 import-linter 的
   `forbidden` 契约强制 —— 包装会让「等价」变成自己跟自己比。

---

## 目录结构

```
modernized/transcript-reimagined/
├── pyproject.toml          ← workspace 根：唯一一份 testpaths / importlinter / ruff 配置
├── conftest.py             ← 极薄：只 import conftest_support
├── conftest_support/       ← 共享的 sys.path 注入 + 规则过滤插件（唯一一份）
├── domain/                 ← 领域模型 + 错误分类法（零依赖）
├── config/                 ← 配置装载 · 凭据掩码 · 用户文件的原子写
├── state/                  ← state.db 的唯一写入者（只有它 import sqlite3）
├── ingest/                 ← 探测 · 归一化 · 切片规划 · VAD
├── post/                   ← 对齐 · 去重 · 词表 · 渲染 · 产物
├── diar/                   ← 说话人分离（ctypes FFI，仅离线路径）
├── engines/                ← Engine 协议 + SPECS 注册表 + 4 个适配器
├── summarize/              ← 显式开启的 Agent 总结 + 流式
├── orchestrate/            ← Pipeline（编排）+ JobManager（调度/SSE/取消）
├── web/                    ← FastAPI 路由 + 来源校验 + 结构化日志 + 前端构建门禁
│   └── src/transcript_reimagined/
│       ├── web/            ← 路由按资源切分；static/dist 是构建产物
│       └── cli/            ← 四个子命令
├── frontend/               ← React + Vite 源码（两个入口，无前端路由）
├── runner/                 ← Phase 1 的纵向切片入口（对照基准，不是产品路径）
├── DEVIATIONS.md           ← 每一处有意的行为变更（D1–D12）
└── unify_namespace.py      ← 一次性命名空间统一脚本（保留以便审计）
```

各成员内部：`src/transcript_reimagined/<pkg>/` + `tests/`。
**顶层 `transcript_reimagined/` 下没有 `__init__.py`** —— 那是 PEP 420 命名空间包。

---

## 各成员职责

| 包 | 承载 | 依赖谁 |
|---|---|---|
| `domain` | `Word`/`Segment`/`Chunk`/`TranscriptResult`/`AudioInfo`、`Rule`/`Change`/`Issue`、`fmt_timestamp`；错误分类法 + NFR-11 常量 | **零依赖** |
| `config` | `Config.load`（优先级 + RULE-105 严格解析）、`atomic_write`、`save_credentials`、掩码 | `domain` |
| `state` | `Store`（tasks/chunks/task_summaries）、终态集合、`task_flags` | `domain` |
| `ingest` | `plan_chunks`、`probe`/`to_wav16k`/`to_mp3_64k`/`cut`/`verify`、`speech_spans` | `domain`（+ ffmpeg、mlx-audio） |
| `post` | `align`、`merge`（P0-1）、`glossary`、`render`、`products`（单点产物决策） | `domain` |
| `diar` | `diarize`（ctypes）· `assign_speaker` · ABI 哈希 | `config`、`domain` |
| `engines` | `SPECS` 注册表、`resolve_kind`、4 个适配器 | `config`、`domain`（+ httpx、MLX） |
| `summarize` | 总结状态机、分批、流式、输出契约 | `config`、`state`、`post`、`domain` |
| `orchestrate` | `Pipeline`（P0-2、续跑、产物单点决策）、`JobManager`（并发/事件/改消） | 上列全部 + `summarize` |
| `web` | 资源路由、来源校验、结构化日志、SSE 转发、前端门禁 | `orchestrate` 及以下 |
| `cli` | `serve` / `run` / `check` / `init-config` | `web` 及以下 |

**分层**：`domain ← config ← {ingest, engines, post, diar, state} ← summarize ← orchestrate ← web ← cli`。
`runner` 是独立的 P1 切片，不参与产品路径。

---

## 规格在哪

| 文件 | 是什么 |
|---|---|
| `analysis/transcript/AI_NATIVE_SPEC.md` | **能力清单（C1–C9）、领域模型、接口契约、NFR、行为契约** |
| `analysis/transcript/REIMAGINED_ARCHITECTURE.md` | 目标架构：C4 图、包边界与归属理由、数据迁移、范围纪律 |
| `analysis/transcript/MODERNIZATION_BRIEF.md` | **绑定契约**：六个阶段、每阶段的 entry/exit criteria |
| `analysis/transcript/BUSINESS_RULES.md` | 140 条规则卡，带 `file:line` 引用 |
| `analysis/transcript/RULE_REVIEWS.json` | 人的 12 条裁定。**判为 `wrong` 的规则不照旧实现** |
| `analysis/transcript/PLAYBOOK.md` | 「重写一个模块的标准动作」十二步 + 结构约定 + 门禁 |
| `analysis/transcript/TEST_MIGRATION.md` | 遗留 184 个测试函数 → 新套件的逐文件对照与省略理由 |
| `analysis/transcript/DIAR_INTERFACE_GAPS.md` | Q8 的接口面缺口与闭合点 |
| `legacy/transcript/` | 冻结的规格快照。**只读，全程不改** |

---

## 怎么跑测试

从 **workspace 根**跑（不要在成员目录里跑）：

```bash
uv sync --all-packages                # 首次/改依赖后：安装全部成员（普通 uv sync 不够）
uv run pytest                          # 全部断言（约 824）
uv run pytest domain/tests             # 单个成员
uv run pytest --list-rules             # 规则覆盖盘点
uv run pytest --rule=RULE-072          # 只跑某条规则
uv run pytest -m pending_implementation
```

分层契约（**绝对路径**：import-linter 解析 `PYTHONPATH` 时会切目录）：

```bash
PYTHONPATH="$PWD/domain/src:$PWD/config/src:$PWD/state/src:$PWD/ingest/src:$PWD/post/src:$PWD/diar/src:$PWD/engines/src:$PWD/summarize/src:$PWD/orchestrate/src:$PWD/web/src:$PWD/runner/src" uv run lint-imports
```

**Python 版本**：3.12（`requires-python = ">=3.12,<3.13"`）。

### 端到端跑一次（真实文件系统）

```bash
cd modernized/transcript-reimagined
cat > /tmp/meta.json <<'JSON'
{"duration_s": 300.0,
 "spans": [[0.0,40.0],[41.2,90.0],[91.5,150.0],[151.0,210.0],[211.0,290.0]],
 "path": "meeting.m4a",
 "merged_text": "我们把集成做完了。",
 "segments": [{"start":0.0,"end":4.0,"text":"我们把集成做完了"}]}
JSON
printf '集成 -> 集诚\n' > /tmp/glossary.txt
PYTHONPATH="$PWD/domain/src:$PWD/config/src:$PWD/state/src:$PWD/ingest/src:$PWD/post/src:$PWD/diar/src:$PWD/engines/src:$PWD/summarize/src:$PWD/orchestrate/src:$PWD/web/src:$PWD/runner/src" \
  uv run python -m transcript_reimagined.runner /tmp/meta.json --out /tmp/out --glossary /tmp/glossary.txt
```

### CLI 与 Web

```bash
uv run python -m transcript_reimagined.cli.main check
uv run python -m transcript_reimagined.cli.main run <音频> --mode offline --artifact srt
uv run python -m transcript_reimagined.cli.main serve --port 8765 --no-browser
```

### 前端

```bash
cd frontend
npm ci && npm run build     # 产物落到 web/src/transcript_reimagined/web/static/dist
npm test                    # 主题/壳层的 11 条 Node 测试
```

服务启动时 `ensure_frontend` 会校验产物完整性；源码比产物新且本地有
`node_modules/.bin/vite` 才重建，**绝不自动 `npm install`**。

---

## 陷阱（每一条都是踩出来的）

| 症状 | 原因 | 正确做法 |
|---|---|---|
| `ModuleNotFoundError: transcript_reimagined.domain` | 在成员目录里跑 pytest，或 `pythonpath` ini 没生效 | 从 **workspace 根**跑；路径注入在 `conftest_support/paths.py` |
| 安装后 `import transcript_reimagined.cli` 失败 | 成员 wheel 包根写成了子包目录；editable 安装只把该目录放进 `sys.path` | 包根统一写 `src/transcript_reimagined`（PEP 420 命名空间根）；`uv sync --all-packages` |
| `option names {'--rule'} already added` | 多个成员各注册一份 pytest 选项 | 只有 `conftest_support/rule_plugin.py` 一份 |
| 测试收集报「同名模块」 | 跨成员有同名测试文件或同名 helper（`_fakes.py` 就踩过） | `--import-mode=importlib`；helper 用**成员前缀**命名（`orchestrate_fakes.py`、`web_fakes.py`） |
| `from conftest import ...` 拿到错的夹具 | 根与成员 `conftest.py` 同名遮蔽 | 成员夹具放具名模块（`runner/tests/_fixtures.py`），别放 conftest |
| 在成员 `pyproject.toml` 里加 pytest 配置 | 成员声明配置会把 rootdir 抢走 | **只有 workspace 根有一份 pytest 配置** |
| `import transcript.X` 却跑出旧行为 | `.venv` 里装着遗留的 `transcript` 包 | 永远用 `transcript_reimagined.X` |
| import-linter 报「Missing layer」 | 只把 `runner/src` 放进了 `PYTHONPATH` | 传**全部**成员的 `src` 绝对路径 |
| `sqlite3 只在 state` 契约误报上层 | `forbidden` 默认连间接 import 也查 | 该契约设了 `allow_indirect_imports = true`，只禁直接 import |
| 前端启动报「产物缺失」 | 没构建 / 产物过期 / 只提交了源码 | `cd frontend && npm ci && npm run build`，提交 `static/dist` |
| 页面 POST 被 403 | 来源校验中间件拒绝跨站请求 | 浏览器同源自动带 `Origin`/`Sec-Fetch-Site`；脚本不带头会放行 |
| `from transcript_reimagined.cli import main` 得到函数而非模块 | 包 `__init__` 的 `main` 遮蔽了子模块 | 测试用 `importlib.import_module("transcript_reimagined.cli.main")` |

---

## 从遗留到重建的追溯映射

| 遗留（`legacy/transcript/src/transcript/`） | 重建 | 承载的规则 |
|---|---|---|
| `models.py` `errors.py` | `domain/` | RULE-025、RULE-059、NFR-11 |
| `config.py` | `config/` | RULE-040/051/105/106 |
| `store.py` | `state/` | RULE-072/074/081/086/088/089 |
| `audio.py` `vad.py` `chunking.py` | `ingest/` | RULE-011/012/028/049/050 |
| `align.py` `merge.py` `glossary.py` `render.py` | `post/` | RULE-001（P0-1）/008/009/010/021/022/023/024/060/062/132/135/136/139 |
| `engines/*` | `engines/` | RULE-014/017/018/019/020/026/052–058/082/107/108/109/111/113/114/127–131/140 |
| `diar.py` | `diar/` | RULE-013、C8（仅离线） |
| `pipeline.py` | `orchestrate/pipeline.py` | RULE-026/029/061/063/072（P0-2）/073/082/086/133 |
| `web/jobs.py` | `orchestrate/scheduler.py` | RULE-029/081/089/090 |
| `summary.py` | `summarize/` | RULE-027/034/065/066/070/071/081/088/137 |
| `web/app.py` | `web/routes/` | RULE-039/040/052/053/055/056/058/063/064/067/110/127/138/139 |
| `web/frontend.py` | `web/frontend.py` | NFR-7 / RULE-068 |
| `cli.py` | `web/src/transcript_reimagined/cli/` | C9 |

**Phase 1–6 覆盖的规则**：跑 `uv run pytest --list-rules` 看逐条归属。

---

## 有意的行为变更

全部在 [`DEVIATIONS.md`](DEVIATIONS.md)。最重要的几条：

- **D2**：数值配置解析失败在启动时抛 `ConfigError`（RULE-105）。
- **D6**：bcut 的 90s 风控冷却提到进程级。
- **D7**：`to_srt` 输出 `[speaker_N]`（Q8）。
- **D8**：`TranscriptResult` 新增 `words`；引擎不再自己对齐。
- **D10**：删除从未实例化的 `SummaryContent` 死契约。
- **D11**：有 `segments` 的分片 payload 不再重复返回 `text`（Q4）。

---

## 凭据在哪

**不在这个仓库里，也不在这份文件里。**

| 名字 | 用途 | 在哪配置 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 百炼在线转写 | `~/.config/transcript/config.env`（0600），由 `config` 包读取 |
| `OPENROUTER_API_KEY` | OpenRouter 转写 + Agent 总结 | 同上 |
| `DASHSCOPE_BASE` / `OPENROUTER_BASE` / `BCUT_BASE` | 可覆盖的 Base URL | 同上，有内建默认值 |
| `ENABLE_DIAR` | 说话人分离开关（仅离线路径生效） | 同上；也可在控制台「更多设置」里开关 |

**约束**：凭据只从 `~/.config/transcript/config.env` 读，**不读 shell 环境里的同名变量**；
页面与日志只显示掩码尾号；凭据永不进 `state.db`、产物或日志。
在线能力必须**显式开启**，离线是默认。

---

## 范围纪律

**不做**：实时听写、批量/文件夹排队、翻译、字幕编辑器、云端/多用户、鉴权。

说话人分离是**唯一**一处经人裁定放行的扩展，边界是「把已经写好的 `diar.py` 接通」，
**仅离线路径**；在线引擎的 `speaker` 恒为 `None` 并有测试断言。
任何超出 `AI_NATIVE_SPEC.md` 能力清单的东西，**先回到规格**。
