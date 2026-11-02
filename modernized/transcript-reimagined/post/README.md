# post —— 后处理（对齐 · 去重 · 词表 · 渲染 · 产物）

`modernized/transcript-reimagined/post/` —— 重建版 transcript 的 `post` 服务。
形态按 `REIMAGINED_ARCHITECTURE.md` §2 的模块边界：**模块包，不是部署单元**，
跑在同一条单进程里（模型进程内缓存，NFR-1）。

## 本阶段（Phase 1）的范围

架构 §5 的落地表把 `post/` 在 Phase 1 限定为 **只含 `glossary.py` + `render.py`**：

| 模块 | 状态 |
|---|---|
| `glossary.py` | 已实现（RULE-021 / 022 / 060 / 132） |
| `render.py` | 已实现（RULE-062 / 135 / 136） |
| `products.py` | 已实现（RULE-132 的产物面；落盘位置由调用方给定） |
| `contracts.py` | 已实现（词表与产物预览的 HTTP 边界形状，供 `web` 调用） |
| `run.py` | 已实现（Phase 1 的最小纵向切片入口，见架构 §5） |
| `align.py` | **Phase 3** —— 只有常量与签名，调用即 `NotImplementedError` |
| `merge.py` | **Phase 3** —— 同上（含 P0-1） |

`domain.py` 只声明 post 自己消费的最小词汇表（字段名与 `AI_NATIVE_SPEC.md` §2 的 ER 图一致）。
架构里 `domain/` 是独立包、由另一个服务并行脚手架，post **不复制它的实现**；
Phase 3 落地 `align`/`merge` 时这两份声明应当收敛成一份。

## 验收测试

`tests/acceptance/` 一条规则一个文件，规则卡的具体 Given 逐条落成可执行断言：

| 文件 | 规则 | 说明 |
|---|---|---|
| `test_rule_060_glossary_grammar.py` | RULE-060 | 用规则卡的 6 行样本；含 6 种分隔符与 `#` 注释边界 |
| `test_rule_021_hot_words.py` | RULE-021 | 期望值 `['小新','集成','集诚','艾麦']`；上限断言 80 词 × 40 字符 |
| `test_rule_022_replacement_order.py` | RULE-022 | `集成→集诚` + `成→诚`、`我们把集成做完了` → `我们把集诚做完了`，changes 记 1 次 |
| `test_rule_132_glossary_trace.py` | RULE-132 | 三产物端到端落盘：`.txt`/`.srt` 头注释 + `.raw.json` 的原文与变更表 |
| `test_rule_062_srt_guard.py` | RULE-062 | `[空文本, (12.0,20.0), (30.0,29.0)]` → 抛 ValueError、编号只数存活行 |
| `test_rule_135_srt_wrapping.py` | RULE-135 | 60 字符行、逗号在中点后 3 字符 → 在逗号后断；只折一次 |
| `test_rule_136_speaker_txt.py` | RULE-136 | `speaker_1/speaker_1/speaker_2/None` 四段的分块输出与两条兜底 |
| `test_artifact_selection_rule_061.py` | RULE-061（附带） | 无时间轴不写 srt；`artifact=txt` 不再写空 `.srt`（已署名行为变更） |
| `test_interface_contracts.py` | 接口契约 | 词表读写与产物预览的形状、200 000 字符上限、上传面无残留 |
| `test_phase3_align_merge.py` | RULE-001/008/009/010/023/024 | **expected-failure（xfail）**，Phase 3 落地后转绿 |

跑：

```bash
pytest                       # 122 passed, 19 xfailed
pytest --list-rules          # 按规则 ID 清点覆盖：哪些已实现、哪些还是 pending
pytest --rule=RULE-060       # 只跑一条规则的验收测试
ruff check . && ruff format --check .
lint-imports                 # 两条 import-linter 契约（无环性可检查）
```

`--list-rules` 的输出是给上级编排的证据：每条规则被多少用例覆盖、是否有
`pending_implementation`（预期失败/跳过）用例，都不用去读文件名猜。

`tests/acceptance/test_phase3_align_merge.py` 的每条 xfail 都带规则 ID，并在 docstring 里
写明**为什么要用修正后的判据** —— P0-1 的规则卡例子是错的（3 字符重叠检测为 0），
判据必须用 ≥4 字符的重叠（`AI_NATIVE_SPEC.md` §5.4）。

## 跑一次真实产物（Phase 1 的纵向切片）

```bash
transcript-post-run --input plan.json --out-dir out --stem meeting
```

`plan.json` 的字段见 `run.py` 的模块 docstring。它会写出真实的 `.txt` / `.srt` / `.raw.json`。
`artifact=srt` 而没有任何段落时**拒绝出产物**（RULE-061），不写空文件充数。

## 边界（刻意不做的事）

- **不做 I/O 位置决策**：产物路径由 orchestrate 的单点决策给出（架构 §2），
  `products.py` 只负责写。
- **不读凭据、不读配置**：`config` 与配置优先级（RULE-105）属 Phase 2，Phase 1 的范围约束
  明确排除它。本服务里没有 `config.env`、没有任何密钥字面量（NFR-4）。
- **不碰网络、不碰 SQLite、不引 FastAPI**：传输在 `web`，落库在 `state`。
- **不新增能力**：本次是重建不是加功能（架构 §7b）。除已裁定放行的 C8 相关语义外，
  任何新引擎、新路由、新依赖都不在本服务的权限内。