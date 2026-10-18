# PLAYBOOK —— 重写一个模块的标准动作

**日期**：2026-10-17
**来源**：Phase 1 试点（`wf_b96c9768-162` 脚手架 + 会话内的收口重构）
**性质**：方案书 Phase 1 的 exit criterion；P2–P6 每个阶段按它复用

---

## 0. 为什么这份文件存在

方案书把 Phase 1 定位成**假设验证器**：它要回答的不是「这个模块能不能重写」，而是「重写一个模块的标准动作是什么」。试点改成纵向切片（见方案书 Phase 1 的 `Proposed revision`）就是为了让这套动作在真实接缝上跑一遍 —— 文件 I/O、跨包 import、产物落盘。

**这套动作本身也是假设。** 下面第 6 节记了试点实际推翻的三处预期。

---

## 1. 标准动作（十二步）

### 搬运前

1. **先读规则卡，不是先读代码。** `BUSINESS_RULES.md` 里 `source` 落在本模块的那几条，逐条读 Given/When/Then 与 `parameters`。规则卡已经把「行为契约」从实现里剥出来了 —— 照着代码重写会把实现细节当契约。
2. **核对规则卡的裁定状态。** `RULE_REVIEWS.json` 里判为 `wrong` 的，**不照旧实现**，按裁定改；判为 `discuss` 的 P0 停下来问。试点里这一条直接决定了两处行为（`offline.py` 的死分支、`fmt_timestamp` 的注释）。
3. **检查规则卡里的例子是否可信。** P0 小组会用「实际执行被引用的函数」来验证，试点里两条 P0 的**具体例子都写错了**（3 字符 vs `_MIN_OVERLAP_CHARS = 4`；分片序号自相矛盾）。**规则陈述可信，例子的具体取值要复算。**
4. **记下注释里承载的不变量。** 这类东西没有测试守着，最容易在搬运中失传。试点遇到的：`chunking` 的 `duration <= max_s` 是 300s 上游上限不被击穿的唯一保障；`merge` 的保守去重阈值来自一次真实事故（87 分钟录音丢 111 字符）。
5. **判断模块属于哪一层，以及它允许依赖谁。** 试点用的分层：`domain ← {ingest, post} ← orchestrate ← web`。**`domain` 零依赖是硬约束**，由测试 + import-linter 强制。

### 搬运中

6. **先建包骨架，再填内容。** 骨架 = `pyproject.toml`（含 `packages` 指向命名空间下的子目录）+ `src/transcript_reimagined/<pkg>/` + `tests/`。**顶层 `transcript_reimagined/` 下不要放 `__init__.py`** —— 那会破坏 PEP 420 命名空间包，让四个成员无法合并。
7. **逐字节等价重写，不顺手改。** 未裁定为缺陷的行为**原样保留**并用测试钉住。试点实例：`Segment.shifted()` 会丢掉 `speaker`（legacy `models.py:34-43`）—— 照旧保留，测试断言它，并**注释说明这是已知行为、修它属于哪一阶段**。
8. **缺陷修复与等价重写分开落。** 别在搬运同一次提交里既等价又改行为。试点做法：`fmt_timestamp` 的树皮语义「改注释不改代码」，缺陷本身不动。
9. **每个公开名字先查它属于哪个包。** 试点踩过：`ChunkPlan` 属 `ingest`（它只在切片规划里用），`Rule`/`Change`/`Issue` 属 `domain`（三处都要同一个类型对象）。**判断标准是「这个名字有几个消费者」而不是「谁先用到它」。**
10. **跨包引用用真包名，不用相对路径。** `from transcript_reimagined.domain import X` —— 相对路径（`from ..domain.models import`）会在包被移动时静默指错地方。
11. **验收测试逐条绑规则 ID。** 用 `@pytest.mark.rule("RULE-0NN")` 标记，未实现的用 `pending_implementation` 标记成 expected-failure 并带规则 ID。这样「哪些规则有归属、哪些还欠」是可清点的事实。

### 搬运后

12. **等价性必须在真实文件上证明一次，不只在单测里。** 试点的纵向切片 `runner` 读元数据 JSON → 规划 → 替换 → 渲染 → **真实写出 `.txt`/`.srt`/`.raw.json` 并回读断言**。这一步抓到的是单测碰不到的接缝问题。

---

## 2. 试点的三道门禁（P2–P6 沿用）

| 门禁 | 命令 | 试点结果 | P6 收口 |
|---|---|---|---|
| 全量测试 | `uv run pytest`（workspace 根） | **542 通过 / 2 跳过 / 41 xfail** | **824 通过 / 2 跳过（UAT 后）** |
| 分层契约 | `lint-imports` | **3 kept, 0 broken** | **13 kept, 0 broken** |
| 端到端 | `python -m transcript_reimagined.runner <meta.json> --out <dir>` | **真实写出三个产物，带词表替换头注释** | 新旧 Pipeline 三产物**逐字节一致** |
| 前端 | `npm test` + `npm run build` | — | **11 条 Node 测试；dist 通过启动门禁** |

**「实际执行的断言数」是门禁的一部分** —— 空跑的套件证明不了任何事。

---

## 3. workspace 的结构约定（P2 起每个新服务照此）

```
modernized/transcript-reimagined/
├── pyproject.toml          ← workspace 根：testpaths / importlinter / ruff 唯一一份
├── conftest.py             ← 极薄：只 import conftest_support，不导出任何成员夹具
├── conftest_support/       ← 共享的路径注入 + 规则过滤插件（唯一一份）
├── domain/  ingest/  post/  runner/
│   ├── pyproject.toml      ← 成员元数据 + workspace 依赖；**不写 pytest 配置**
│   ├── src/transcript_reimagined/<pkg>/   ← 无 __init__.py 于顶层
│   └── tests/
```

**四条不可违反的约定**（每一条都是试点里踩出来的，不是风格偏好）：

1. **顶层名是 `transcript_reimagined`，不是 `transcript`。** 后者会解析到 `.venv` 里遗留的 `site-packages/transcript/` —— **静默跑旧代码而不报错**。
2. **只有 workspace 根有一份 pytest 配置。** 成员各写一份会让 pytest 把 rootdir 判给成员目录，`pythonpath` 相对 rootdir 解析 → 注入静默失效。
3. **只有一份 `pytest_addoption`。** 三个成员的 conftest 各注册 `--rule` / `--list-rules` → 合并后 `ValueError: option names {'--rule'} already added`。
4. **测试文件名不能跨成员重名。** 试点有 8 组重名（`test_rule_011_chunk_budget.py` 同时在 `ingest/` 和 `runner/`），默认 prepend 模式下 pytest 会互相覆盖 → 必须 `--import-mode=importlib`。

---

## 4. 试点实际抓到的四类问题（P2–P6 会再遇到）

### 4a. 并行脚手架的「被结构逼出的复制」

`runner` 把 `domain`/`ingest`/`post` 各拷了一份（**736 行**），因为那三个是普通目录、没有可依赖的已安装包。

**教训**：并行搭多个服务时，**先建 workspace 骨架再发 agent**。否则每个 agent 只能看到自己那一个目录，重复实现是理性的选择。
**更重要的**：这不只是重复 —— 同名模块在同一个进程里被导入两次会产生**两个类对象**，跨包 `isinstance` 静默失效。

### 4b. 并行实施的接口分歧

四个 agent 各自选择 import root：三个用 `transcript_reimagined.*`，`post` 用 `transcript_post`。四个各自内部一致，合起来不一致。

**教训**：并行 agent 之间**必须有强制的共享约定**（命名空间、包布局、依赖方向），不能靠「大家都会想到」。

### 4c. 一个接口被两个 agent 同时实现，结论不同

`domain` 与 `post` 都定义了 `Segment` / `Word` / `fmt_timestamp`；`post` 的版本**额外写对了** `round-half-to-even` 的注释（并说「按 §6b 的裁定」），`domain` 的版本写对了测试。两份都「正确」，但合成一份时两边的**注释与测试各取所长**才是对的。

**教训**：收口时不是「选一个丢掉另一个」，而是**逐字段合并**。

### 4d. 名字对齐：合并后测试引用的名字必须存在

收口过程中发现的缺失/改名：`Rule`（domain 里叫这个，post 里叫 `GlossaryRule`）、`Issue` / `GlossaryIssue`、`ChunkPlan`（在 `ingest` 而非 `domain`）、`is_recoverable` / `retry_delay_s`（domain 没实现，但 runner 测试按 NFR-11 断言）、`load_glossary` / `_wrap` / `MAX_HOT_WORDS`（legacy 的旧名）。

**教训**：合并后必须**按规则卡与 NFR 核一遍每个被引用的名字是否真实存在**，而不是等测试报错。旧名如果被等价性测试引用，保留**同义词别名**而不是改测试 —— 否则新旧对照就断了。

---

## 5. 给 P2–P6 的操作清单

**发 agent 之前**
- [ ] workspace 骨架已建（根 `pyproject.toml` + `conftest_support/`）
- [ ] 命名空间约定写进每个 agent 的 prompt：顶层名 `transcript_reimagined`，子包名 = 服务名
- [ ] 依赖方向写进 prompt，并说明它会被 lint 强制
- [ ] 本阶段要落的规则 ID 与它们的**裁定状态**一起给 agent

**收 agent 结果之后**
- [ ] 内容哈希扫一遍，找真重复（`find . -name '*.py' | xargs shasum | sort | uniq -c -w40`）
- [ ] 同名模块扫一遍（`pathlib.rglob` 按 basename 分组）
- [ ] 逐成员单跑 + 从根合跑，两者都必须绿
- [ ] `lint-imports` 必须 0 broken
- [ ] 端到端在**真实文件系统**上跑一次并回读断言

**每阶段结束**
- [ ] 规则 ID 覆盖盘点：本阶段的规则是否都有测试、哪些还是 xfail
- [ ] 本阶段引入的行为变更逐条署名
- [ ] 更新本文件：新的门禁、新的结构约定、被推翻的预期

---

## 6. 试点推翻了什么（诚实记录）

1. **预期**：`pythonpath` ini 选项能让四个成员互相导入。**实际**：它相对 rootdir 解析，而 rootdir 会被成员自己的 pytest 配置抢走 —— 改成在根 `conftest.py` 里显式 `sys.path.insert`。
2. **预期**：四个服务的测试可以直接合跑。**实际**：需要同时解决三类冲突（`--rule` 重复注册、8 组同名测试文件、根与成员 `conftest` 同名遮蔽）。**并行脚手架的合并成本不在代码，在测试基建。**
3. **预期**：把 `runner` 的副本删掉、import 改指真包就完事。**实际**：还需要给真包补 6 个被引用的名字（其中 `is_recoverable` / `retry_delay_s` 是规则卡里有、实现里漏的 NFR-11 常量）。

---

## 6b. P2–P6 追加的教训（全部踩过）

1. **测试 helper 不能跨成员重名。** `orchestrate/tests/_fakes.py` 与 `web/tests/_fakes.py` 在 `importlib` 模式下共享模块名，后加载的成员会拿到前一个成员的模块。改成 `orchestrate_fakes.py` / `web_fakes.py`。
2. **ruff 按成员解析配置。** 根 `pyproject.toml` 的 `per-file-ignores` 不会作用于成员文件；`B008`（FastAPI `Depends`）与 `SIM118`（sqlite3.Row）的豁免必须写在各成员的 `pyproject.toml`。
3. **`Config` 的默认 `state_db` 指向用户真实库。** 测试夹具必须显式传 `state_db=tmp_path/...`；漏传会让子进程写进 `~/Documents/Transcript/state.db`（本项目踩过一次，已清理）。
4. **通用 `dist/` 忽略会吞掉前端产物。** 服务启动的硬门槛要求提交 `web/src/.../static/dist`，必须在 `.gitignore` 里显式放行。
5. **包 `__init__` 不要 re-export 与子模块同名的 `main`。** 否则 `python -m pkg.main` 会触发 runpy 的「found in sys.modules」警告；控制台脚本直接指向 `pkg.main:main`。
6. **前端修复要留静态断言。** Q1/Q2/Q4/Q5/Q6/Q10 是行为修复，但 React 单测成本高；在 `web/tests/test_frontend_source.py` 里对关键字符串做断言，能防回退。
7. **进程级续跑要真杀进程。** `test_process_kill.py` 用子进程 `os._exit(9)`，父进程重新打开同一个 `state.db` 验证分片 0 未重跑 —— 新建一个 Pipeline 实例不算「杀进程」。
8. **`uv sync` 不等于「能跑」。** 虚拟 workspace 要 `uv sync --all-packages` 才安装全部成员；而成员的 wheel 包根必须写成 PEP 420 命名空间根 `src/transcript_reimagined`，写成子包目录会让 editable 安装只把该目录放进 `sys.path`。普通测试用 `PYTHONPATH` 导入，完全看不见这两类错。
9. **`[project.scripts]` 会吞掉后面的键。** 把 `dependencies` 写在 scripts 表之后，TOML 合法、测试全绿，但 hatchling 打包时报 `Object reference ... must be a string`。`web/tests/test_workspace_packaging.py` 现在钉住这一类错误。
10. **真实模型的字节等价只在编排层成立。** 同一音频、同一模型 ID，mlx-audio 0.5.4 → 0.5.9 会产生少量词差（实测相似度 99.6%）。方案书里的「逐字节一致」证据是编排层用确定性假引擎做的，不能外推到推理层。
11. **端到端要用真实模型点一遍。** 渲染器单测全绿，但装配层把 `segments` 丢给了 `to_txt(..., None)`，`.srt` 有说话人而 `.txt` 没有；`language="auto"` 则直接让任务失败。两者都只有真实 UAT 能抓到。
12. **UAT 的音频必须先复制到 `/tmp`。** 产物默认写在源文件同目录；直接拿用户 `uploads/` 里的文件跑，会原地覆盖已有产物（本次踩过，已用 legacy 重跑恢复）。

---

## 7. 本阶段产出的产物清单

| 产物 | 位置 |
|---|---|
| 四个成员包（541 断言） | `modernized/transcript-reimagined/{domain,ingest,post,runner}/` |
| workspace 根（配置与共享插件） | `modernized/transcript-reimagined/{pyproject.toml,conftest.py,conftest_support/}` |
| 命名空间统一脚本（可重跑、可审计） | `unify_namespace.py` |
| 脚手架评审记录 | `analysis/transcript/SCAFFOLD_REVIEW.md` |
| 死代码删除清单（含恢复方式） | `analysis/transcript/DEAD_CODE_REMOVED.md` |
| 行为基准 | `analysis/transcript/BASELINE.md` |