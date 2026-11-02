# runner —— Phase 1 纵向切片入口

`modernized/transcript-reimagined/runner/` 是 transcript 重建后的**第一个可执行服务**。
它不是终点形态的 `orchestrate`（那是 Phase 5），而是架构 §5 特意设计的那一步：
**让试点碰到真实接缝**。

背景：方案书原定 Phase 1 只搬 5 个纯函数模块（`models` `errors` `chunking` `glossary`
`render`）。`REIMAGINED_ARCHITECTURE.md` v2 指出那样做「一条真实接缝都碰不到」，因此
Checkpoint 2 裁定改为**三个包 + 一个最小 `run` 入口**。本目录就是那次裁定的落点。

## 它做什么

读一份**音频元数据 JSON**（时长、语音区间、待渲染文本）→ 调
`ingest.plan_chunks` 规划分片 → 调 `post.glossary` 做确定性替换 → 调 `post.render`
渲染 txt 与 srt → 写一份最小的 `.raw.json` → 把文件写到输出目录。

真实读文件、真实跨包 import、真实落盘。就这些。

## 它不做什么（范围纪律，架构 §5 / §7b）

不含 `config`、不含 `store`、不含 `pipeline`、不含 `web`；不含真实 ffprobe / VAD /
引擎调用；不引任何运行时依赖（只用标准库）。这些分别属于 Phase 2/3/4/5/6。
`tests/test_architecture.py` 用 AST 检查把这些边界钉住，而不只是写在文档里。

## 目录结构

```
runner/
├── pyproject.toml                 # 栈与强制机制（ruff / pytest / import-linter）
├── README.md
├── LEGACY_DEVIATIONS.md           # 与 legacy 的不一致之处，逐条署名（方案 §6 门禁）
├── src/transcript_reimagined/
│   ├── domain/                    # 无障碍公共词汇：models + errors（零 I/O、零第三方依赖）
│   ├── ingest/                    # 只回答「该切成哪几片」：chunking
│   ├── post/                      # 只作用于「已拿到的文本与时间轴」：glossary + render
│   └── runner/                    # 入口：metadata 读取 · products 单点落盘 · run · cli
└── tests/                         # 每个行为契约规则一个文件，文件名带规则 ID
```

分层方向：`runner → {ingest, post} → domain`。

## 技术选型（与架构一致）

| 项 | 选择 | 依据 |
|---|---|---|
| 语言 | Python 3.12（`>=3.12,<3.13`，硬钉） | 架构 §3；`mlx-*` 是 Apple Silicon 专属 |
| 运行时依赖 | 无 | 本切片要碰的是文件 I/O 与 import 图，不是第三方库 |
| 测试 | pytest | 与 legacy 一致，便于把 264 条断言搬过来（Q13） |
| Lint | ruff | 与 legacy 一致 |
| 依赖方向 | `import-linter`（dev）+ AST 兜底检查 | 架构 §3：「无环性从口号变成可检查事实」 |

## 跑起来

```bash
cd modernized/transcript-reimagined/runner

# 测试（不需要安装包，conftest 会把 src/ 加进 sys.path）
PYTHONPATH=src python -m pytest -q

# 分层契约（可选，需要 dev 依赖）
uv sync --group dev        # 或 pip install import-linter
PYTHONPATH=src python -m pytest -q tests/test_architecture.py

# 一次真实的端到端运行
PYTHONPATH=src python -m transcript_reimagined.runner \
    tests/data/metadata.sample.json --out /tmp/runner-out --json
```

退出码：`0` 成功；`2` 元数据/参数问题；`3` 产物被拒绝（例如要 srt 而引擎没有时间戳）。
后两种情况下**不写任何文件**。

## 元数据 JSON 的契约

```json
{
  "task_id": 42,
  "path": "audio/会议.m4a",
  "duration_s": 300.0,
  "spans": [[0.0, 60.0], [61.2, 300.0]],
  "merged_text": "待渲染的正文",
  "segments": [{"start": 0.0, "end": 20.0, "text": "…", "speaker": "speaker_1"}],
  "chunk": {"min_s": 30.0, "max_s": 120.0, "overlap_s": 0.5},
  "engine": "dashscope",
  "has_timestamps": true,
  "artifact": "srt",
  "mode": "online"
}
```

`tests/data/metadata.sample.json` 是同一份契约的可执行样例（有测试断言它与夹具一致）。

### 安全边界

- 这份文件是**元数据**，不是凭据载体。任何疑似密钥的字段名（`api_key` / `secret` /
  `token` / `password` / `credential`）都会被**拒绝**，而不是读进内存。
- 凭据（若后续阶段需要）只从环境读，占位形如 `${DATABASE_URL}`；测试夹具一律是同形状
  的假值（例如 `sk-fake-not-a-real-key-0000`）。**没有任何 legacy 凭据字面量进入本服务。**

## 验收测试

每个行为契约规则一个文件，文件名带规则 ID；规则 ID 也出现在每个用例的文档字符串里，
便于按 ID 反查 `AI_NATIVE_SPEC.md` §5.2。

| 文件 | 规则 | 状态 |
|---|---|---|
| `test_rule_011_chunk_budget.py` | `RULE-011` 分片预算与长度不变量 | 已实现 |
| `test_rule_012_silence_cuts.py` | `RULE-012` 切点优先落静音 | 已实现 |
| `test_rule_059_http_classification.py` | `RULE-059` HTTP 失败分类 | 已实现 |
| `test_rule_060_glossary_grammar.py` | `RULE-060` 词表语法与条目校验 | 已实现 |
| `test_rule_021_hotwords.py` | `RULE-021` 热词列表组成与上限 | 已实现 |
| `test_rule_022_replacement.py` | `RULE-022` 替换顺序与变更计数 | 已实现 |
| `test_rule_025_timestamp.py` | `RULE-025` SRT 时间戳格式与取整 | 已实现 |
| `test_rule_062_srt_validation.py` | `RULE-062` 倒序拒绝与编号连续 | 已实现 |
| `test_rule_132_artifacts.py` | `RULE-132` 替换痕迹写进产物 | 已实现（真实文件回读） |
| `test_rule_135_srt_wrapping.py` | `RULE-135` SRT 长行折行 | 已实现 |
| `test_rule_136_speaker_txt.py` | `RULE-136` 说话人分块 | 已实现 |
| `test_runner_end_to_end.py` | 纵向切片本身 | 已实现（临时目录真实落盘 + 回读 + 子进程） |
| `test_architecture.py` | 分层 contract 与范围纪律 | 已实现 |
| `test_legacy_equivalence.py` | 与 legacy 的**双执行 diff** | 已实现（基准不在场时跳过并说明） |
| `test_phase_deferred.py` | `RULE-001` `RULE-072` `RULE-063` `RULE-133` | **xfail**，原因写明所属阶段 |

标记为 `xfail` 的用例一律写明「因哪个包尚不存在而失败、由哪个阶段兑现」——
**不静默跳过**。当前结果：`200 passed, 1 skipped, 4 xfailed`。

`test_legacy_equivalence.py` 把只读快照 `legacy/transcript/` 当预言机用：同一组输入喂给
新旧实现，比较输出。它只 import 与调用纯函数，不读凭据、不写文件、不碰 `state.db`；
快照不在场时跳过并说明「基准不在场，没查」。

## 人工验一次

```bash
PYTHONPATH=src python -m transcript_reimagined.runner \
    tests/data/metadata.sample.json --out /tmp/runner-out
```

产出（`--out` 目录下三个文件）：

```text
2026-10-17 会议.txt        [speaker_1] 我们把集成做完了。请确认艾麦的报价。
                          [speaker_2] 好的。
2026-10-17 会议.srt        1 / 00:00:00,000 --> 00:00:20,000 / 我们把集成做完了。请 …
2026-10-17 会议.raw.json   分片计划 4 片、未替换原文、final_text、glossary_changes
```

（从 ``/tmp`` 直接跑会撞上别人放在那里的 ``dis.py`` 之类的同名模块 —— 在干净目录里跑。）

## 下一步（不在本切片）

逐字节等价已经由 `test_legacy_equivalence.py` 钉住六组输入；剩下的是**端到端**那一半：
让 legacy 的 `Pipeline` 真的跑完一次（需要 SQLite 与引擎），把产出与 `run()` 的产出对比。
那属于 Phase 1 的 exit criterion 收尾，需要 Phase 2 的 `store` 就位。