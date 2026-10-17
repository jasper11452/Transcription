# 现代化评估 — transcript

**日期**：2026-10-17
**代码位置**：`legacy/transcript/`（工作区内的真实目录，非符号链接；`git archive HEAD` @ `e0e29c0` 导出的只读快照）
**度量工具**：`scc` 4.1.0（本次评估前已安装；此前 `scc`/`cloc` 都缺失，预检报告预期的「LOC 退算法」已被更准的数据取代）

---

## Executive Summary

`transcript` 是一个 6,897 SLOC 的单人本机转录工具（Python 4,108 + TypeScript 2,789），本机跑得起来、测得过 —— 快照自带测试套件 264 通过 / 2 失败 / 8.9 秒，前端 11/11。它不是老系统：技术栈是当前的（FastAPI + Pydantic 2 / React 18 + Vite 5），依赖锁文件里没有一个已知漏洞。**风险不在技术债的体量，而在三处结构性缺陷**：`web/app.py` 是一个 743 行、复杂度 171 的 god function，25 条路由全是嵌套闭包，没有任何可独立测试的接缝；`frontend/src/task.tsx` 是 1,271 行、复杂度 281 的单个组件；以及约 10,400 行没有任何路由挂载的死代码（workbench 被三份拷贝躺在树里）。安全面只有一处值得动手：**所有状态变更路由既不校验 `Host` 也不校验 `Origin`**，一个 DNS rebinding 页面就能读走全部转录文本并改写 API Key —— 这是本机 127.0.0.1 绑定唯一挡不住的东西。**建议的重建方式不是推平重来，而是「保域换壳」的架构重构（Rearchitect → `reimagine`）**：`audio`/`vad`/`chunking`/`align`/`merge`/`glossary`/`render`/`store`/`engines` 这九个领域模块边界清楚、注释充分（26 个 Python 文件里 21 个有实质性文件级 docstring），值得近乎原样搬运；真正要重做的是 Web 层与前端。

---

## System Inventory

度量口径：**产品代码 = `src/transcript/**` + `frontend/src/**`**。不含 `tests/`（4,773 行）、`spikes/`（775 行），也不含下面「死代码」一节列出的那 4,233 行无挂载 workbench 拷贝。

| 语言 | 文件 | SLOC | 复杂度 | 复杂度/KSLOC |
|---|---:|---:|---:|---:|
| Python | 26 | 4,108 | 1,032 | 251.2 |
| TypeScript | 22 | 2,789 | 435 | 156.0 |
| CSS / JSON / HTML | 3 | 308 | 0 | — |
| **合计** | **51** | **6,897** | **1,467** | **212.7** |

**最复杂的文件**（`scc --by-file -s complexity`，只列产品代码）：

| 文件 | 行数 | 复杂度 | 备注 |
|---|---:|---:|---|
| `src/transcript/web/app.py` | 743 | **171** | 单个 `create_app` 函数定义了全部 25 条路由 |
| `src/transcript/summary.py` | 373 | **107** | 批处理/压缩循环 + 流式解析 |
| `src/transcript/pipeline.py` | 665 | 96 | 编排脊柱，复杂度分散在重试/缓存/续跑分支 |
| `src/transcript/align.py` | 243 | 63 | 词级时间轴对齐 |
| `src/transcript/store.py` | 412 | 60 | SQLite 单文件库 |
| `frontend/src/task.tsx` | 1,271 | **281** | 任务详情页整页一个组件 |
| `frontend/src/main.tsx` | 300 | 73 | 控制台页 |
| `frontend/src/lib/summary-stream.ts` | 97 | 40 | SSE 流解析 |

**树整体数字（含死代码与测试）供对照**：`scc legacy/transcript` 报 156 文件 / 29,859 SLOC / 复杂度 4,698 —— 但这个数字被三份 workbench 拷贝严重放大，**不能当作系统规模**。

---

## Architecture at a Glance

12 个功能域，完整依赖图见 `analysis/transcript/ARCHITECTURE.mmd`。

| 域 | 文件 | 职责 | 依赖 |
|---|---|---|---|
| **1 核心契约** | `models.py` `errors.py` `config.py` | 领域数据类；错误分类法（`RecoverableError` vs `FatalError` **就是**重试策略）；配置从 `~/.config/transcript/config.env` 读取；凭据掩码 | stdlib, dotenv |
| **2 音频入料** | `audio.py` `vad.py` `chunking.py` | ffprobe 探测 / ffmpeg 归一化到 16k wav 或 64k mp3；silero-VAD 语音段；纯函数切片规划器（保证 `duration <= max_s`，这是 300s 上游上限不被击穿的唯一保障） | 1 |
| **3 流水线编排** | `pipeline.py` | 单一控制脊柱：探测→归一化→VAD→规划→逐片转写（缓存复用/重试/取消）→合并→词表→可选分离→渲染→写盘；分片级 SQLite 检查点，进程被杀可续跑 | 1,2,4,5,6,8 |
| **4 引擎适配器** | `engines/{base,offline,dashscope,openrouter,bcut}.py` | 每引擎一文件，统一在 `Engine` Protocol 之后；`base.py` 的 `SPECS` 是**唯一注册表**（引擎 id、所需凭据、`max_chunk_s`、`auto`→artifact 映射） | 1,2,5 |
| **5 后处理** | `align.py` `merge.py` `glossary.py` `render.py` | Qwen 文本对齐到 whisper 词级时间轴（单调时间不变量）；相邻分片去重（阈值刻意保守）；热词解析与 `错词 -> 正确词` 确定性替换 + 变更台账；txt/SRT 渲染 | 1 |
| **6 状态存储** | `store.py` | 单文件 SQLite（WAL，短连接）；`tasks`/`chunks`/`summaries`；**分片是唯一的续跑单位**；从不存凭据 | 1 |
| **7 Agent 总结** | `summary.py` | 任务级显式开启；只发文本不发音频；批处理压缩 + 流式解析 + JSON 校验 | 1,5,6 |
| **8 说话人分离** | `diar.py` | ctypes 绑定本地 `libnemo_speech_asr_c.dylib` + Nemotron GGUF；**未接通的死路径**，见技术债 #9 | 1,3 |
| **9 Web 服务** | `web/{app,jobs,frontend}.py` | FastAPI、仅绑 127.0.0.1、故意无鉴权；约 20 个 JSON 端点 + SSE 扇出；离线串行 / 在线并行线程池；`frontend.py` 是构建产物门禁（**绝不 `npm install`**） | 1–7 + Vite 产物 |
| **10 React SPA** | `frontend/src/**` `frontend/*.html` | 两个 Vite 入口 = 两个页面，无前端路由；静态 HTML 是「表单唯一真相」，React 只补丁带 id 的岛 | 9 |
| **11 CLI** | `cli.py` | `serve` / `run` / `check [--probe]` / `init-config` | 1,3,4,6,9 |
| **12 验证与探针** | `tests/**` `spikes/**` `.agents/acceptance/PROJECT.md` `*.md` | 按隔离层级组织的 pytest；录制的引擎夹具；一次性在线探针（其产物成了 `config.py` 里的常量） | 集成 |

**架构的整体评价**：领域层（1–8）是**这套代码里最好的部分** —— 边界干净、依赖单向、注释解释的是「为什么」而不是「是什么」（例如 `merge.py` 的去重阈值注释：「少去重只是留一点重复，多去重会吃掉正文」）。问题全部集中在**接缝之外**：Web 层（9）把 20 多条路由和全部应用级辅助函数塞进一个闭包，前端（10）把整页塞进一个组件。这是典型的「内核长得好、外壳长歪了」。

---

## Production Runtime Profile

**存在真实的运行期证据**：产品仓库里的 `state.db`（7.0 MB，本机任务历史）就是一份运行导出。以下是它的全部内容 —— 11 个任务、10 个成功、0 个失败、469 个分片。

| 任务 | 模式 | 引擎 | 音频秒 | 墙钟秒 | 字符 | 成本 |
|---:|---|---|---:|---:|---:|---:|
| 16 | online | dashscope:qwen-audio-3.1-asr-flash | 1,403 | 40.0 | 5,619 | 0.000 |
| 14 | offline | offline:qwen3-asr+whisper | 521 | 47.0 | 2,168 | 0.000 |
| 6 | offline | offline:qwen3-asr+whisper | 668 | 50.0 | 2,448 | 0.000 |
| 13 | offline | offline:qwen3-asr+whisper | 606 | 61.0 | 6,214 | 0.000 |
| 10 | online | dashscope | 3,300 | 77.0 | 12,629 | 0.000 |
| 11 | online | dashscope | 3,300 | 78.0 | 10,342 | 0.000 |
| 15 | online | dashscope | 3,457 | 79.0 | 12,688 | 0.000 |
| 12 | online | dashscope | 3,210 | 80.0 | 11,066 | 0.000 |
| 7 | online | dashscope | 4,036 | 108.0 | 16,887 | 0.000 |
| 8 | online | dashscope | 5,661 | 169.0 | 20,496 | 0.000 |

| 模式 | n | 墙钟 p50 | 墙钟 max | RTF p50（墙钟/音频） |
|---|---:|---:|---:|---:|
| offline | 3 | 50.0 s | 61.0 s | 0.090 |
| online | 7 | 79.0 s | 169.0 s | 0.025 |

**读出来的三件事**：

1. **离线的 p50 墙钟（50 s）压在在线（79 s）之下，但样本里最长的音频只有 5,661 s（94 分钟）**，且 RTF 差 3.6 倍。样本量太小（n=3 / n=7），这条曲线在真实负载下的分离度无法从这份数据确定 —— 重建时不要据此改动引擎默认值。
2. **在线路径的墙钟随音频近乎线性**（1,403 s 音频 → 40 s；5,661 s → 169 s），说明分片确实是并行的，且瓶颈在引擎侧不在本机。
3. **`cost_usd` 全为 0.000**。任务 8 是 94 分钟音频走 dashscope，成本记录却是 0。这不是「免费」，而是**成本核算在 dashscope 路径上根本没接线** —— 与之对照，`pipeline.py:37` 硬编码的 `ONLINE_PRICE_PER_HOUR = 0.1` 说明作者知道要算这笔账。用户界面上展示的成本估算因此对在线任务是不可信的。

**最高方差**：在线路径（40 s → 169 s，4.2 倍跨度）对离线路径（47 s → 61 s，1.3 倍）。运营风险点在在线引擎 —— 但它在设计上就是可降级的（切离线即可），所以是**可接受的方差**，不是需要加固的地方。

---

## Technical Debt（按修复价值排序，前 10）

| # | 位置 | 类别 | 问题 | 修复价值 |
|---:|---|---|---|---|
| 1 | `src/transcript/pipeline.py:366`（被 `tests/test_pipeline.py:174`、`tests/test_web.py:298` 断言） | 正确性 / 已知 bug | `.srt` 被**无条件**写出：`srt_path = self._write(out_dir / f"{stem}.srt", to_srt(...))` 忽略了 `artifact`。同一个 `_run_inner` 在第 347 行**有** `artifact == "srt"` 判断、在第 469 行也按 `artifact` 决定要不要时间戳，说明分支意识是有的，只是落盘这一处漏了。后果：跑「只要 txt」的任务会静默产出一个半成品 `.srt`，`RunResult.srt_path` 非空使 `srt_exists` 翻真，界面因此给出一个「下载字幕」按钮 —— 而两个测试正是在说不该有。两个测试当前都失败，即契约已在代码里钉住、只是实现没跟上。 | **最高。** 一行分支即可，且消灭一整类「说明说一种产物、磁盘上是另一种」的 bug。重建时应把产物选择做成**单个写决策**，而不是两次独立的 `_write` 调用。 |
| 2 | `src/transcript/web/app.py:108-743` | god object | `create_app` 是**单个 635 行函数**，25 条路由全是嵌套闭包，还包含 `_status_payload` / `_task_payload` / `_detail_payload` / `_task_list` / `_key_fields` / `_write_*` / `output_path` 等应用级辅助函数，以及可变缓存 `model_cache`（:525）。没有任何部分可独立测试 —— 要测一条路由必须先构造完整的 app + store + JobManager。 | 高。这正是第 7 项（配置写入三份实现）的**成因**：闭包让复用不可能。重建按资源切分（tasks / settings / credentials / outputs / events），依赖显式注入。 |
| 3 | `src/transcript/web/static/workbench/**`（13 文件 4,233 行）vs `spikes/workbench/`（同内容）vs `spikes/workbench/.baseline/`（第三份，5,872 行） | 死代码 / 三重复制 | workbench 在树里存在**三份字节相同**的拷贝（`diff -rq` 已逐文件确认：`static/workbench` 与 `spikes/workbench/src`+`styles` 完全一致，仅多 `index.html` 与 `styles`）。`app.mount('/static/dist', DIST_DIR)` 只暴露 `static/dist`，**没有任何路由挂载 `static/workbench`**，`pyproject.toml:29` 也把它排除在 wheel 之外 —— 既不被服务也不被打包。而无路由挂载的那份 `main.js:581` 还在用 `document.execCommand('copy')`。 | 高。重建前删掉 `src/` 那份拷贝与 `.baseline/` 可减少约 **10,400 行**未经测试、不可达的表面，同时移除一个「设计师会照着抄」的陈旧分支。`spikes/` 本身有 README 与 ABLATION 记录，是研究产物，可以留。 |
| 4 | `src/transcript/engines/offline.py:102-110` | 伪装成兜底的逻辑错误 | 时间戳兜底**永远不会生效，而且一旦触发就把成本翻倍**。`build_segments(text, words)` 只在 `align.py:172-178` 两条路径返回 `[]`，两条都取决于 `char_times` 全为 `None` —— 结果是 `(text, words)` 的纯函数。所谓兜底在第 108 行用**相同的** `path`/`repo`/`language` 重跑一遍 `_whisper_words(...)`，再把同一个词表喂给同一个 `build_segments`，只可能再返回 `[]`。在罕见可达路径上，它付一次完整 whisper 转写（离线路径每片数秒到数分钟，且位于逐片循环内）。 | 高。正确的做法是：词级时间轴只算一次，让 `align.build_segments` **报告它为什么退化**（`align.py:201` 的 `_fallback_segments` 等时平摊），而不是用第二次模型调用把原因盖住。第 108 行的注释「而不是丢掉时间信息」描述的是这段代码**产生不了**的行为 —— 把它归类成「兜底」正是它活下来的原因。 |
| 5 | `frontend/package.json:15-30` + `frontend/src/components/ui/*.tsx` | 死代码 / 无用依赖 | 14 个 shadcn/Radix 包装组件里 **9 个（652 行）零引用**（alert / card / dialog / dropdown-menu / label / progress / select / skeleton / toast —— 只有 button / input / tabs / textarea / badge 在用）。三个声明的运行时依赖在源码、HTML、测试里都查不到：`@tanstack/react-query`、`react-router-dom`、`zustand` —— 应用实际用的是手写 `fetch`、手写 `popstate`/事件委托路由（`task.tsx:1205-1254`）和 `useState`。这 9 个孤儿组件**正是** `@radix-ui/react-{dialog,dropdown-menu,progress,select,toast}` 存在于 `dependencies` 的唯一原因。 | 中高。重建时应先定下**一种**状态/数据/路由策略，而不是发布一套「记录了所有没人选的方案」的组件包。先删掉它们，也就移除了重写期间「就用现成的 dialog 吧」这个诱惑 —— 那会悄悄把同样的重复机制再引进来。 |
| 6 | `src/transcript/web/jobs.py:119-123` + 整个 `src/` | 缺可观测性 | **`src/` 里没有任何日志** —— `grep -rn "import logging" src/` 返回 0 命中。唯一的全局捕获是 `except Exception as exc: self.store.update_task(..., error=f"内部错误：{exc}")`，同一个字符串既进 `RunResult` 又经 SSE 发到浏览器；`app.py:117-120` 的 `HTTPException` 处理器同样原样返回 `str(exc.detail)`。于是一次意外内部失败表现为**没有堆栈、没有关联 id、没有落盘**的一行异常文本，且无法区分「上游拒绝」（`errors.py:40-52` 精心分类过的那种）和「我们自己有 bug」。 | 中高。新服务需要带任务/请求关联 id 的结构化日志和稳定的错误分类法；界面应渲染错误码 + 人类可读句子，而不是插值异常。目前失败之所以还能排查，只是因为人正好坐在终端前看着 `transcript serve` 的输出 —— 这个前提活不过重建。 |
| 7 | `src/transcript/web/app.py:410-423`、`:668-675`；死重复在 `config.py:213-246` | 重复 / 错误处理不一致 / 文件安全 | 配置与热词写入是**同一件事的三份实现，安全级别各不相同**。凭据路径很严谨 —— 临时文件 + `os.chmod(tmp, 0o600)` + `os.replace`；但 `_write_hot_words`（:410）和 `put_glossary`（:668）是裸的 `path.write_text(...)`，**无临时文件、无原子替换、无 chmod**，所以写入中崩溃会截断用户的热词，且产物没有 600 权限 —— 尽管它可能含同一批专名。与此同时 `config.save_credentials`（:213）**已经**实现了正确的原子、保注释、600 版本，而且**在 `src/`、`tests/`、`frontend/` 里没有任何调用者**；它的 docstring 里声明的保证，恰恰是实际在用的那份拷贝（`_write_config_file`）只部分复现的。 | 中高。选**一个**原子写辅助函数作为所有用户文件变更的唯一通道，让密钥写入和热词写入都调它。那个无人调用的 `save_credentials` 是**意图契约**的提炼，正是该保留的规格；两个 ad-hoc 写入器才是该删的。 |
| 8 | `src/transcript/web/app.py:645-656`（`/api/upload`）；`jobs.py:209`；`summary.py:34`；`glossary.py:135`；`config.py:58` | 死代码 / 缺防护 | 五个无人调用的符号，其中一个是**活跃的 HTTP 面**。`/api/upload` 是 `create_task` 上传分支（:265-281）的第二份、更弱的实现：它**完全不检查** `MAX_UPLOAD_BYTES`，会把无上限的请求体直接落到 `state_db.parent/uploads`（该目录同时装着 `state.db` 和全部产物），且没有任何任务记录指向这些文件、也没有任何东西删除它们 —— 而 `MAX_UPLOAD_BYTES`（:52，2 GB）在文档里被描述为产品上限。另外：`JobManager.history` 只被测试当断言钩子用；`SummaryContent`（一个 4 字段的 Pydantic 模型）从未被实例化，`_parse_content` 的校验是手写的、只用 `[:80]` / `[:2000]` / `[:8]` 截断；`dedupe_rules` 与 `Config.mask` 无调用者。 | 中。这五个都是「文档在撒谎说自己在跑」。重建时：直接删掉 `/api/upload`（它是回环绑定背后一条**未认证、无上限**的写入路径，而 `PRODUCT.md` 为回环绑定给出的理由是「单个可信用户」）；如果 `SummaryContent` 是意图中的输出契约，就真的按它校验，而不是用字符串切片重造它的限制。 |
| 9 | `src/transcript/config.py:94-97`；`diar.py:153-211`；`render.py:28-48` | 未接通的死功能路径 | 说话人分离是一个**完整实现的约 210 行 ctypes FFI 模块，而没有任何受支持的输入路径能到达它**。`enable_diar` 默认 `False`，只从配置文件里的 `ENABLE_DIAR` 读 —— 没有路由、没有 boot payload、没有前端控件暴露它，用户必须手改 `config.env` 才能开。而它做出来的工作还被部分丢弃：`assign_speaker` 写入 `segment.speaker`，`to_txt` 会渲染 `[speaker_N]` 块，但 `to_srt` **完全忽略 `speaker`**；`tests/data` 里没有分离夹具，所以 ctypes ABI 从未对照已安装的 dylib 验证过。 | 中。重建时必须二选一：把说话人分离做成端到端的产品功能（config → API → UI → srt/txt 都接通），或把这个 FFI 模块移出 `src/`。发布一个绑定到版本化第三方 dylib（`diar.py:21-30` 硬编码了 `…/NeMoSpeech/main-97a15af/…`）、且没有任何测试能执行它的 ctypes 绑定，是**长期升级风险** —— 预设字符串 `b"v3-offline"` 和 10 字段 `_ModelCfg` 结构体与该构建哈希静默耦合。顺带一提，`PRODUCT.md` 把「说话人分离」明确列在非目标里 —— 文档与代码必有一份是陈旧的。 |
| 10 | `pipeline.py:37`；`cli.py:25`；`web/app.py:52`；`frontend/index.html:85` vs `main.tsx:206` | 硬编码配置 / 两个真相来源 | 运营常量被烤进「恰好最先用到它」的那一层。`ONLINE_PRICE_PER_HOUR = 0.1` 是用户可见成本估算的代码常量，改价即发版；引擎元数据刻意集中到了 `engines/base.py:63-104`，但价格、端口、上限没有跟着集中。`DEFAULT_PORT = 8765` + `--host 127.0.0.1` 在 `.agents/acceptance/PROJECT.md:15-17` 里被复制成文档，必然漂移。`MAX_UPLOAD_BYTES` 只在一个上传路径里生效，不在另一个（见 #8）。最露骨的一处：前端 HTML 里有一个用户填好的 `<input type="hidden" name="artifact" value="srt" />`（`index.html:85`），但 `main.tsx:206` 用 `const artifact = 'srt'` 把它盖掉 —— DOM 里那个值是装饰性的。 | 中。把可调项（定价、绑定默认值、尺寸上限、artifact 选项）集中到**引擎注册表旁边** —— 那个模式已经被证明好用。前端应该读它自己渲染出来的表单值，而不是用字面量遮蔽它。这一类最可能在重建中静默回归，因为每个常量在它所在的位置看起来都无害且局部。 |

---

## Security Findings

**没有发现任何真实凭据**。全仓扫描只命中合成测试夹具（`tests/test_engines_online.py:134` 的 `Bearer sk-secret-1234`、`tests/test_summary.py:173` 的 `Bearer test-summary-key`、`tests/web/test_summary_settings.py:109-110`、`tests/web/test_api.py:494`），因此**未创建 `SECRETS.local.md`**，也不需要轮换任何东西。

**负向结果（同样有价值）**：SQLite 存储层**不存在 SQL 注入** —— 每条 DML 都是参数化的，唯一的动态 SQL 是「从硬编码键白名单构造 `SET` 子句」；`src/` 里没有 `pickle`、`yaml.load`、`eval`、`exec`、`shell=True`；subprocess 调用全部走 list argv。`frontend/src`（**实际发布的那份**前端）的 XSS 面**干净**：唯一的 `innerHTML` 写入是 `main.tsx:164` 的清空操作，无 `dangerouslySetInnerHTML`；服务端 boot JSON 内联正确转义了 `<>&` 与 U+2028/9。后端锁定的 15 个包经 OSV 查询**全部 0 告警**。源码、配置、夹具与文档里也**没有任何针对自动化分析的指令形状文本** —— 即这份代码库没有试图引导本次评审。

| CWE | 严重度 | 位置 | 问题 | 为什么重要 | 修复方向 |
|---|---|---|---|---|---|
| **CWE-306** 关键功能缺失鉴权（+ CWE-352 CSRF，无 `Origin`/`Host` 校验） | **中** | `web/app.py:247, 429, 637, 645, 668, 698` | 每条状态变更路由（`POST /api/tasks`、`PUT /api/summary-settings`、`POST /api/reveal`、`POST /api/upload`、`PUT /api/glossary`、`POST /api/credentials`）都不鉴权，且**既不校验 `Host` 也不校验 `Origin` 或 `Sec-Fetch-Site`**。单看「没有鉴权」是文档写明的、对本机单人工具的合理选择；**缺少来源校验不是**。 | 两个具体攻击：(1) 用户访问的任何页面都能提交一个普通跨站 HTML 表单（`application/x-www-form-urlencoded` / `multipart` 不触发 CORS 预检）打到 `127.0.0.1:8765/api/tasks` 或 `/api/reveal`，浏览器代理都不需要；(2) **DNS rebinding** 让攻击者域名解析到 127.0.0.1，预检屏障随之消失，JSON 端点变成可读的同源 API —— 完整任务列表、全部转录文本，以及改写总结 Base URL 和 API Key 的能力。**这是本次评估唯一的实质安全风险**，也是本机绑定唯一挡不住的东西。 | 加中间件拒绝任何 `Host` 不是 `127.0.0.1[:port]` / `localhost[:port]` 的请求，并对所有非 GET 路由要求 `Sec-Fetch-Site: same-origin`（或 `Origin` 白名单）。可选：每进程生成一个 token，经 boot JSON 内联，要求以 header 提交。 |
| **CWE-918** 服务端请求伪造（SSRF） | 中 | `web/app.py:457-477`（校验）、`:540-544`（模型代理）、`summary.py:144-147, 178-183` | `OPENROUTER_BASE` 的校验只到「http(s)、有 hostname、无 userinfo/query/fragment」。回环、RFC1918、link-local 与云元数据地址**全部被接受**，之后该值被服务端用于 `GET {base}/models` 与 `POST {base}/chat/completions`，并附带 `Authorization: Bearer <存储的密钥>`。 | 与上一条**串联**后威力放大：一个 rebinding 页面把 `base_url` 设成攻击者或内网主机，下一次总结就把**整份转录、用户提示词和 OpenRouter 密钥**推过去；`/api/summary-models` 还会把响应体代理回来。 | 解析后拒绝指向回环/私有/link-local 网段的 base URL（拨号前先 `resolve` 再判断）；主机变更时要求重新输入 API Key；对默认厂商保留显式主机白名单。 |
| **CWE-770** 无限制或无节流的资源分配 | 中 | `web/app.py:645-656`（对照有上限的 `:265-280`） | `/api/upload` 把请求体直落磁盘，**无字节上限、无后缀白名单**；`/api/tasks` 用同一个上传目录时**有** 2 GB 上限。 | 未认证的重复上传会耗尽那个同时装着 `state.db` 和全部产物/raw.json 的卷；这条无上限路由也是「本该是唯一入口」之外的第二条无限制入口。 | 删掉 `/api/upload`，或给它加与 `:275` 相同的 `MAX_UPLOAD_BYTES` 循环与 `_AUDIO_MIME` 后缀校验；拒绝时清理残留分片文件。 |
| **CWE-73** 文件名或路径的外部可控 | 中 | `web/app.py:282-292`、`:625-635` | 表单来的 `source_path` 经 `expanduser()` 后**原样使用**并被持久化，随后由 `/api/tasks/{id}/audio` 逐字节回送。 | 与 CWE-306 串联后，这是读取「用户账户能读、且 ffprobe 认得出是非零时长音频」的任意文件的读原语（会议录音、磁盘上任何位置的语音备忘）。音频容器要求使它够不上「任意文件读」，故定中而非高。 | 把接受的路径限制在配置的根目录内（`output_dir` / `state_db` 父目录 + uploads），`Path.resolve()` 后检查包含关系再接受；永不回送非流水线产出的路径。 |
| **CWE-200** 敏感信息暴露 | 低 | `web/app.py:124-131, 143-175, 177-189`；`config.py:58-73` | boot JSON / API payload 携带绝对 `source_path`、`out_dir`、`txt_path`、`srt_path`、`raw_path` 与完整分片文本；`credential_status` / `mask_preview` 暴露每个密钥的**后 4 位**。转义本身是对的。 | 用户主目录布局与 4 位密钥尾巴可被任何够得到该 API 的东西读到（见 CWE-306）。**从不返回明文密钥** —— 这是加固缺口，不是泄露。 | 列表端点返回 basename/相对路径，绝对路径只在详情页披露；`credential_status` 去掉 4 位尾巴，或置于同一来源校验之后。 |
| **CWE-79** DOM XSS | 低 | `web/static/workbench/main.js:661, 667`；不可信值从 `store.js:271` 进入（副本在 `spikes/workbench/src/`） | `speakers[].color` 被原样插值进 `style="background:${r.color}"`，`replaceDoc` 转发 `next.speakers` 时不做归一化（`segments` 在 `store.js:274-291` **有**归一化，`speakers` 没有），`escapeHtml` 在这里从未被调用。 | 一个精心构造的 `.raw.json` 经 workbench 的文件选择器打开，就能从引号属性里逃逸并注入带事件处理器的标签。可达性受限：`src/` 里没有任何路由或引用指向这个 bundle，`pyproject.toml` 也把它排除在 wheel 外 —— 故定低。 | 渲染前用 `^#[0-9a-fA-F]{3,8}$` 校验颜色，对所有插值应用 `escapeHtml`；**并删除这份遗留 bundle 及其 spike 副本**（没有任何路由服务它）。 |
| **CWE-1104 / CWE-1395** 使用未维护或存在漏洞的第三方组件 | 低 | `frontend/package-lock.json`：`vite` 5.4.21、`esbuild` 0.21.5、`braces` 3.0.3 | OSV 对这三个精确版本报出 5 条公告（Vite 3 条：优化依赖 `.map` 路径穿越 GHSA-4w7w-66w2-5vf9、Windows 备用路径绕过 `server.fs.deny`、`launch-editor` UNC 路径泄露 NTLMv2 哈希；esbuild 1 条：开发服务器可被任意网站读写 GHSA-67mh-4wv8-2f99；braces 1 条：深层嵌套模式栈耗尽）。**Vite 的全部修复都落在 6.x**，5.x 线不会收到。 | **仅开发服务器** —— 发布的是构建好的 `dist` 包。两条是 Windows 专属；路径穿越那条是真的，esbuild 那条则与平台无关，浏览器页面能与回环端口上的开发服务器通话。`README.md:69` 明确记录了「后端运行时另开 `vite dev`」这个用法。 | 升到当前 Vite（7.x，连带 `@vitejs/plugin-react`），或至少不在不可信时段运行 `vite dev`。 |
| **CWE-88** 参数注入 | 低 | `audio.py:52-64, 96-115, 139-159` | ffmpeg/ffprobe 用 list argv 调用（**已确认无 `shell=True`**），但路径参数前**没有 `--` 分隔符**，所以以 `-` 开头的路径 token 会被当成选项解析。 | **按当前发布形态不可达**：所有调用方传的都是绝对路径或生成的临时名。仍值得修，因为 CLI 入口（`cli.py:176`）和未来调用方可以传入裸相对文件名，而 ffmpeg 未来新增的 `-` 前缀选项会把它变成真实误行为。 | 在 `probe`、`_normalize`、`cut` 的最后一个输入/输出位置参数前插入 `--`；拒绝 basename 以 `-` 开头的路径。 |

---

## Documentation Gaps

代码实际做的事，与 README / 文档 / 注释说的事之间的差距。以下是新工程师最需要被解释清楚的 5 件事：

| # | 缺口 | 证据 |
|---:|---|---|
| 1 | **四份被引用但根本不存在的文档。** `src/transcript/align.py:3`、`config.py:24,258`、`pipeline.py:36` 都把 `docs/spec.md` 当作实测常量的证据来源（模型 id、`DASHSCOPE_MAX_CHUNK_S = 300.0`）；`config.py:3,216`、`pipeline.py:3` 引用 `AGENTS.md`；`audio.py:3` 引用 `qwen3-asr-audio-input.md`；`bcut.py:3` 引用仓库外的 `/Users/jasper/Desktop/online_bcut_srt.py`。**`docs/` 目录在整个仓库及其父目录都不存在。** | 每个实测常量都指向一份不在这里的文档 —— 新工程师无法验证任何一个数字，也无法知道它们是测出来的还是猜的。 |
| 2 | **README 描述了一个不存在的前端测试层。** `README.md:89,96` 声称有 `frontend/src/**/*.test.ts`（Vitest 组件/hook 测试）；`README.md:97,100,101` 详细描述了 `frontend/e2e/`（含 `serve_e2e.py`、`.state.json`、端口 8876）。**实际：`frontend/src` 下 0 个 `.test.ts`，`frontend/e2e/` 不存在，`package.json` 里没有 vitest 也没有 playwright**，`test` 脚本只有 `node --test tests/*.test.mjs`（2 个文件、11 个用例）。 | 新人会照着 README 去找一套不存在的测试，并据此错误估计前端覆盖率。 |
| 3 | **说话人分离：文档与代码互相矛盾。** `PRODUCT.md` 把「说话人分离」明确列在**非目标**里，但 `diar.py`（211 行、ctypes 打进本地 dylib）确实存在并且在 `pipeline.py:331-345` 接通了。两份必有一份陈旧。 | 见技术债 #9。这是一个「到底是产品功能还是研究残留」的判断题，代码自己回答不了。 |
| 4 | **workbench 的定位说明与实际部署不符。** `spikes/workbench/README.md:5` 自称「不接入 `src/transcript/` 的后端，不写用户数据，不参与打包」，但同一份内容被提交到了 `src/transcript/web/static/workbench/`。**是 `pyproject.toml:29` 的排除规则让这句话碰巧成立，而不是设计使然。** | 见技术债 #3。任何一次对打包配置的改动都会让一份 4.2k 行的死代码意外进入发行包。 |
| 5 | **「分层错误分类就是重试策略」这条核心设计从未被写在架构文档里。** `errors.py` 里 `RecoverableError` 与 `FatalError` 的区分决定了哪些错误退避重试、哪些直接暴露；`pipeline.py` 开头的四条硬规则（分片是唯一重试单位、只重试可恢复错误、错误不得当结果返回、原文件只读）是整套编排的宪法。这些现在只存在于源码 docstring 和一个**不存在**的 `AGENTS.md` 的引用里。 | 重建时最容易丢掉的就是这种「没有文档、只靠注释传递」的不变量。`extract-rules` 必须把它们挖成显式的规则卡。 |

---

## Relative Scale

**规模指数**（用户给定的公式 `2.94 × KSLOC^1.10`，纯作为**跨系统排名的相对尺度**使用）：

| 范围 | SLOC | 指数 |
|---|---:|---:|
| Python（产品代码） | 4,108 | 13.9 |
| TypeScript（产品代码） | 2,789 | 9.1 |
| **产品代码合计** | **6,897** | **24.6** |
| 全部（含测试、探针、三份 workbench 拷贝） | 29,859 | 111.6 |

**这个数字不是工期，不是成本，不是任何时间承诺。** 该公式以人月团队的有机生产力为假设，对 agent 驱动的现代化完全不适用。`scc` 自己还会打印「Estimated Schedule Effort 7.67 months」「Estimated People Required 2.49」和美元金额 —— **本次评估明确忽略这三行**，它们对这类工作无效。此处只保留指数，用途仅限一件事：把 `transcript` 与将来其他系统放在同一张表里排序。

**量级判断**：6,897 SLOC 的产品代码、51 个文件、单进程、单人使用 —— 这是一个**小型系统**。它的重建属于几天到两周的强度，不属于数月工程。任何把它当作「大型遗留系统」来规划的方案都是过度设计。

---

## Recommended Modernization Pattern

### 判定：**Rearchitect**（架构重构），路由到 `/code-modernization:modernize-reimagine`

（`Rehost` = 原样搬迁、`Replace` = 采购替换，两者都不改代码，不适用；`Replatform` = 换运行时但保留代码，此项目的运行时已是当前的，不适用；`Refactor` 与 `Rearchitect` 的区别在于**是否改变模块边界** —— 下面的分析会说明边界本身必须动。）

**理由。** 本次评估**确认了** `INTENT.md` 里「模块化单体」的目标架构，但要给出一条重要的精确化：**这次重建应该是外科手术式的，而不是推平重来。**

三个结构性缺陷——`web/app.py` 的 743 行 god function（复杂度 171，零可测接缝）、`task.tsx` 的 1,271 行单组件（复杂度 281）、以及约 10,400 行无挂载的死代码——**全部位于领域层之外**。而领域层（`models` / `errors` / `config` / `audio` / `vad` / `chunking` / `align` / `merge` / `glossary` / `render` / `store` / `engines`）恰恰是这套代码里质量最高的部分：依赖单向、边界清楚、注释解释「为什么」、26 个文件里 21 个有实质性文件级 docstring，并且有 264 个通过的测试钉住行为。**把这些模块重写一遍，等于用风险换取零收益。**

因此「按新架构重建」在这个代码库上的正确含义是：

1. **必须重塑的边界**：Web 层。把 `create_app` 的单个 635 行闭包拆成按资源切分的路由模块（tasks / outputs / settings / credentials / events），依赖显式注入而非闭包捕获。这一刀顺带解决技术债 #7（配置写入三份实现）——闭包正是复用不可能的原因。同时给这一层加上带关联 id 的结构化日志（#6）和来源校验中间件（安全表第一条）。
2. **必须重做的外壳**：前端。先定下**一种**状态/数据/路由策略，删掉 9 个未使用的 shadcn 组件与 3 个未使用的依赖（#5），再按页面拆 `task.tsx`。
3. **近乎原样搬运的内核**：上述 12 个领域模块。它们已经在架构上就是「模块化单体」该有的样子。搬过来时把技术债 #1（`artifact` 落盘分支）、#4（offline 的伪兜底）、#10（硬编码常量）一并修掉——这三个都是**局部、低风险、有测试或文档背书**的改动，正好落在你选的「顺手修已知 bug」上。
4. **必须先做的减法**：删掉 `src/transcript/web/static/workbench/**` 与 `spikes/workbench/.baseline/**`（约 10,400 行）。在动手重建之前做，目的是让新代码的复杂度基线不被死代码污染——`scc` 现在报的 4,698 总复杂度里有相当一部分是同一个 workbench 数了三遍。
5. **需要做出决定的两项**：说话人分离（#9）到底是产品功能还是研究残留——`PRODUCT.md` 说非目标、代码说已接通，重建时不能既不删也不接线。`/api/upload`（#8）是删掉还是补上限——它现在是一条未认证、无上限的写入路径，而 `PRODUCT.md` 为回环绑定给出的理由是「单个可信用户」，两者不能同时成立。

**这些决定应当留到 `review` 阶段由你来拍**——`extract-rules` 会把它们连同证据一起转成规则卡，其中「行为应当是什么」由你的回答决定，而不是由旧代码决定。

**路由命令**：`/code-modernization:modernize-reimagine transcript`（前置：先跑 `map` 和 `extract-rules`，让重建方案建立在实际依赖图和显式规则卡之上，而不是这份评估的摘要之上）。