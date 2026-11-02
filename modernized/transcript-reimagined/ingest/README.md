# ingest — 音频入料：探测 · 归一化 · 切片规划 · VAD

`transcript` 重建版（`modernized/transcript-reimagined/`）的一个**模块包**，不是部署单元。
整个系统是单进程模块化单体（见 `analysis/transcript/REIMAGINED_ARCHITECTURE.md` §0/§1）。

- 旧模块：`legacy/transcript/src/transcript/audio.py` · `vad.py` · `chunking.py`
- 阶段：Phase 1（领域内核试点）。**本阶段只含 `chunking`**；`audio` / `vad` 属 Phase 3
- 承载规则：`RULE-011`（分片预算与长度不变量）、`RULE-012`（切点优先落静音）；
  另有三条属本包但归 Phase 3：`RULE-028`（VAD 门控）、`RULE-049`（工作副本契约）、
  `RULE-050`（输入资格检查）

它只回答「音频是什么、该切成哪几片」，不回答「转写结果怎么落盘」——
落盘决策在 `orchestrate` 的单点决策里（架构 §2）。

## 为什么切片规划值得单独一个包

`chunk.duration <= max_s` 是**物理不变量**，不是审美问题：在线引擎有单次硬限
（百炼 300s），片长了会被上游直接拒 —— 这条是 300s 上限不被击穿的**唯一**保障。
实现方式是把重叠算进预算（`inner = max(MIN_INNER_S, max_s - overlap)`），而不是
算在预算外。切片错了后面全错，所以它是纯函数、零副作用、可独立单测。

## 边界（机器可验证）

依赖图（架构 §2，v2 砍掉了 `engines → ingest` 那条边）：

```
domain <- ingest <- orchestrate
```

`tests/test_ingest_boundaries.py` 用 AST 扫描 + 隔离子进程导入钉住四件事：

1. 只 import stdlib、`domain`、本包 —— 逐文件**精确**白名单，加一行 import 就会红；
2. 纯规划层不碰任何做 I/O 的 stdlib 模块（`os`/`subprocess`/`sqlite3`/…）；
3. `pyproject.toml` 的 `dependencies` 为空、`requires-python = ">=3.12,<3.13"`、
   wheel 只打包本服务；
4. 隔离解释器里导入不会拉进第三方，也**不会**连带加载遗留 `transcript` 包
   （重建版与旧树并存；若本包开始 import 旧树，等价性对比就会变成同义反复）。

## 公开面（API stub，对应规格的接口契约）

| 名称 | 形态 | 契约 |
|---|---|---|
| `ChunkPlan(min_s=30.0, max_s=120.0, overlap_s=0.5)` | frozen dataclass | 切片预算；派生 `overlap` / `half` / `inner` / `target`；非法参数在**构造时**抛 `ValueError` |
| `MIN_GAP_FOR_CUT_S = 0.15` · `MIN_INNER_S = 1.0` | 常量 | 两个门控常量是契约的一部分 |
| `plan_chunks(spans, duration, *, min_s, max_s, overlap_s)` | 纯函数 | `RULE-011` / `RULE-012` 的实现入口 |
| `plan_chunks_with(spans, duration, plan)` | 纯函数 | 同一实现的预算对象入口（纯转发） |
| `audio.probe` / `to_wav16k` / `to_mp3_64k` / `cut` / `verify` / `require_ffmpeg` | Phase 3 占位 | 调用即 `NotImplementedError`，不提供半成品 |
| `vad.speech_spans` / `merge_gaps` / `load_vad` | Phase 3 占位 | 同上 |

`audio` / `vad` **不**从包根 re-export：它们的调用会抛 `NotImplementedError`，
从包根导出会让人误以为已经可用。

## 跑测试

```
cd modernized/transcript-reimagined/ingest
python -m pytest                     # 需要 pytest>=8；不需要安装本包（pyproject 里配了 pythonpath）
python -m pytest --list-rules        # 规则覆盖与 pending 状态一览
python -m pytest --rule=RULE-012     # 只跑一条规则的验收测试
```

`conftest.py` 会把**兄弟服务 `domain` 的 `src/`** 也放进 `sys.path`：
`transcript_reimagined` 是 PEP 420 命名空间包，两个片段要同时在路径上才能合并。

## 覆盖与 pending

| 规则 | 用例 | 状态 |
|---|---|---|
| `RULE-011` 分片预算与长度不变量 | 34 + 等价性 41 | 已实现 |
| `RULE-012` 切点优先落静音 | 20 | 已实现 |
| `RULE-028` VAD 门控 | 6 | **pending**（Phase 3，`xfail` + `pending_implementation`） |
| `RULE-049` 工作副本契约 | 5 | **pending**（Phase 3） |
| `RULE-050` 输入资格检查 | 7 | **pending**（Phase 3） |

pending 用例一律**显式标注**（`xfail` + `@pytest.mark.pending_implementation("RULE-XXX")`），
不静默跳过 —— 这样「哪些规则还没落地」可以被 `pytest -m pending_implementation`
或 `--list-rules` 一次问出来。

## 等价性证据

`tests/test_equivalence_with_legacy_chunking.py` 按**文件路径**（`importlib`）加载
`legacy/transcript/src/transcript/chunking.py` 并做差分：32 组固定输入 + 400 轮固定种子的
随机扫描，逐字节比对 `(index, start, end)` 与 `ValueError` 文本。找不到旧树时整文件跳过，
本包自己的验收测试不依赖旧树。

读旧树是**只读**的（`legacy/transcript/` 全程冻结不改）。

## 实现时不得放宽的常量与顺序

- `overlap_s` 算在预算**内**（`inner = max_s - overlap`）。算在预算外 = 每片超出
  `overlap_s`，百炼场景直接击穿 300s。
- `duration <= 0` 的返回**先于**参数校验：`plan_chunks([], 0.0, min_s=0, max_s=0)` 返回
  `[]` 而不是抛错。调换顺序与 legacy 分道扬镳（有测试钉住）。
- 语音区间**不去重**：重复区间各算一次 `acc`，会让切点前移。去重是行为变更，不是重构。
- 两个 clamp：`cut >= cursor + MIN_INNER_S` 且 `cut <= duration`。
- Phase 3 的 `audio` 里，ffmpeg/ffprobe 的**位置参数前必须加 `--`**
  （架构 §6，CWE-88）—— 这是加固项，不是 legacy 行为。

## 安全边界

- 没有任何凭据、真实录音或私有素材进入本包或测试夹具：切片规划的输入就是浮点数。
- 本包不读环境变量、不读配置文件（架构 §2：`config` 是单独一层）。
- `state.db` 不在这里（那属 `state/`，且它是唯一写入者）。