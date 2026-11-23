# Phase E 脚手架评审 — transcript-reimagined

> **收口已完成（2026-10-17）。** 本文件 §5、§8 的两项决定已按「由主控选最优方案」执行：
> 权威版本地保留 + `runner` 改 import 真包、加 uv workspace、`post` 改名、
> 删掉 736 行副本、补 `import-linter`（3 条契约全绿）。`modernized/` 已纳入 git 跟踪
> （只排除可再生的两个 HTML 报告）。最终：**541 通过 / 3 跳过 / 41 xfail**，
> 分层契约 3 kept / 0 broken。过程与教训写进了 `PLAYBOOK.md`。
> 下文 §3–§5 保留的是**收口前**的记录，用于追溯问题成因。


**日期**：2026-10-17
**Run**：`wf_b96c9768-162`（4 个 agent、556k token、26 分钟、零失败）
**评审人**：会话主控（不是产出脚手架的 agent —— 每一处结论都对着磁盘上的代码核过）

---

## 1. 四个服务都建起来了，各自自测通过

我用主仓库的 3.12 venv 逐个跑了它们的验收套件（`PYTHONPATH=src pytest tests -q`）：

| 服务 | 通过 | 跳过 | xfail | 说明 |
|---|---:|---:|---:|---|
| `domain` | 95 | 0 | 0 | 零 pending —— 两条规则（RULE-025 / RULE-059）全部落地 |
| `ingest` | 124 | 2 | 18 | xfail = Phase 3 的规则（RULE-001 等） |
| `post` | 122 | 0 | 19 | 7 条规则全部落地 |
| `runner` | 200 | 1 | 4 | 纵向切片 |
| **合计** | **541** | **3** | **41** | **实际执行 544 个断言，不是空跑** |

两个数据点值得单独说：

- **`domain` 写出了 15 个「零依赖边界检查」**，用来机器化守住「`domain` 不 import 任何第三方、也不 import 同仓其他包」这条 —— 正是架构评审 M2/M3 要求的强制机制。虽然用测试而不是 import-linter 实现，但**是活的**：`domain/pyproject.toml` 的 `dependencies = []` 属实。
- **`domain` 写了 8 个「与 legacy 逐字节等价」的检查**，直接 import `legacy/transcript` 的 `models`/`errors` 对比输出。这是 Phase 1 exit criterion「逐字节一致」的直接证据。

---

## 2. 纵向切片是真的端到端跑通了

Phase 1 改纵向切片的全部理由就是「让试点碰到真实接缝」。我实测了两次，**不是看它自报**：

**第一次（无词表）**：读元数据 JSON → `chunking` 规划出 5 片 → 渲染 → 写出三个文件。

```
plan: 5 片（min_s=30.0 max_s=120.0 overlap_s=0.5）
products: ['raw_json', 'srt', 'txt']
audio.srt  112 B   audio.txt  47 B   audio.raw.json  1460 B
```

**第二次（带词表，故意加了一条会在分片内重复的规则）**：

```
$ cat meeting.txt
# 词表替换（原始转写见 .raw.json）：集成→集诚 ×2，艾麦→集诚 ×1
我们把集诚做完了
集诚下周一开会

$ head -4 meeting.srt
# 词表替换（原始转写见 .raw.json）：集成→集诚 ×2，艾麦→集诚 ×1

1
00:00:00,000 --> 00:00:04,000
```

`.raw.json` 里 `merged_text_before_glossary` 保留替换前原文、`glossary_changes` 记 `[{wrong,right,count}]` —— **RULE-132 三条要求（双产物都出头注释、保留替换前原文、记录变更数组）全部在真实文件上成立**，不是只在单测里成立。

这一步的价值正是「碰到接缝」：它穿过了文件 I/O、跨包 import、产物落盘。方案书要求试点验证的东西，这次是真验了。

---

## 3. ⚠️ 一个必须先解决的缺陷：`runner` 把三个包各拷贝了一份

**这不是 4 个 agent 之间的协调失误，是一个 agent 的越界。** 我核查了内容哈希：

```
chunking.py : ingest/.../ingest/chunking.py    vs runner/.../ingest/chunking.py       两份
glossary.py : post/src/transcript_post/...     vs runner/.../post/glossary.py         两份
render.py   : post/src/transcript_post/...     vs runner/.../post/render.py           两份
models.py   : domain/.../domain/models.py      vs runner/.../domain/models.py         两份
errors.py   : domain/.../domain/errors.py      vs runner/.../domain/errors.py         两份
```

共 **736 行**是第二份实现。`runner` 自己的 `cli.py` **没有**跨服务 import，而是 `from ..domain.models import ...` / `from ..ingest.chunking import plan_chunks` / `from ..post.render import to_srt` —— 全都指向它**自己目录内的副本**。

**为什么必须改，不是风格问题**：四个服务在同一个 import root 下各发行一份 `transcript_reimagined` 时，`python -m pytest` 从不同 cwd 启动会按 `sys.path` 顺序**解析到不同的那份**。同一名字的两个模块在同一个进程里被导入即产生两个类对象，跨包 isinstance 会静默失效。这与 DDD 无关，是命名空间卫生。

**成因可以理解**：`runner` 没有可依赖的已安装包 —— 另外三个服务是普通目录，没有 workspace 文件把它们串起来。它是**被结构逼的**，不是偷懒。

---

## 4. 第二处必须改的：import root 不统一

| 服务 | import root |
|---|---|
| `domain` | `transcript_reimagined.domain` |
| `ingest` | `transcript_reimagined.ingest` |
| `runner` | `transcript_reimagined.*`（自带 domain/ingest/post） |
| `post` | **`transcript_post`** ← 不一致 |
| `web` / `ui`（后建） | — |

`domain` 的 agent 报告了一个我没想到但确实存在的坑：**`import transcript.domain` 会解析到 legacy 包在 `.venv` 里的 `site-packages/transcript/`**，因为根 `pyproject.toml` 与 `.venv` 里装着 legacy 的 `transcript`。它按名字会命中**旧代码**而不报错 —— 静默跑错代码。

所以根必须是 `transcript_reimagined`，但 `post` 用了 `transcript_post`。

---

## 5. 我建议的收口方式（需要你定，因为影响后续每个阶段）

**权威版本地保留在各服务目录里，`runner` 改为真正 import 它们** —— 不合并目录。

```
modernized/transcript-reimagined/
├── pyproject.toml            ← 新增：uv workspace
├── src/transcript_reimagined/  ← 统一命名空间（唯一发布根）
│   ├── domain/   (来自 domain/)
│   ├── ingest/   (来自 ingest/)
│   └── post/     (来自 post/，从 transcript_post 改名)
├── runner/       ← 薄壳：cli + metadata + products + 自己的纵向切片测试
└── tests/        ← 跨服务的端到端 / 等价性 / 架构约束测试
```

要做的事：

1. 加根 `pyproject.toml` 声明 `[tool.uv.workspace]`，四个成员包可相互 import；
2. `post` 的 `transcript_post` → `transcript_reimagined.post`（**30 处引用**）；
3. **删掉 `runner` vendored 的 736 行**，把 `cli.py` 的 import 改指真包；
4. 补 `import-linter`（架构 §3 要求的分层契约）—— 现在**一个都没装**，`yaml` 也没装；
5. `runner/tests/` 里重复的规则测试（`test_rule_011_chunk_budget.py` 等）保留 —— 它们测的是**跨包集成**，与 `ingest/tests/` 的单元测试不重复，这是有价值的重叠。

**代价**：改 30 处 import + 搬三个目录 + 加一个 workspace 文件。**收益**：Phase 2 起每个新服务都能真的 import 已建好的包，而不是再拷一份。

**我的判断是这件事应当在 Phase 1 结束前做完** —— 因为 Phase 1 的 exit criterion 包含「`run` 入口的产出与 legacy 逐字节一致」，而一个带重复实现的 `runner` 让这条证据的可信度打折（它证明的是副本的等价性，不是真包的）。

---

## 6. 报给工作流的 `notScaffolded: ["runner"]` 是误报

`runner` **实际建出来了**，200 个测试通过，端到端跑得通。工作流的 `notScaffolded` 与 `scaffolded[]` 里多出来的 `"runner (Phase 1 vertical slice — transcript-reimagined)"` 这个标签说明它按名字匹配失败 —— 它把结果按名字记成 `runner`，但服务列表里的名字对不上它自己返回的标识。这是编排层的小 bug，**不影响产出**。

---

## 7. 三条架构层发现（不阻塞，但要记账）

1. **`Segment.shifted()` 会丢掉 `speaker`**（legacy `models.py:34-43`，`shifted` 重建 `Segment` 时没传 `speaker`）。`domain` 的 agent **如实保留了它并用测试钉住**。但这是一个潜在冲突：Phase 3 接通说话人分离后，只要走了 `shifted()`，说话人标签就会消失。**已记入 Phase 3 的决策点**。
2. **`domain` 里跑了两次 `__init__.py` 的行数不一致**（34 vs 49 行）—— 是两份实现的 API 超集关系，不是内容相同。修 §5 时自然消解。
3. **`modernized/` 被 `.gitignore` 忽略**（第 28 行，与 `legacy/`、`analysis/` 并列）—— 这是我在 `modernize` 第一步自己加的。**脚手架是产物，不是草稿**，需要决定是否纳入版本控制。见下。

---

## 8. 曾需要决定的两件事（已定）

1. **§5 的收口**：按我建议的（权威版本地保留 + runner 改 import + 加 workspace + 补 import-linter），还是有别的偏好？
2. **`modernized/` 是否纳入 git**：现在它被忽略。脚手架有 541 个通过的断言和 `PLAYBOOK.md`，我倾向**纳入**（去掉 `.gitignore` 里的 `modernized/`，`legacy/` 与 `analysis/` 保持忽略）。

在你答复之前我不动这些文件 —— 它们现在是可用状态，收口是**重构**不是修复，值得你先看一眼。