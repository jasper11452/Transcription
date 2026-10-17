# domain — 领域模型与错误分类法

`transcript` 重建版（`modernized/transcript-reimagined/`）的一个**模块包**，不是部署单元。
整个系统是单进程模块化单体（见 `analysis/transcript/REIMAGINED_ARCHITECTURE.md` §0/§1）。

- 旧模块：`legacy/transcript/src/transcript/models.py` · `errors.py`
- 承载规则：`RULE-025`（SRT 时间戳格式与取整）、`RULE-059`（HTTP 失败分类）
- 阶段：Phase 1（领域内核试点）

导入名是 `transcript_reimagined.domain`，**不是** `transcript.domain`。理由：
遗留系统仍以 `transcript` 安装在本仓的 `.venv` 里（根 `pyproject.toml` +
`site-packages/transcript`），同名会让 `import transcript.domain` 静默解析到遗留包 ——
那正是「重建版偷偷跑老代码」这类最难查的失败。重建版用一个独占的顶层名，
与遗留版并存且互不干扰。**这是一个跨服务的命名决定**：凡是要 import 本包的服务，
都用 `transcript_reimagined.<service>`。

## 边界（机器可验证）

`domain` 是全仓**唯一的零依赖包**：

1. 零第三方依赖 —— `dependencies = []`，src 里只 import 标准库。
2. 零 I/O —— 不读文件、不开网络、不 import `os`/`io`/`socket`/`subprocess`/`sqlite3`。
3. 不依赖同仓其他包（包括 `config`/`ingest`/`post`/…）—— 它在依赖图最底层，
   `domain ← config ← {ingest, engines, post, diar, state} ← orchestrate ← web`。

三条都由 `tests/test_zero_dependency_contract.py` 用 AST 扫描 + 隔离子进程导入来守住，
不靠调用方纪律。

## 公开面（API stub，对应规格的接口契约）

来源：`AI_NATIVE_SPEC.md` §2 Domain Model + §5.2 规则卡。

| 名称 | 形态 | 契约 |
|---|---|---|
| `Word` | frozen dataclass | `text, start, end, probability=None` |
| `Segment` | dataclass | `start, end, text, words=[], speaker=None`；`.duration`、`.shifted(offset)` |
| `Chunk` | dataclass | `index, start, end`；`.duration` |
| `TranscriptResult` | dataclass | `text, segments, language, audio_seconds, cost_usd, engine, has_timestamps`；`.shifted(offset)` |
| `AudioInfo` | dataclass | `path, duration, size_bytes, codec, sample_rate, channels, has_audio`；`.megabytes` |
| `fmt_timestamp(seconds, *, sep=",")` | 纯函数 | `RULE-025` |
| `TranscriptError` / `FatalError` / `RecoverableError` / `InputError` / `UpstreamError` | 异常 | 分类即重试策略（`recoverable`） |
| `classify_http(status, body="")` | 纯函数 | `RULE-059`，**返回**异常实例，由调用方 `raise`（与 legacy 调用点一致） |

规格 §2 里的 `CHUNK_PLAN` / `GLOSSARY_RULE` / `GLOSSARY_CHANGE` / `ENGINE_SPEC` / `TASK` /
`CHUNK` / `TASK_SUMMARY` 实体**不属于本包** —— 按架构 §2 的归属，它们分别住在
`ingest`（切片预算）、`post`（词表）与 `engines`（注册表）、`orchestrate`、`state`。
本包只承载「所有引擎的公共语言」。

## 两条人裁定（必须保真）

1. **`RULE-025` 取整语义**：裁定为「**改注释，代码不变**」。Python 的 `round()` 是
   round-half-to-even（半值取偶），注释过去写「四舍五入进位」是描述失真，不是代码缺陷。
   现行为保留，`fmt_timestamp` 的 docstring 如实说明 —— 有测试断言注释措辞
   （`tests/test_rule_025_timestamp.py::test_rule_025_rounding_comment_states_half_to_even`）。
2. **`Segment.shifted` 不带 `speaker`**：legacy 行为如此（`models.py:34-43`）。Phase 1 要求
   逐字节等价，本包**原样保留**该行为并加测试钉住，避免「顺手修」变成未署名行为变更。
   它是否该修，属于 Phase 3（`diar` 连通）的决策点。

## 跑测试

```
cd modernized/transcript-reimagined/domain
python -m pytest                                   # 本机：python 指本仓 .venv/bin/python
python -m pytest --list-rules                      # 列出规则 ID / 用例数 / pending 情况
python -m pytest --rule=RULE-059                   # 只跑一条规则的验收测试（可重复传入）
```

不需要先 `pip install -e .` —— `pyproject.toml` 里配了 `pythonpath = ["src"]`。

`--rule=<ID>` 存在的理由：`-m` 的表达式语法要求标记名是合法标识符，而规则 ID 形如
`RULE-025`（带连字符），`-m 'rule(RULE-025)'` 会报语法错。插件在
`tests/conftest.py` 里，只依赖 pytest。

**当前覆盖**（`--list-rules` 的实测输出）：

| 规则 | 用例数 | pending |
|---|---|---|
| `RULE-025` | 26 | 0 |
| `RULE-059` | 35 | 0 |

另有 34 个用例不绑规则 ID：`tests/test_zero_dependency_contract.py`（15，架构边界）、
`tests/test_domain_model.py`（11，领域模型形状）、`tests/test_equivalence_with_legacy.py`
（8，对 legacy 的逐字节差分 = Phase 1 exit criteria）。

## 与 legacy 的逐字节等价（Phase 1 exit criteria）

`tests/test_equivalence_with_legacy.py` 直接加载 `legacy/transcript/src/transcript/` 的
`models.py` / `errors.py`（**只读**，不写入旧树）跑差分：

- `fmt_timestamp`：12072 个（值 × 分隔符）组合，0 处不一致
- `classify_http`：199–604 全状态 × 10 种 body = 4060 个组合，类型 / 消息 / `status` / `code` / `recoverable` 全等
- 5 个 dataclass 的字段名、类型标注、默认值、`frozen`、公开方法集合一一对应
- `shifted()` 的逐字节输出与两个公开函数的签名

旧树不在时可整文件跳过（`TRANSCRIPT_LEGACY_SRC=<path>` 可显式指定），
此时其余 87 个用例仍独立成立。

## 尚未实现（预期失败/跳过）的约定

本包承载的两条规则 `RULE-025`、`RULE-059` 都已实现，**当前没有** pending 用例
（`pytest --rule` 与 `--list-rules` 的输出都印证这一点）。后续阶段若要把某条规则
先写成验收测试再实现，用：

```python
@pytest.mark.rule("RULE-XXX")
@pytest.mark.pending_implementation("RULE-XXX")
@pytest.mark.xfail(reason="RULE-XXX 未实现", strict=True)
# 或 @pytest.mark.skip(reason="RULE-XXX 未实现")
def test_rule_xxx_...():
    ...
```

两个标记都必须在 `pyproject.toml` 的 `markers` 里注册（已注册），
且 `pending_implementation` 必须带规则 ID —— 这样「哪些规则还没落地」可以被
`pytest --list-rules` 与 `-m pending_implementation` 各问一次。
用 `xfail(strict=True)` 而不是裸 `xfail`：规则一旦被实现，测试会变红提醒摘掉标记。