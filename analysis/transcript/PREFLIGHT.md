# PREFLIGHT — transcript

**日期**：2026-10-17
**代码位置**：`legacy/transcript/` —— 工作区内的真实目录（不是符号链接），由 `git archive HEAD`（提交 `e0e29c0`）导出，167 个受版本控制的文件全在其中。**只读，本次预检没有改动它一个字**（已核对：`legacy/` 下无 `__pycache__`、无 `.pytest_cache`）。

---

## Answers（人的回答 —— 这些不在源码里）

### 1. Scope —— 这份代码是完整系统，还是更大代码库的一部分？

> **完整系统**

佐证与 Check 6 一致：快照覆盖了全部 167 个受版本控制的文件，没有上游/兄弟模块。

### 2. Build & test locally —— 这台机器能恢复依赖、构建并跑测试吗？完整流水线大概多久？

> **能，本机能完整跑**
>
> （用户未给具体时长。）

**实测补充**（不是用户回答，是本次预检验证的）：后端 264 通过 / 2 失败 / 10 跳过，**8.9 秒**；前端单元测试 11/11 通过；`tsc --noEmit` 干净。依赖已装（`.venv` 用本机 Python 3.12.11，`frontend/node_modules` 在位）。全量流水线在本机是秒级，不是分钟级。

### 3. Bespoke build infrastructure —— 有没有外人猜不到的、团队特有的构建或依赖机制？

> **没有，都是公开工具链**

佐证：依赖全部来自公开 PyPI 与公开 npm；锁文件 `uv.lock` 在位；无内部源、无代码生成器、无包装脚本。仓库里**完全没有 CI 定义**（见 Check 3a）。

### 4. Prior attempts —— 以前有人尝试过现代化/重建这个项目吗？结果如何？

> **没有，第一次**

### 5. Off limits —— 这次重建中，有没有什么东西不允许改动？

> **没有禁区**

⚠️ 提醒：「没有禁区」指的是**产品代码**。`legacy/transcript/` 本身对现代化流程仍然是只读快照 —— 它是这次重建的**基准**，不是待改的代码。要改代码，改的是 `modernized/transcript-reimagined/`。用户已确认这一点（AskUserQuestion 的「没有禁区」选项即「整个仓库都可以改」，指的是原仓库没有需要保护的模块）。

---

## Check 6 —— Scope boundary（下游命令最依赖的一项）

**`transcript` 是一个独立仓库，不是切片。**

- **Outbound**：无。快照内对 `transcript.*` 的引用全部在树内解析成功，无指向树外的项目引用或共享 include。
- **Inbound**：无。`legacy/transcript/` 的消费方只有产品仓库自己，没有兄弟模块引用它。

只有 2 个受版本控制的文件落在四个代码目录（`src` `tests` `spikes` `frontend`）之外：

| 文件 | 说明 |
|---|---|
| `.agents/acceptance/PROJECT.md` | 验收标准 —— `extract-rules` 应当读它 |
| `.claude/launch.json` | 本机启动配置，非代码 |

**结论**：不存在「改了会连带打断别人」的节点。重建的切分可以只按 `transcript` 自己的模块边界走，不需要为外部消费者留过渡期。

---

## 检查表

| # | 检查 | 状态 | 发现 | 未绿时的修法 |
|---|---|---|---|---|
| 1 | 技术栈指纹 | ✅ | 见下方「技术栈」 | — |
| 2 | 分析工具 | ⚠️ | `scc`、`cloc`、`lizard` 全缺；`python3` 3.15.0、`node` 22.23.3、`npm` 10.9.9、`uv` 0.8.22、`ffmpeg`、`git` 均在位 | `brew install scc`（补 COCOMO 与复杂度，`assess` 的 LOC 从 `find`+`wc` 退化值升级）；portfolio 分析才需 `pipx install lizard` |
| 3a | 构建定义 | ✅ | 见下方「构建定义」 | — |
| 3b | 构建冒烟（真跑） | ✅ | Level 1：54 个 `.py` 全部 AST 解析通过，0 语法错误。Level 2：用仓库自带 3.12 venv 跑快照自己的测试套件 —— **264 通过 / 2 失败 / 10 跳过 / 8.9s**；前端 `node --test` 11/11、`tsc --noEmit` 干净 | 2 个失败**不是环境问题，是真实缺陷**，见下方「预检发现的第一个 bug」 |
| 4 | 源码完整性 | ⚠️ | 无缺失 include，无无源二进制。两处需要知道：`static/dist/`（前端构建产物）**不在快照、也不受版本控制**，靠 `npm run build` 生成，而 `web/frontend.py` 的 `validate_dist` 是服务启动硬门槛；`~/.config/transcript/{config.env,summary-prompt.txt,glossary.txt}` 是树外配置 | 重建时把前端构建步骤显式建模（原仓库靠 `ensure_frontend` 自动重建）；树外配置是**有意设计**，不是缺失 |
| 5 | 可选上下文 | ⚠️ | 无 APM。**但有真实运行证据**：产品仓库里的 `state.db`（7 MB，本机任务历史）+ `uploads/` 可作 assess 的运行期叠加。版本控制：只有 1 个提交（`e0e29c0`，2026-10-17） | 变更频率风险排序不可用（无历史）。命令这一轮重建，风险排序改用**结构耦合度**而非提交频率 |
| 6 | 范围边界 | ✅ | 独立仓库，见上 | — |
| 7 | 源码防改保护 | ⚠️ | **未发现任何 deny 规则**。项目 `.claude/settings.json` 与 `.claude/settings.local.json` 都不存在；`~/.claude/settings.json` 的 `permissions.deny` 为空（`null`）。`CLAUDE_CONFIG_DIR` 未设置 | 见下方代码块 |

### Check 7 建议加的规则

写入产品仓库的 `.claude/settings.json`（已有 `permissions.deny` 就并进去）：

```json
{ "permissions": { "deny": ["Edit(/legacy/**)"] } }
```

`legacy/transcript/` 是真实目录而非符号链接，所以不需要额外覆盖链接目标。注意 `Edit(/legacy/**)` 只挡 `legacy/`，不会挡 `analysis/` 与 `modernized/` —— 那两处命令要写。

**这行保护不是硬保证**：权限规则只覆盖 Claude 的文件工具和它认得出的 shell 命令（`sed`、`tee`、`>` 重定向），挡不住一个自己打开文件写的脚本。硬保证在操作系统层：只读挂载，或禁止 shell 写入的沙箱。

---

## 技术栈

| 层 | 内容 |
|---|---|
| 后端 | Python **3.12**（`requires-python = ">=3.12,<3.13"`，硬钉在 3.12）；FastAPI ≥0.115 + uvicorn；Pydantic ≥2；httpx；python-multipart；python-dotenv；numpy ≥2.0,<2.5；soundfile |
| 本机模型 | `mlx-audio` ≥0.4.3（Qwen3-ASR）、`mlx-whisper` ≥0.4.3 —— **Apple Silicon 专属**，非 macOS/无 MLX 环境跑不了离线路径 |
| 运行时外部依赖 | `ffmpeg` + `ffprobe`（`audio.require_ffmpeg()` 在启动时检查） |
| 构建 | hatchling；包管理 `uv`（`uv.lock` 在位）；无 CI |
| 前端 | React 18.3 + TypeScript 5.5 + Vite 5.3 + Tailwind 3.4 + shadcn/ui（Radix 系列）+ zustand + react-query + react-router；npm；构建脚本 `tsc && vite build` |
| 测试 | 后端 pytest（标记 `smoke` / `online`）；前端 `node --test`；另有 `tests/test_frontend.py` |

**规模**（`scc` 缺失，用 `find`+`wc` 退算法，仅行数）：

| 区域 | 行数 | 文件数 |
|---|---|---|
| `src/`（产品代码） | 5 264 | 26 |
| `tests/` | 4 773 | 22 |
| `frontend/src` + `frontend/tests` | 3 587 | 25 |
| `spikes/` | 775 | 6 |
| **产品代码合计** | **8 851** | **51** |

最大的几个后端文件：`web/app.py` 743 行、`pipeline.py` 665、`store.py` 412、`summary.py` 373、`config.py` 270。

`spikes/`（775 行，6 个一次性探针 + 一个 workbench）是「可以丢」的候选 —— 用户说没有禁区，`reimagine` 时值得显式决定留不留。

---

## 构建定义（Check 3a）

**没有 CI。** 仓库里没有任何 `.github/workflows/`、`Jenkinsfile`、`azure-pipelines.yml`、`gitlab-ci.yml`、`Makefile` 或 `Dockerfile`。只有两个一次性 shell 脚本，在 `spikes/workbench/`，是 spike 的本地跑法，不是构建入口。

所以「构建定义」就是：

- **`pyproject.toml`** —— hatchling 后端；固定 `requires-python = ">=3.12,<3.13"`；依赖全部公开 PyPI；`[project.scripts] transcript = "transcript.cli:main"`；wheel 额外强制包含 `src/transcript/web/static/dist`。
- **`uv.lock`** —— 真实钉版本的地方。
- **`frontend/package.json`** —— `build: "tsc && vite build"`，`test: "node --test tests/*.test.mjs"`。**没有 `engines` 字段**，但 README 要求 Node 22.12+（用于 Vite 5 / ESM）。
- **README「快速开始」** 是事实上的构建流程：`uv sync` → 前端 `npm ci && npm run build` → `uv run transcript`。

**没有任何 bespoke 机制**：无私有 feed、无 `.npmrc`/`pip.conf`、无代码生成、无包装脚本。与用户回答一致。

---

## 预检发现的第一个 bug（重要 —— 直接关联你选的「顺手修已知 bug」）

跑快照自己的测试套件时，**2 个测试失败，都在说同一件事**：

```
FAILED tests/test_pipeline.py::test_txt_run_does_not_emit_srt
       → assert result.srt_path is None
         实际：PosixPath('.../input.srt')

FAILED tests/test_web.py::test_output_missing_kind_returns_404
       → assert .../output?kind=srt == 404
         实际：200
```

两个测试的名字和文档字符串把意图写得很清楚：

- `test_pipeline.py::test_txt_run_does_not_emit_srt` —— *「txt 任务不该产出半成品 srt（没有时间戳就没资格给 srt）。」*
- `test_web.py::test_output_missing_kind_returns_404` —— 请求一个不存在的产物种类应当 404。

而 `src/transcript/pipeline.py:366` 是**无条件**写 srt 的：

```python
txt_path = self._write(out_dir / f"{stem}.txt", to_txt(...))
srt_path = self._write(out_dir / f"{stem}.srt", to_srt(...))   # ← 没有 artifact == "srt" 判断
```

同一文件在 347 行**有** `artifact == "srt"` 的判断（时间戳缺失时拒绝），说明作者本来知道 `artifact` 该分支，只是落盘这一处漏了。

**这意味着什么**：跑一个「只要 txt」的任务，产物目录里会多出一个 `.srt`；Web 端点也照样 200 返回它。这是真实的代码漂移，不是测试写错 —— 两个独立测试从两个角度断言同一件事。

**交给下游**：`extract-rules` 要把这条记成规则卡（带 `pipeline.py:366`、`tests/test_pipeline.py:174`、`tests/test_web.py:298` 三处引用），`review` 阶段由你拍板确认「测试是对的、代码该改」。这是「顺手修已知 bug」的第一个具体候选。

---

## Ready / Ready-with-gaps 逐命令判定

| 命令 | 判定 | 依据 |
|---|---|---|
| `assess` | ✅ Ready | Check 1 绿、Check 2 只缺 `scc`（LOC/复杂度走退算法，COCOMO 指数偏粗）。装 `scc` 会更准，不装也能跑 |
| `map` | ✅ Ready | `python3` 在位，依赖图全部树内可解析 |
| `extract-rules` | ✅ Ready | 同上，且无缺失 include |
| `brief` | ✅ Ready | 只需要发现产物，不需要工具链 |
| `reimagine` | ✅ Ready | 目标栈 = Python + React，**两者都在本机构建运行成功**（3b Level 2 已证） |
| `verify` | ✅ Ready | `python3` 在位，证明脚本可跑；前端也有可执行的测试入口 |
| `harden` | ⚠️ Ready-with-gaps | `bandit`、`pip-audit`、`semgrep`、`trivy` 全缺。`npm audit` 可用（npm 在位），`ruff` 0.16.7 可用（已是 dev 依赖）。要跑 Python SAST 需装：`uv tool install bandit pip-audit` |
| `uplift` | — 不适用 | 目标不是同栈升版本，是重建 |

---

## 结论

**Not-ready 的项：零。** 6 项检查里 3 项绿、4 项带小缺口（2、4、5、7），没有一项挡住任何命令。

**最值得先做的一件事**：装 `scc`。它是唯一会让 `assess` 的产出**质量下降**而不仅仅是少个功能的东西 —— 缺了它，复杂度与 COCOMO 全靠决策关键字数估算，而这次重建的切分方案正是从 `assess` 的复杂度数据推出来的。

```
brew install scc
```

另外建议在 `assess` 之前把 Check 7 的 deny 规则加上 —— 不是命令的硬要求，但快照目前对文件编辑没有任何自动保护。

**下一步**：

```
/code-modernization:modernize-assess transcript
```