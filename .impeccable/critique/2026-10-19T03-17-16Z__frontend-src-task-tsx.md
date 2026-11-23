---
target: frontend/src/task.tsx
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
p2_count: 2
target_identity: "file:/Users/jasper/Documents/Transcript/frontend/src/task.tsx"
target_fingerprint: "sha256:084753c1695a362116d96645093c9b4c80276b29050d303daf58ffd7c374813c"
target_path: /Users/jasper/Documents/Transcript/frontend/src/task.tsx
timestamp: 2026-10-19T03-17-16Z
slug: frontend-src-task-tsx
---
# Critique — Transcript（控制台 + 任务详情 + 全局设置）

⚠️ DEGRADED: B leg inline — Assessment A 在隔离子代理 (1af478d3) 中完成；Assessment B 子代理 (8bfdbb1b) 在运行窗口内未产出，检测器与浏览器证据由主上下文补跑。

目标：`frontend/src/task.tsx`（主工作台），同时覆盖 `frontend/src/main.tsx`、两个静态外壳与全局设置页。审查时点是 polish 之前。

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|---|---|---|
| 1 | Visibility of system status | 4 | %, 分片计数, LIVE, 流式总结, 诚实的已中断；缺 elapsed/ETA |
| 2 | Match system / real world | 3 | 中文界面里混英文状态眉题；auto 引擎名带完整路由说明 |
| 3 | User control and freedom | 3 | 停止转录立即生效，无确认；删除反而有二次确认 |
| 4 | Consistency and standards | 2 | 同一失败状态在侧栏叫「失败」、详情叫「已中断」；完成态仍显示「已暂停跟随」 |
| 5 | Error prevention | 2 | 无文件/路径时提交按钮可点，错误要等服务端 400 才出现 |
| 6 | Recognition rather than recall | 2 | 热词与总结连接只藏在某条任务的设置标签里 |
| 7 | Flexibility and efficiency | 3 | 拖放/路径/CLI；50 条历史无搜索或快捷键 |
| 8 | Aesthetic and minimalist design | 3 | 克制可读；浅色虚线拖放框对比度 ~1.2:1；控制台近半屏空 |
| 9 | Error recovery | 2 | 续跑按钮在 1440×900 下位于 y=940（首屏外） |
| 10 | Help and documentation | 2 | 首次运行没有离线就绪提示，也没有帮助入口 |
| **Total** | | **26/40** | **Acceptable（21–30）** |

## Design Specificity Verdict

**内容层是本产品的，外壳是 xAI 的。** 时间码沟、实时字幕行（橙色当前行、光标、「正在识别下一段…」）、「离线优先 · 文件不出本机」「在线续跑会重新上传音频并按量计费」、以及把「进程不在了」诚实地显示成「已中断」而不是假进度——这些在任何别的工具里都不成立。可替换的是：288px 侧栏 + 字标 + 主题 pill、整幅虚线拖放区、全大写等宽眉题、白色 pill CTA、近黑画布。DESIGN.md 自己写明灵感来源，控制台构图更接近营销页而不是操作台。判定约 70/30 产品特异性。

**Deterministic scan**：`impeccable detect` 对 `frontend/src frontend/index.html frontend/task.html` 只报 1 条 warning —— `overused-font`（`index.css:210` Geist Mono）。这是**假阳性**：DESIGN.md 明确把 Inter（Universal Sans 替身）与 Geist Mono（品牌配套等宽）写进承诺，换字体才是偏离设计系统。无其他机械命中。

**Visual overlays**：未注入。`live-server` 会向 HTML 入口写入注入脚本，本次为保护工作区未启动；改用无头 Chromium 的 computed-style 证据替代（见 Run Notes）。

## Overall Impression

一个已经想清楚的工作台：失败可续跑、分片可见、离线默认，这些承诺在界面上是可见的。主要缺口不在视觉，而在**恢复路径与全局设置的位置**：最需要动作的两个入口（续跑、热词/模型设置）都在首屏之外或某条历史的标签里；其次是状态词与语言的三种写法，以及键盘用户看不到的模式开关焦点。没有 P0，26/40。

## What's Working

1. **诚实的失败生命周期**：死进程识别、保留已完成分片、只在未运行时显示续跑、文案说明留下了什么——把产品原则 2 变成界面事实。
2. **字幕工作台**：时间码沟、当前行光标与橙色底、滚轮即暂停跟随、无 SRT 时回退分片文本、LIVE 状态。这是页面存在的理由，做得完整。
3. **克制的渐进披露**：离线不显示密钥、高级设置折叠、思考过程折叠、主题首帧恢复、尊重 reduced-motion。

## Priority Issues

- **[P1] 恢复入口在首屏之外** — `task.tsx` 失败卡原先排在 `ResultTabs` 之后，1440×900 下续跑按钮 y=940（/t/2）与 y=895（/t/4）。等待二十分钟后用户看到「可续跑」却看不到按钮。修：失败卡移到标签之上，或把续跑放进进度卡；错误只留一处。→ `$impeccable harden`
- **[P1] 全局设置被困在单条任务里** — 热词、总结模型/密钥/提示词是全局的，却只能点开某条历史的「设置」标签；控制台「更多设置」只有语言/引擎。首次使用者无法在转录前录入专名。修：侧栏级「设置」入口，任务内标签保留为深链。→ `$impeccable layout`
- **[P1] 键盘/辅助技术在最关键的地方失效** — 模式 radio 是 sr-only，pill 上没有焦点样式；密钥输入无显式标签、保存/清除按钮同名重复；历史每行有 2 个不可见 tab 停靠点；32px 删除按钮。修：pill `:has(input:focus-visible)` 焦点环、`htmlFor`/`id` 与带引擎名的按钮名、行级菜单或单一动作、≥44px 目标、跳转链接。→ `$impeccable harden`
- **[P2] 一个状态三个名字 + 会撒谎的跟随开关** — 侧栏「失败」/详情「已中断」/眉题 NEEDS ATTENTION；完成的任务也显示「已暂停跟随」。修：统一词表（失败 / 已中断 / 停止中）；跟随只在运行时出现。→ `$impeccable clarify`
- **[P2] 移动端历史压过任务** — 844px 视口里 rail 占 525px，控制台 H1 在 y≈557，任务标签在 y≈751；45vh 历史不能折叠。修：<lg 只列最近 3 条 + 「全部任务」披露；任务页把 main 放到历史之前；保留「文件不出本机」。→ `$impeccable adapt`

## Persona Red Flags

**Alex（熟练用户）**：无法在开跑前设置热词；不能在字幕里选中错名加入热词；50 条历史无检索；API 已有引擎费用/上限/时间戳信息但界面没显示（现已补提示行）；没有新建转录快捷键；文件和路径两个输入同时存在时文件静默优先。

**Sam（键盘/AT）**：模式开关无可见焦点（已修）；两个「粘贴密钥」输入框和四个保存/清除按钮无法区分（已修）；历史行每行 2 个不可见 tab 停靠点（未修）；删除 32×32、跟随 30px、文件位置 16px 目标；10px 时间码；整块 80 行字幕滚动容器带 `aria-live` 会一次性播报（已改为列表语义 + 底栏 status）。

**Riley（压力测试）**：续跑按钮曾在首屏外（已修）；「失败/已中断」歧义（已修）；一键停止长任务无确认；界面承诺「按量计费」但没有费用预估；无输入提交返回 400 后只有灰字提示（现已本地拦截并 role=alert）。

## Minor Observations

- 同页两处字数不一致：页头 `1,555 CHARACTERS` vs 文稿页脚 `1,586 个字符`（已统一为任务字数）。
- 在线流程从不调用 `/api/estimate`，界面说「按量计费」却没有数字。
- 文件与路径两个来源竞争、文件静默优先。
- 上传提示格式与 `accept` 列表不一致（已补 mov）。
- 浏览器标题固定为「任务 · 转录」（现已跟随任务名）。
- 「已暂停跟随」在完成页无意义（已修）。

## Questions to Consider

1. 如果产品承诺是「只需改专名」，为什么改专名要离开错误行、去找某条任务的设置标签？「选中错名 → 加入热词」会改变什么？
2. 如果历史是高频表面，为什么它只是 288px 侧栏，而一次性的表单占据整页？
3. 当产物固定是 srt 时，「auto（按产物…）」还是真选择吗？界面是否应该直接解析并显示一个引擎、价格与时间戳能力？

Questions skipped: 用户在调用时已要求「直接走全流程」，优先方向与范围预先授权（critique → polish），故不再停留提问。

## Postscript — Assessment B 补记（同日，B 子代理延迟返回）

B 子代理 (8bfdbb1b) 实际完成了评估，报告：`/tmp/transcript-impeccable/assessment-b.md`。因此本快照的 "B leg inline / degraded" 标记只描述报告发布时点，最终证据为双代理完整。

B 的补充证据（pinned build `main-BvKKazME.js` / `task-CAcBvhk7.js`）：
- 浏览器 overlay 注入成功：`/t/1` 81 条（80 × 10px 时间码 undersized-ui-text + 1 kicker），`/` 2 条；overlay 可见（80 个 `.impeccable-overlay` 徽标）。
- 对比度：`/` 与 `/t/1` 两个主题 0 AA 违规；浅色焦点环仅 2.9:1（<3:1）；`/t/2` 错误文字 4.49:1（临界）；禁用项 3.04/2.72（WCAG 豁免）。
- 响应式：390/768 下历史在正文之前，控制台提交按钮 y=981/948（低于首屏）；无横向溢出。
- 可访问名：6 个「删除」按钮同名；两个 `<aside>` 未命名；文稿面板仍有整块 `aria-live`。
- 触摸目标：10–11 个控件 <44×44；「在访达中显示」「文件位置」16px 高，属 WCAG AA 24×24 失败。

B 返回后已追加修复（见下方），snapshot 保持 open 直到移动端与剩余 a11y 项清零。

### Follow-up fixes applied after B
- 文稿面板去掉 `aria-live`，改 `aria-label="文稿内容"`；状态栏 `role=status` 承担播报。
- 删除按钮可访问名带上任务标题；两个 `<aside>` 分别命名「导航与历史」「任务信息」。
- 浅色 `--ring` 提高到 0.62（合成对比 ~5.0:1）；提交按钮焦点环 1px → 2px。
- 移动端历史限高 45vh → 132px（约 3 条）：390 下控制台提交按钮 y 981 → 741（进入首屏），任务页 h1 y 630 → 382。
- 模式 pill 32 → 40px；「在访达中显示」「文件位置」16 → 32px；品牌链接 20 → 32px。
- 侧栏文件名加 `title`（长文件名截断可悬停看全）。
- 禁用导出项 opacity 0.65 → 0.8。
- 未修（backlog）：10px 时间码（品牌密度取舍）、历史行双 tab 停靠点、模型 combobox 缺 aria-activedescendant、在线费用预估未接 `/api/estimate`。

### Follow-up fixes, round 2（继续优化）
- **停止确认**：进度卡的「停止转录」改为两段式（第一次变「再点一次，确认停止」，4 秒回落），与删除的二次确认一致；不再一键中断长任务。
- **已用时**：运行中的进度卡显示「已用 mm:ss」，每 30 秒刷新一次；后端新增 `tasks.started_at`（迁移补列），job 每次真正开跑写入，续跑不继承旧时长。旧库兼容（列为 NULL 时回退 created_at）。
- **在线费用预估**：在线模式 + 本机路径时调用既有 `/api/estimate`（500ms 防抖），显示「预计 时长 · 费用约 $x（按实际用量计费）」；选中的浏览器文件在提交前不上传，故不预估；路径不存在时显示可读错误。
- **时间码可读性**：10px/48px → **11px/54px**，无截断（B 的 80× undersized-ui-text 是同一模式，此项收紧到 11px；未追到 12px 以保留密度）。
- **触控尺寸**：主题按钮 36→40；导出行 38→40；侧栏删除/停止 32→36（窄屏 40）。
- **文档同步**：DESIGN.md 更新两处实现约定（中文含义标签 + 技术拉丁 token；窄屏历史 132px 上限）。

验证：`npm run build` ✓；前端单测 11/11 ✓；pytest 引擎/标题通过、`test_web` 仍只余改动前既有失败；无头复测「预计 1:33 · 费用约 $0.003」「已用 04:17」「再点一次，确认停止」均生效；11px 时间码 `clipped=false`。

### Follow-up fixes, round 3（继续优化）
- **历史搜索**：侧栏在 ≥6 条任务时出现搜索框（仅宽屏），按标题/文件名即时过滤；`/` 聚焦、`Esc` 清空并失焦；无匹配显示「没有匹配的任务。」。任务多时不必再靠滚动找记录。
- **模型选择 combobox 语义**：输入框补 `aria-autocomplete="list"` 与 `aria-activedescendant`；选项改为 `role="option" tabIndex={-1}`（焦点留在输入框），上下键移动高亮时自动滚入可视区。复测 activedescendant 指向 `summaryModelOption-0`。
- **浅色拖放区边界**：虚线框 `#deded8`（~1.2:1）→ `#8f8f87`（~3.2:1），浅色画布上终于能看出可拖放区域。

验证：`npm run build` ✓；前端单测 11/11 ✓；Playwright 复测搜索过滤/清空、`/` 聚焦、combobox aria、浅色边框均通过。历史行双 tab 停靠点未动（需要行级操作菜单，属下一步结构性改动）。

### Follow-up fixes, round 4（首次使用 + 提交错误）
- **首次使用说明**：没有历史任务时，控制台在表单下方显示三条事实：离线在本机跑/首次会加载或下载模型；产物是源文件旁的 .txt 与 .srt；在线引擎要先在「设置」填密钥。有历史后自动隐藏（不塞进日常视图）。
- **空状态文案**：侧栏「还没有任务」改为「还没有任务。拖入一个文件开始第一次转录。」，给出下一步动作。
- **提交失败可见**：进度区新增 `role="alert"` 的错误行；提交 400/连接失败时显示红色可读错误，并把「完成后会显示产物」的自相矛盾提示收起；同一位置不再只有一行灰字。
- 复测：空库页 firstRun 可见、有历史隐藏；提交不存在路径显示「文件不存在：…」且 foot 提示隐藏；前端单测 11/11，build 通过。
- 仍未清：历史行双 tab 停靠点、移动端历史先于正文、44px（AAA）触控目标。
