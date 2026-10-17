# CLAUDE.md — transcript-reimagined

**这份文件是新系统的持久上下文。** 它随代码提交，所以**连接信息与凭据只写环境变量名**，不写值。

---

## 这是什么

`transcript`（本机单人转录工具）的**重建版**。不是移植，是**从提取出的意图重建**：
遗留系统是**规格来源**，不是结构模板。

**这是一次保域换壳，不是推平重来。** 领域层（契约、入料切片、后处理、引擎、状态）在
遗留系统里已经具备模块化单体该有的形状，搬运并加固；Web 层与前端两层壳重写。

**当前进度**：Phase 1（领域内核试点）已产出可运行的脚手架。P2–P6 见方案书。

---

## 三条不可违反的约定

1. **顶层名是 `transcript_reimagined`，不是 `transcript`。** 后者会解析到 `.venv` 里遗留的
   `site-packages/transcript/` —— **静默跑旧代码而不报错**。
2. **`domain` 不依赖任何东西。** 零 I/O、零第三方、不 import 同仓其他包。这条由
   `domain/tests/test_zero_dependency_contract.py`（AST 扫描）与 `lint-imports` 双重强制。
3. **重建，不包装。** 重建版永不 import 遗留的 `transcript`。由 import-linter 的
   `forbidden` 契约强制 —— 包装会让「等价」变成自己跟自己比。

---

## 目录结构

```
modernized/transcript-reimagined/
├── pyproject.toml          ← workspace 根：唯一一份 testpaths / importlinter / ruff 配置
├── conftest.py             ← 极薄：只 import conftest_support，不导出任何成员夹具
├── conftest_support/       ← 共享的 sys.path 注入 + 规则过滤插件（唯一一份）
├── domain/                 ← 领域模型 + 错误分类法（零依赖）
├── ingest/                 ← 探测 · 归一化 · 切片规划 · VAD（Phase 1 只含切片规划）
├── post/                   ← 对齐 · 去重 · 词表 · 渲染 · 产物（Phase 1 只含词表 + 渲染）
├── runner/                 ← Phase 1 的纵向切片入口
└── unify_namespace.py      ← 一次性命名空间统一脚本（保留以便审计）
```

各成员内部：`src/transcript_reimagined/<pkg>/` + `tests/`。
**顶层 `transcript_reimagined/` 下没有 `__init__.py`** —— 那是 PEP 420 命名空间包，
四个成员的片段在各自的 `src/` 上合并成同一个顶层包。

---

## 各成员职责

| 包 | 承载 | 它在依赖图的哪一层 |
|---|---|---|
| `domain` | `Word`/`Segment`/`Chunk`/`TranscriptResult`/`AudioInfo`、`Rule`/`Change`/`Issue`、`fmt_timestamp`；`TranscriptError` 家族 + `classify_http`、`is_recoverable`、`retry_delay_s` | 最底层，**零依赖** |
| `ingest` | `plan_chunks`（纯函数）、`ChunkPlan`、`MIN_GAP_FOR_CUT_S`/`MIN_INNER_S` | 只依赖 `domain` |
| `post` | `glossary`（词表四规则）、`render`（txt/srt）、`products`（产物写盘）、`contracts` | 只依赖 `domain` |
| `runner` | 纵向切片入口：元数据 JSON → 切片 → 替换 → 渲染 → 落盘 | 依赖 `{ingest, post}` |
| （P2 起）`config` `state` `engines` `orchestrate` `diar` `summarize` `web` `ui` | 见架构文档 §2 | 见架构文档 §2 |

**分层方向**：`domain ← {ingest, post} ← runner`，P2 起完整形态是
`domain ← config ← {ingest, engines, post, diar, state} ← orchestrate ← web`。

---

## 规格在哪

| 文件 | 是什么 |
|---|---|
| `analysis/transcript/AI_NATIVE_SPEC.md` | **能力清单（C1–C9）、领域模型、接口契约、NFR、行为契约** —— 实现前先读这个 |
| `analysis/transcript/REIMAGINED_ARCHITECTURE.md` | 目标架构：C4 图、包边界与归属理由、数据迁移、范围纪律 |
| `analysis/transcript/MODERNIZATION_BRIEF.md` | **绑定契约**：六个阶段、每阶段的 entry/exit criteria。想改执行方式就编辑它 |
| `analysis/transcript/BUSINESS_RULES.md` | 140 条规则卡，带 `file:line` 引用。验收测试的判据来源 |
| `analysis/transcript/RULE_REVIEWS.json` | 人的 12 条裁定。**判为 `wrong` 的规则不照旧实现** |
| `analysis/transcript/PLAYBOOK.md` | 「重写一个模块的标准动作」十二步 + 结构约定 + 门禁 |
| `analysis/transcript/TOPOLOGY.html` | 遗留系统的交互式依赖图（在浏览器里打开） |
| `legacy/transcript/` | 冻结的规格快照。**只读，全程不改** —— 它是基准 |

---

## 怎么跑测试

从 **workspace 根**跑（不要在成员目录里跑，见下方「陷阱」）：

```bash
cd modernized/transcript-reimagined
python -m pytest                      # 全部 541 个断言
python -m pytest domain/tests         # 单个成员
python -m pytest --list-rules         # 规则覆盖盘点：哪些规则有测试、哪些还是 xfail
python -m pytest --rule=RULE-011      # 只跑某条规则的验收测试
python -m pytest -m pending_implementation   # 只跑还没实现的（xfail）
```

分层契约：

```bash
PYTHONPATH="$PWD/domain/src:$PWD/ingest/src:$PWD/post/src:$PWD/runner/src" lint-imports
```

**路径必须用绝对路径**：import-linter 解析 `PYTHONPATH` 时会先切目录，相对条目会失效。UV 环境里用 `uv run lint-imports`（同样带这组 `PYTHONPATH`）。

**Python 版本**：3.12（`requires-python = ">=3.12,<3.13"`）。

### 端到端跑一次

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
PYTHONPATH="$PWD/domain/src:$PWD/ingest/src:$PWD/post/src:$PWD/runner/src" \
  python -m transcript_reimagined.runner /tmp/meta.json --out /tmp/out --glossary /tmp/glossary.txt
```

写出真实的 `.txt` / `.srt` / `.raw.json`，`# 词表替换…` 头注释在两者里都有，
`.raw.json` 保留替换前原文。

---

## 陷阱（每一条都是踩出来的）

| 症状 | 原因 | 正确做法 |
|---|---|---|
| `ModuleNotFoundError: transcript_reimagined.domain` | 在成员目录里跑 pytest，或 `[tool.pytest.ini_options] pythonpath` 没生效 | 从 **workspace 根**跑；路径注入在 `conftest_support/paths.py`，不依赖 ini |
| `option names {'--rule'} already added` | 多个成员各注册一份 pytest 选项 | 只有 `conftest_support/rule_plugin.py` 一份，根 `conftest.py` 注册它 |
| 测试收集报「同名模块」 | 跨成员有同名测试文件（如 `test_rule_011_chunk_budget.py` 同时在 `ingest/` 与 `runner/`） | 已设 `--import-mode=importlib`；新增成员时**别重名** |
| `from conftest import ...` 拿到错的夹具 | 根 `conftest.py` 与成员 `conftest.py` 同名遮蔽 | 成员夹具放具名模块（如 `runner/tests/_fixtures.py`），别放 conftest |
| 在成员 `pyproject.toml` 里加 pytest 配置 | 成员声明配置会把 rootdir 抢走，路径注入静默失效 | **只有 workspace 根有一份 pytest 配置** |
| `import transcript.X` 却跑出旧行为 | `.venv` 里装着遗留的 `transcript` 包 | 永远用 `transcript_reimagined.X` |

---

## 从遗留到重建的追溯映射

| 遗留（`legacy/transcript/src/transcript/`） | 重建 | 承载的规则 |
|---|---|---|
| `models.py` | `domain/src/.../domain/models.py` | RULE-025（时间戳）、+ `Rule`/`Change`/`Issue` |
| `errors.py` | `domain/src/.../domain/errors.py` | RULE-059（HTTP 失败分类）、`is_recoverable`、`retry_delay_s` |
| `chunking.py` | `ingest/src/.../ingest/chunking.py` + `plan.py` | RULE-011（分片预算与不变量）、RULE-012（静音切点） |
| `glossary.py` | `post/src/.../post/glossary.py` | RULE-021/022/060/132 |
| `render.py` | `post/src/.../post/render.py` | RULE-062/135/136 |
| — （新增） | `post/src/.../post/products.py` + `contracts.py` | 产物写盘的单点决策；接口契约 |
| `pipeline.py` 的落盘段 | `runner/src/.../runner/run.py`（Phase 1 的最小形态） | 纵向切片；Phase 5 会由 `orchestrate` 取代 |

**Phase 1 覆盖的 11 条规则**：RULE-011 012 021 022 025 059 060 062 132 135 136。
逐条对应哪个测试文件，跑 `python -m pytest --list-rules` 看。

---

## 还没做的（见方案书 P2–P6）

| 阶段 | 模块 | 关键约束 |
|---|---|---|
| P2 | `store` `config` | `state.db` 收敛为单写入者；配置写路径三份实现合并为一份；修 RULE-105（数值解析吞异常） |
| P3 | `audio` `vad` `align` `merge` `diar` | P0-1 规则（正文零丢失）在此；`diar` 按裁定接通，**仅离线路径** |
| P4 | `engines.*` | 注册表是引擎知识的唯一真相来源；删 RULE-129 的死分支 |
| P5 | `pipeline` `summary` `orchestrate` | P0-2 规则（失败不写产物）在此；产物选择必须是**单点决策** |
| P6 | `web` `ui` `cli` | 来源校验中间件（NFR-6）；删 `/api/upload`；结构化日志 |

---

## 凭据在哪

**不在这个仓库里，也不在这份文件里。**

| 名字 | 用途 | 在哪配置 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 百炼在线转写 | `~/.config/transcript/config.env`（0600），由 `config` 包读取 |
| `OPENROUTER_API_KEY` | OpenRouter 转写 + Agent 总结 | 同上 |
| `DASHSCOPE_BASE` / `OPENROUTER_BASE` / `BCUT_BASE` | 可覆盖的 Base URL | 同上，有内建默认值 |
| `ENABLE_DIAR` | 说话人分离开关（仅离线路径生效） | 同上 |

**约束**：凭据只从 `~/.config/transcript/config.env` 读，**不读 shell 环境里的同名变量**；
页面与日志只显示掩码尾号；凭据永不进 `state.db`、产物或日志。
在线能力必须**显式开启**，离线是默认。

---

## 范围纪律（`PRODUCT.md` 的非目标即承诺）

**不做**：实时听写、批量/文件夹排队、翻译、字幕编辑器、云端/多用户、鉴权。

说话人分离是**唯一**一处经人裁定放行的扩展，且边界就是「把已经写好的 `diar.py` 接通」——
不是新增能力。任何超出 `AI_NATIVE_SPEC.md` 能力清单的东西，**先回到规格**。