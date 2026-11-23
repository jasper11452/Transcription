# 已接受的差异（逐条署名）

方案书 §6 的门禁：**每一处「已接受的差异」都要署名并写明理由；未署名的差异视为失败。**
本文件就是本服务的差异台账。凡与 `legacy/transcript/` 行为不一致的地方，必须在这里有
一行；`tests/` 里对应的断言也在注释里指回本文件。

默认姿态是**逐字节等价**（Phase 1 的 exit criterion）。下面每一条都是**有意**偏离。

---

## D-1 · `artifact=txt` 不再产出 `.srt`

- **差异**：legacy 无论 `artifact` 是 `txt` 还是 `srt` 都会写 `.txt` 与 `.srt`
  （`pipeline.py:365-366`），txt 任务因此会留下一个空的 `.srt`。
  本服务改为：`artifact=srt` 才写 `.srt`；`artifact=txt` 只写 `.txt`。
- **依据**：人裁定 `RULE-061`「**对，但顺手补齐**」——「`artifact=txt` 时不该写 `.srt`」
  （`RULE_REVIEWS.json`；`MODERNIZATION_BRIEF.md` §7b Q9）。
- **署名**：`REIMAGINED_ARCHITECTURE.md` §2「产物选择必须是单点决策」+ 人工裁定。
- **落点**：`src/transcript_reimagined/runner/products.py::select_products`（唯一决策点）；
  测试 `tests/test_runner_end_to_end.py::test_runner_txt_task_does_not_write_an_srt`。

## D-2 · `.txt` 走 segments 路径，因此**带说话人前缀**

- **差异**：legacy 的 `pipeline.py:365` 调用 `to_txt(final_text, None, ...)`，把 segments
  传成 `None`，于是 `RULE-136` 的说话人分块在正常路径上**不可达**（只有纯文本输出）。
  本服务把 segments 传给 `to_txt`：有 speaker 时输出 `[speaker_1] …`，无 speaker 时
  一段一行。因此基线上的 `.txt` 与 legacy 的 `.txt` **不同**。
- **依据**：`AI_NATIVE_SPEC.md` §5.2 把 `RULE-136`（带说话人的文本输出分块）列为 Phase 1
  必须落成可执行验收测试的规则。要让这条契约可执行，输出路径必须真的能带 speaker。
  `RULE-136` 判据本身给出的期望值就是 `[speaker_1] 你好我们开始`，与 legacy pipeline
  的调用方式互斥 —— 以规则卡为准。
- **署名**：按「P0 之外按所属阶段落地」的门禁，这是一处**行为变更**，因此在此署名。
  若批准者要求 Phase 1 保持逐字节等价，则把 `run()` 里 `segments or None` 改回 `None`，
  并把 `test_rule_136_speaker_txt.py` 改为只测 `post.render` 层（契约测试仍然成立）。
- **落点**：`src/transcript_reimagined/runner/run.py`（带 `# 段落交给 to_txt 是有意的`）。

## D-3 · 切片入口读**元数据 JSON**，不读音频

- **差异**：legacy 用 ffprobe 探测真实音频、用 VAD 求语音区间。本服务从 JSON 读同样的事实。
- **依据**：架构 §5 的范围约束 ——「一个最小 CLI：读一段真实音频的**元数据**」。真实
  `audio`/`vad` 属 Phase 3。
- **署名**：`REIMAGINED_ARCHITECTURE.md` §5（Checkpoint 2 已批准）。
- **落点**：`src/transcript_reimagined/runner/metadata.py`。

## D-4 · `.raw.json` 的分片状态是 `planned`，且不含 `cost_usd` 等字段

- **差异**：legacy 的 `.raw.json` 记录的是**分片执行结果**（`status`/`attempts`/`error`/
  `words`/逐片文本）。本切片不执行引擎调用，因此分片行是**计划**：`status: "planned"`，
  `text: null`，`attempts: 0`。`task_id`/`source`/`mode`/`artifact`/`engine`/`chunk_count`/
  `config` 位置的 `chunk_params`/`merged_text_before_glossary`/`final_text`/`segments`/
  `glossary_changes` 这些**键名与 legacy 对齐**，供下游按 `RULE-034` / `RULE-132` 消费。
- **依据**：架构 §5「写一份最小的 `.raw.json`」；逐字段等价属 Phase 5（`RULE-034`）。
- **署名**：`REIMAGINED_ARCHITECTURE.md` §5。
- **落点**：`src/transcript_reimagined/runner/run.py::_chunk_rows`。

## D-5 · `Segment.shifted()` 仍然丢失 `speaker`（搬运缺陷，未顺手修）

- **差异**：legacy 的 `Segment.shifted()` 构造新 `Segment` 时不传 `speaker`，标签在平移
  后丢失（`models.py:41-50`）。本服务**照搬**了这个行为。
- **理由**：本切片不调用 `shifted()`；修它属于 `diar` 接通的范围（`C8`，Phase 3），
  且 `INTENT.md` 的硬约束是「顺手修已知 bug」而这里是**已知且未列入裁定清单**的缺陷。
  刻意保留 + 在此署名，好过在无关阶段悄悄改掉它。
- **落点**：`src/transcript_reimagined/domain/models.py::Segment.shifted`。

## D-6 · `classify_http` 的可重试错误不携带 `status` / `code` 属性

- **差异**：legacy 的 `RecoverableError` 是裸 `Exception` 子类，只把状态码与上游错误码写进
  消息；只有 `UpstreamError` 有 `.status` / `.code` 属性。本服务**保持原样**。
- **理由**：行为等价优先。测试因此断言消息文本（`"HTTP 429 Throttling"`）而不是属性。
- **落点**：`src/transcript_reimagined/domain/errors.py`；
  测试 `tests/test_rule_059_http_classification.py`。

## D-7 · 新增的非行为 API（不是差异，是补齐）

下列 API 在 legacy 里没有，但**不改变任何既有行为**，只是把已经存在的规则变成可断言的形状：

| API | 用途 | 依据 |
|---|---|---|
| `domain.errors.is_recoverable()` | 把「只重试可恢复错误」变成可测的判定函数 | `NFR-11`、`RULE-059` |
| `domain.errors.retry_delay_s()` | 指数退避 1/2/4s、上限 3 次 | `NFR-11` |
| `post.glossary.cap_hot_words_for_summary()` | 总结热词上限（40 字符/80 词）显式化 | `RULE-021`；legacy 的常量住在 `summary.py` |
| `domain.models.ChunkPlan` | 把切片预算（min/max/overlap）变成一个可传递的值对象 | 架构 §5 的 `chunking` 边界 |
| `runner.metadata` 拒绝凭据字段 | 凭据不得进任务输入 | `NFR-4` |

## D-8 · P0 判据例子按修正值使用（不照抄规则卡）

- **差异**：本项目**不实现** P0 规则（`RULE-001`/`RULE-072` 属 P3/P5），但已把它们的
  验收用例以 `xfail` 形式放好，且例子用的是 `AI_NATIVE_SPEC.md` §5.4 的**修正值**：
  - P0-1：重叠必须 ≥ `_MIN_OVERLAP_CHARS = 4`；3 字符重叠（`开会。`）**不会被去重**。
  - P0-2：失败场景写作「分片 0-2 与 4-5 成功、分片 3 失败」（原卡「0-4 成功、3 失败」自相矛盾）。
- **依据**：`AI_NATIVE_SPEC.md` §5.4、`MODERNIZATION_BRIEF.md` §5 的「不得照抄原例」。
- **落点**：`tests/test_phase_deferred.py`。