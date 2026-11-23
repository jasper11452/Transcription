# Business Rules — transcript

At extraction: 140 confirmed rules (2 P0); later steps may add or correct rules below. Each citation was checked by a second agent that read the cited lines; 0 candidate rules were refuted and left out.

| ID | Name | Category | Priority | Source | Confidence |
|---|---|---|---|---|---|
| RULE-001 | Deduplicate only at chunk boundaries and never drop content | Calculation | P0 | `src/transcript/merge.py:82-119` | Medium |
| RULE-002 | Progress bar fill is a left-shift of a full-width band, not a width change | Calculation | P1 | `frontend/src/components/ui/progress.tsx:9-22` | Medium |
| RULE-003 | Tab underline is placed by pixel measurement, animated only on tab change | Calculation | P1 | `frontend/src/components/ui/tabs.tsx:59-104` | High |
| RULE-004 | Subtitle source precedence: saved SRT file beats live chunks | Calculation | P1 | `frontend/src/task.tsx:172-173` | High |
| RULE-005 | Transcript text source: saved TXT file beats chunk text | Calculation | P1 | `frontend/src/task.tsx:269-273` | High |
| RULE-006 | SRT parsing: block layout, timestamp format, and dropped entries | Calculation | P1 | `frontend/src/task.tsx:61-79` | High |
| RULE-007 | Only completed chunks feed the live subtitle/text view | Calculation | P1 | `frontend/src/task.tsx:85-102` | Medium |
| RULE-008 | Sentence-splitting rules for subtitle lines | Calculation | P1 | `src/transcript/align.py:118-156` | High |
| RULE-009 | Fallback time distribution when no usable timestamps exist | Calculation | P1 | `src/transcript/align.py:159-222` | High |
| RULE-010 | Character-level time mapping with interpolation and a monotonic-time invariant | Calculation | P1 | `src/transcript/align.py:34-104` | High |
| RULE-011 | Chunk plan budget and the chunk-length invariant | Calculation | P1 | `src/transcript/chunking.py:37-93` | Medium |
| RULE-012 | Cut points land on silence gaps in preference to hard cuts | Calculation | P1 | `src/transcript/chunking.py:53-79` | High |
| RULE-013 | Speaker label assignment by longest overlap | Calculation | P1 | `src/transcript/diar.py:193-211` | High |
| RULE-014 | Effective chunk length cap is the smaller of the configured max and the engine'… | Calculation | P1 | `src/transcript/engines/base.py:163-171` | Medium |
| RULE-015 | Bcut upload splits the audio into server-sized pieces and chains their ETags | Calculation | P1 | `src/transcript/engines/bcut.py:138-184` | Medium |
| RULE-016 | Bcut utterances become segments: milliseconds to seconds, empty ones dropped, t… | Calculation | P1 | `src/transcript/engines/bcut.py:238-252` | High |
| RULE-017 | DashScope word-level timestamps are converted from milliseconds and the text is… | Calculation | P1 | `src/transcript/engines/dashscope.py:155-188` | High |
| RULE-018 | Offline transcription takes its text from the local ASR model and its timeline… | Calculation | P1 | `src/transcript/engines/offline.py:84-120` | High |
| RULE-019 | Cost attribution differs per engine: local and anonymous are free, the paid srt… | Calculation | P1 | `src/transcript/engines/openrouter.py:112-113` | High |
| RULE-020 | OpenRouter returns sentence-level segments and the authoritative cost of the ca… | Calculation | P1 | `src/transcript/engines/openrouter.py:94-116` | High |
| RULE-021 | Hot-word list composition and caps | Calculation | P1 | `src/transcript/glossary.py:150-158` | High |
| RULE-022 | Glossary replacement order and change counting | Calculation | P1 | `src/transcript/glossary.py:161-175` | High |
| RULE-023 | Cost is summed across chunks, but audio seconds are never aggregated | Calculation | P1 | `src/transcript/merge.py:122-144` | High |
| RULE-024 | Overlap detection between consecutive chunks (dedup judgement) | Calculation | P1 | `src/transcript/merge.py:13-67` | High |
| RULE-025 | SRT timestamp format and rounding | Calculation | P1 | `src/transcript/models.py:100-110` | Medium |
| RULE-026 | Cost pre-estimate per engine and artifact | Calculation | P1 | `src/transcript/pipeline.py:92-106` | High |
| RULE-027 | Summary input batching and compression loop | Calculation | P1 | `src/transcript/summary.py:219-251` | High |
| RULE-028 | Speech activity gating: drop micro-spans and bridge short pauses | Calculation | P1 | `src/transcript/vad.py:31-61` | High |
| RULE-029 | 任务进度百分比由已完成分片数推算 | Calculation | P1 | `src/transcript/web/jobs.py:92-104` | High |
| RULE-030 | Streaming summary shows title/overview/key points as soon as each field closes | Calculation | P2 | `frontend/src/lib/summary-stream.ts:80-91` | High |
| RULE-031 | Model list filtering and display cap of 60 | Calculation | P2 | `frontend/src/task.tsx:384-394` | High |
| RULE-032 | Progress percentage: from SSE current/total, clamped at the card | Calculation | P2 | `frontend/src/task.tsx:948-951` | High |
| RULE-033 | Small corner radii are derived from a single radius token | Calculation | P2 | `frontend/tailwind.config.js:88-92` | High |
| RULE-034 | 模型清单里的每百万 token 单价 | Calculation | P2 | `src/transcript/web/app.py:552-570` | Medium |
| RULE-035 | Saved preference is only accepted as an exact, known value | Validation | P1 | `frontend/public/theme.js:7-14` | High |
| RULE-036 | A row offers Stop while it is running and Delete only when it is not | Validation | P1 | `frontend/src/components/history-sidebar.tsx:153-168` | High |
| RULE-037 | The component layer performs no validation; all field rules are the caller's | Validation | P1 | `frontend/src/components/ui/input.tsx:6-21` | Medium |
| RULE-038 | One error contract for every API call | Validation | P1 | `frontend/src/lib/api.ts:12-19` | High |
| RULE-039 | Agent summary settings: accepted fields, key retention, prompt fallback | Validation | P1 | `frontend/src/lib/api.ts:66-80` | High |
| RULE-040 | Saving secrets: a blank field keeps the stored secret and a masked preview is n… | Validation | P1 | `frontend/src/lib/api.ts:94-105` | Medium |
| RULE-041 | Engine is selectable only when ready; missing credentials are named | Validation | P1 | `frontend/src/main.tsx:20-25` | High |
| RULE-042 | Audio source is required and an attached file beats a typed path | Validation | P1 | `frontend/src/main.tsx:203-219` | Medium |
| RULE-043 | Credential save/clear payload: empty input still saves an empty key | Validation | P1 | `frontend/src/main.tsx:42-55` | High |
| RULE-044 | Saved output files are only read for a finished, non-running task | Validation | P1 | `frontend/src/task.tsx:157-170` | High |
| RULE-045 | Model list cannot be fetched while the connection settings have unsaved edits | Validation | P1 | `frontend/src/task.tsx:343-361` | Medium |
| RULE-046 | Hot words: separators, 40-character truncation, exact-match dedupe, 80-word cap | Validation | P1 | `frontend/src/task.tsx:420-433` | High |
| RULE-047 | Summary settings can only be saved with a non-empty model and Base URL | Validation | P1 | `frontend/src/task.tsx:641` | High |
| RULE-048 | Summary cannot be started until a working model connection exists | Validation | P1 | `frontend/src/task.tsx:753-755` | Medium |
| RULE-049 | Working-copy audio contract and its verification | Validation | P1 | `src/transcript/audio.py:162-178` | High |
| RULE-050 | Input file eligibility check | Validation | P1 | `src/transcript/audio.py:44-91` | High |
| RULE-051 | Credential value sanitization on save | Validation | P1 | `src/transcript/config.py:213-246` | High |
| RULE-052 | A task only starts if the credentials the chosen engine actually needs are pres… | Validation | P1 | `src/transcript/engines/base.py:155-160` | High |
| RULE-053 | Online capability is 'ready' when at least one online engine needs no credentia… | Validation | P1 | `src/transcript/engines/base.py:206-210` | Medium |
| RULE-054 | Bcut rejects anything that is not a non-empty mp3 before opening the network ca… | Validation | P1 | `src/transcript/engines/bcut.py:98-107` | High |
| RULE-055 | DashScope upstream error codes are mapped to actionable fatal errors before gen… | Validation | P1 | `src/transcript/engines/dashscope.py:129-146` | High |
| RULE-056 | DashScope container whitelist decides the declared audio format and rejects unk… | Validation | P1 | `src/transcript/engines/dashscope.py:66-73` | High |
| RULE-057 | DashScope blocks a chunk longer than its 300s ceiling locally instead of spendi… | Validation | P1 | `src/transcript/engines/dashscope.py:75-82` | Medium |
| RULE-058 | Upload-size rejections from the srt engine are recognised by message text and r… | Validation | P1 | `src/transcript/engines/openrouter.py:80-87` | High |
| RULE-059 | HTTP failure classification: retryable or fatal | Validation | P1 | `src/transcript/errors.py:40-52` | High |
| RULE-060 | Glossary file grammar and entry validation | Validation | P1 | `src/transcript/glossary.py:49-140` | High |
| RULE-061 | An srt task is refused when the engine cannot supply timestamps | Validation | P1 | `src/transcript/pipeline.py:347-352` | Medium |
| RULE-062 | SRT refuses inverted timestamps and numbers only surviving lines | Validation | P1 | `src/transcript/render.py:28-48` | High |
| RULE-063 | 提交任务前的输入校验（模式 / 产物 / 在线引擎 / 源文件） | Validation | P1 | `src/transcript/web/app.py:256-292` | High |
| RULE-064 | 上传文件 2GB 上限 | Validation | P1 | `src/transcript/web/app.py:265-281` | High |
| RULE-065 | Base URL 校验：只允许干净的本机/服务地址 | Validation | P1 | `src/transcript/web/app.py:457-477` | High |
| RULE-066 | Prompt and hot-word limits | Validation | P1 | `src/transcript/web/app.py:480-504` | Medium |
| RULE-067 | 内联到页面的 JSON 必须转义尖括号与行分隔符 | Validation | P1 | `src/transcript/web/app.py:73-82` | High |
| RULE-068 | 服务启动时的前端产物完整性硬门槛 | Validation | P1 | `src/transcript/web/frontend.py:29-50` | High |
| RULE-069 | Export actions appear only for artifacts that actually exist | Validation | P2 | `frontend/src/task.tsx:1002-1013` | High |
| RULE-070 | Summary result normalization and length caps | Validation | P2 | `src/transcript/summary.py:109-137` | High |
| RULE-071 | Summary output contract handed to the model | Validation | P2 | `src/transcript/summary.py:34-68` | High |
| RULE-072 | Task and chunk status lifecycle; no partial products | Lifecycle | P0 | `src/transcript/pipeline.py:316-326` | Medium |
| RULE-073 | Theme changes propagate across tabs | Lifecycle | P1 | `frontend/public/theme.js:84-89` | High |
| RULE-074 | Chunk-level transcription state | Lifecycle | P1 | `frontend/src/lib/types.ts:74-84` | Medium |
| RULE-075 | Console submission lifecycle: queue, stream, and terminal outcome | Lifecycle | P1 | `frontend/src/main.tsx:243-267` | High |
| RULE-076 | Detail-page event stream connects only while work is live and closes on result | Lifecycle | P1 | `frontend/src/task.tsx:1064-1099` | High |
| RULE-077 | Chunk list merge keyed by chunk index | Lifecycle | P1 | `frontend/src/task.tsx:1085-1090` | High |
| RULE-078 | Summary lifecycle and 700 ms polling, ending in a task-title refresh | Lifecycle | P1 | `frontend/src/task.tsx:718-739` | High |
| RULE-079 | Enable / regenerate / retry summary all use the same enable action | Lifecycle | P1 | `frontend/src/task.tsx:741-751` | High |
| RULE-080 | Resuming an online task costs money and needs an explicit second confirmation | Lifecycle | P1 | `frontend/src/task.tsx:913-932` | Medium |
| RULE-081 | A running task with no live process is reported as interrupted, not as running | Lifecycle | P1 | `frontend/src/task.tsx:945-951` | Medium |
| RULE-082 | Resuming an interrupted task keeps the engine it originally ran on instead of r… | Lifecycle | P1 | `src/transcript/engines/base.py:147-152` | High |
| RULE-083 | Retry policy: exponential backoff for recoverable errors only | Lifecycle | P1 | `src/transcript/pipeline.py:109-134` | High |
| RULE-084 | Cancellation semantics: stop at a chunk boundary and keep what is done | Lifecycle | P1 | `src/transcript/pipeline.py:312-314` | High |
| RULE-085 | Speaker separation is gated and never blocks the transcript | Lifecycle | P1 | `src/transcript/pipeline.py:331-345` | High |
| RULE-086 | Resume reuses completed chunks and re-runs only two special cases | Lifecycle | P1 | `src/transcript/pipeline.py:428-457` | Medium |
| RULE-087 | Concurrency policy: serial offline, parallel online | Lifecycle | P1 | `src/transcript/pipeline.py:545-557` | High |
| RULE-088 | Agent summary state machine | Lifecycle | P1 | `src/transcript/summary.py:280-366` | Medium |
| RULE-089 | Task lifecycle flags drive cancel/resume/delete | Lifecycle | P1 | `src/transcript/web/app.py:143-175` | Medium |
| RULE-090 | SSE 进度流：先补历史，再实时推，空闲时心跳 | Lifecycle | P1 | `src/transcript/web/jobs.py:172-199` | High |
| RULE-091 | Transition lock is always released, with a hard timeout backstop | Lifecycle | P2 | `frontend/public/theme.js:46-53` | High |
| RULE-092 | Toggle flips to the opposite of the currently applied theme | Lifecycle | P2 | `frontend/public/theme.js:79-82` | High |
| RULE-093 | Stop is not applied optimistically; row state changes only on the next poll | Lifecycle | P2 | `frontend/src/components/history-sidebar.tsx:104-111` | Medium |
| RULE-094 | Dialogs are always modal with an overlay and an always-present close control | Lifecycle | P2 | `frontend/src/components/ui/dialog.tsx:26-48` | Medium |
| RULE-095 | Theme preference resolution precedence | Policy | P1 | `frontend/public/theme.js:15-21` | High |
| RULE-096 | Storage unavailability degrades to session-only theming | Policy | P1 | `frontend/public/theme.js:33-37` | High |
| RULE-097 | Live OS theme changes are honoured only without an explicit user preference | Policy | P1 | `frontend/public/theme.js:83` | High |
| RULE-098 | Permanent delete requires a second click within a 4-second window | Policy | P1 | `frontend/src/components/history-sidebar.tsx:46-66` | Medium |
| RULE-099 | Button style contract: pill shape, weight 400, no shadow, and only the primary… | Policy | P1 | `frontend/src/components/ui/button.tsx:7-38` | Medium |
| RULE-100 | Fallback console state when the boot payload is missing | Policy | P1 | `frontend/src/lib/types.ts:172-186` | High |
| RULE-101 | Console defaults: offline by default, and the credentials deep link forces onli… | Policy | P1 | `frontend/src/main.tsx:104-125` | High |
| RULE-102 | API keys are paste-only and never rendered back in clear | Policy | P1 | `frontend/src/main.tsx:69-80` | High |
| RULE-103 | Restoring defaults does not touch the API key or the hot words | Policy | P1 | `frontend/src/task.tsx:439-446` | High |
| RULE-104 | Enabling a summary discloses transcript text and key to the configured Base URL | Policy | P1 | `frontend/src/task.tsx:819` | Medium |
| RULE-105 | Configuration precedence and legacy settings compatibility | Policy | P1 | `src/transcript/config.py:131-201` | High |
| RULE-106 | Credentials are only ever shown masked and never persisted outside the config f… | Policy | P1 | `src/transcript/config.py:58-73` | High |
| RULE-107 | Engine resolution: mode, artifact and per-task override decide which engine runs | Policy | P1 | `src/transcript/engines/base.py:128-144` | Medium |
| RULE-108 | Bcut task result is polled every 1.5s until state 4 or a 300s deadline | Policy | P1 | `src/transcript/engines/bcut.py:195-223` | High |
| RULE-109 | A 412 ban from the free anonymous engine triggers a 90-second self-imposed cool… | Policy | P1 | `src/transcript/engines/bcut.py:72-88` | Medium |
| RULE-110 | 本机配置文件写入策略：原子替换、600 权限、保留用户内容 | Policy | P1 | `src/transcript/web/app.py:679-696` | High |
| RULE-111 | One theme wipe transition at a time; clicks during a transition are dropped | Policy | P2 | `frontend/public/theme.js:55-62` | High |
| RULE-112 | Animation is skipped when unsupported or when reduced motion is requested | Policy | P2 | `frontend/public/theme.js:58-61` | High |
| RULE-113 | Sidebar refresh cadence: 2 s while work is in flight, 10 s otherwise | Policy | P2 | `frontend/src/components/history-sidebar.tsx:74-93` | High |
| RULE-114 | History list is capped at the 50 newest tasks | Policy | P2 | `frontend/src/components/history-sidebar.tsx:79` | High |
| RULE-115 | Badge colour contract: no coloured background, destructive is red text on a hai… | Policy | P2 | `frontend/src/components/ui/badge.tsx:6-22` | High |
| RULE-116 | Elevation model: hairline borders inline, shadows only on floating overlays | Policy | P2 | `frontend/src/components/ui/dropdown-menu.tsx:51-67` | Medium |
| RULE-117 | Form-field chrome is identical across text input, textarea and select trigger | Policy | P2 | `frontend/src/components/ui/input.tsx:5-24` | High |
| RULE-118 | Toast auto-dismiss duration and swipe axis are library defaults, not stated in… | Policy | P2 | `frontend/src/components/ui/toast.tsx:24-39` | Low |
| RULE-119 | Single toast region: full-width top on phones, bottom-right capped at 420px on… | Policy | P2 | `frontend/src/components/ui/toast.tsx:9-22` | High |
| RULE-120 | History is bucketed by local calendar day: today / yesterday / last 7 days / ea… | Policy | P2 | `frontend/src/lib/task-groups.ts:22-34` | Medium |
| RULE-121 | Online mode alone exposes the engine picker and the credential panel | Policy | P2 | `frontend/src/main.tsx:127-143` | High |
| RULE-122 | Subtitle vs transcript classification drives the default tab and the ready label | Policy | P2 | `frontend/src/task.tsx:185-186` | High |
| RULE-123 | UI colors resolve through CSS custom-property tokens, never literal values | Policy | P2 | `frontend/tailwind.config.js:11-63` | Medium |
| RULE-124 | Display/heading typography uses a fixed negative letter-spacing pair | Policy | P2 | `frontend/tailwind.config.js:93-97` | Medium |
| RULE-125 | Frontend build output must land at a fixed path with a Vite manifest for backen… | Policy | P2 | `frontend/vite.config.ts:16-27` | High |
| RULE-126 | Configuration file permission hygiene | Policy | P2 | `src/transcript/config.py:203-210` | High |
| RULE-127 | The engine chooser shows a fixed catalog with per-engine readiness, limits and… | Policy | P2 | `src/transcript/engines/base.py:174-203` | High |
| RULE-128 | DashScope defaults transcription to Chinese with inverse text normalisation on | Policy | P2 | `src/transcript/engines/dashscope.py:91-98` | High |
| RULE-129 | Offline fallback when no timeline can be produced re-runs the same call and is… | Policy | P2 | `src/transcript/engines/offline.py:100-110` | Medium |
| RULE-130 | Offline ASR models are cached process-wide and reloaded only when the configure… | Policy | P2 | `src/transcript/engines/offline.py:21-35` | Medium |
| RULE-131 | OpenRouter sends at most 50 hotwords as a prompt prefix | Policy | P2 | `src/transcript/engines/openrouter.py:61-62` | High |
| RULE-132 | Glossary changes are disclosed in the products | Policy | P2 | `src/transcript/glossary.py:178-182` | High |
| RULE-133 | Product output directory fallback when the source directory is not writable | Policy | P2 | `src/transcript/pipeline.py:565-577` | High |
| RULE-134 | Raw JSON provenance record | Policy | P2 | `src/transcript/pipeline.py:585-645` | High |
| RULE-135 | SRT line wrapping for long segments | Policy | P2 | `src/transcript/render.py:12-25` | High |
| RULE-136 | Speaker-labelled text output groups consecutive segments | Policy | P2 | `src/transcript/render.py:51-88` | High |
| RULE-137 | Extracting a summary goes through the stored transcript, not the audio | Policy | P2 | `src/transcript/summary.py:336-347` | High |
| RULE-138 | 模型清单按 Base URL 缓存 10 分钟 | Policy | P2 | `src/transcript/web/app.py:524-538` | High |
| RULE-139 | 产物正文预览截断到 20 万字符 | Policy | P2 | `src/transcript/web/app.py:606-612` | High |
| RULE-140 | 控制台默认值：离线优先、srt、中文、引擎自动 | Policy | P2 | `src/transcript/web/app.py:68` | High |

## Calculation

### RULE-001: Deduplicate only at chunk boundaries and never drop content
**Category:** Calculation
**Priority:** P0
**Source:** `src/transcript/merge.py:82-119`
**Plain English:** Duplicated text is removed only where two chunks were stitched together, and a piece is only discarded if what remains after the cut is non-empty; overlapping timestamps are repaired separately so the player never shows two lines at once.
**Specification:**
  Given Chunk A's last segment '…我们下周一开会。' (start 100.0, end 103.0) and chunk B's first segment '开会。请准备材料' (start 102.9, end 106.0)
  When  Segment groups are merged in chunk order
  Then  The earlier segment's end is pulled back to max(prev.start + 0.05, 102.9); the repeated '开会。' is stripped from the head and, because '请准备材料' remains, it is emitted as a segment starting at 102.9 — no text is lost; segments inside a chunk are never deduplicated against each other
**Parameters:** Minimum segment duration 0.05s (merge.py:104,112); leading punctuation stripped after a cut: '。！？!?…，,；;、：:. \n\t' (merge.py:13,79,107); dedup is text-based at the chunk boundary only (merge.py:88-92 records the 87-minute lesson: sentence-level dedup lost 111 characters)
**Edge cases handled:** whitespace-only segments are filtered before merging; if stripping the overlap leaves nothing, the head segment is dropped and the rest of that chunk is kept; an overlap of 0 means plain concatenation; segment order inside a group is by (start, end)
**Confidence:** Medium — P0 panel doubts spec fidelity: P0 justified: the rule guards the integrity of the deliverable the tool exists to produce. Dedup happens only at chunk boundaries (merge.py:99-117), a piece is discarded only when the remainder is empty (merge.py:107-117), and the timeline is repaired so the player never shows two lines at once (merge.py:103-104). A wrong result here silently and irreversibly delete…

### RULE-002: Progress bar fill is a left-shift of a full-width band, not a width change
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/components/ui/progress.tsx:9-22`
**Plain English:** The progress bar never resizes its filled band; it renders a full-width band and slides it left by whatever percentage is still missing, so 42% progress means the band is moved left by 58% of the track.
**Specification:**
  Given A transcription job reported as 42% complete (value = 42, no caller className override)
  When  The Progress component renders
  Then  The indicator gets style transform: translateX(-58%) and the visible filled portion of the track is 42% wide (filled% = value, offset% = 100 - value)
**Parameters:** Formula: translateX(-(100 - (value || 0))%). value fallback: `value || 0` (undefined/null/0 all render an empty bar). Track: h-1 (4px) w-full rounded-full bg-canvas-soft. Indicator: h-full w-full flex-1 bg-sunset, transition-all. No explicit min/max/clamp anywhere in this file; Radix Progress defaults (max 100) are the only bound.
**Edge cases handled:** value omitted, null or 0 -> 'value // 0' yields 0 -> translateX(-100%), bar shows empty; value = 100 -> translateX(-0%), full bar; value > 100 not clamped by this file (e.g. 120 -> translateX(+20%), band pushed past the right edge); negative value not clamped (e.g. -5 -> translateX(-105%), extra empty gutter visible); fractional values (42.5) pass straight to CSS
**Suspected defect:** No clamping to 0..100 in the component; only Radix's Root max prop (never passed here) constrains the input. A job reporting >100% (retry double-count, stale poll) draws a visibly wrong bar instead of pinning at 100%.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Read /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/components/ui/progress.tsx (lines 1-27). The cited lines 9-22 do exactly what the rule states: the Radix Indicator is always 'h-full w-full flex-1' (full-width band) and the fill is produced only by 'style={{ transform: 'translat…

### RULE-003: Tab underline is placed by pixel measurement, animated only on tab change
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/components/ui/tabs.tsx:59-104`
**Plain English:** One shared underline is moved and stretched to sit under the currently active tab: its horizontal offset is the active tab's left edge minus the list's left edge, and its 1px base width is stretched to the active tab's width; it animates only when the selected tab changes, and jumps instantly on first paint and on container resize.
**Specification:**
  Given A tab list whose left edge is at x=100px, with tabs [Summary, Transcript, Notes] where Notes occupies left=240px and width=72px, and the underline has already been placed once
  When  The user selects the Notes tab (value changes to "notes")
  Then  The underline gets transform: translateX(140px) scaleX(72px) with transform-origin left center, animated over 240ms cubic-bezier(0.33, 0.35, 0.45, 1)
**Parameters:** offset = activeBox.left - listBox.left (px, from getBoundingClientRect). stretch = activeBox.width (px) applied as scaleX to a 1px-wide bar. Bar geometry (frontend/src/index.css:272-281): width 1px, height 2px, bottom -1px (deliberately overlapping the container's 1px divider), transform-origin left center, transition 240ms cubic-bezier(0.33, 0.35, 0.45, 1), background var(--ink). Animate flag: true only when `placed` is already true; ResizeObserver always calls place(false) and a forced reflow (void bar.offsetWidth) commits the instant jump before the transition is restored.
**Edge cases handled:** no element with [data-state="active"] found -> place() returns early, underline keeps its previous position; first placement after mount -> animate=false (no slide-in on page entry); window/font resize -> ResizeObserver -> place(false) instant reposition; active tab removed from the DOM (e.g. conditional tab) -> early return leaves the line stale; TabUnderline must be rendered inside the TabsList container; listRef comes from the caller
**Suspected defect:** The underline is a square 2px bar anchored at bottom:-1px, but TabsList is styled rounded-full (tabs.tsx:14) with p-1; at the first and last tab the bar can contradict the pill's rounded corners. Also, unlike Button (motion-reduce:active:scale-100, button.tsx:11), TabUnderline has no prefers-reduced-motion opt-out, so the 240ms slide always runs.
**Confidence:** High

### RULE-004: Subtitle source precedence: saved SRT file beats live chunks
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/task.tsx:172-173`
**Plain English:** Once the finished subtitle file is available it is the authoritative view; live chunk output is only a temporary stand-in while the task runs, and the raw chunk text is the last resort.
**Specification:**
  Given a finished task whose SRT file loaded 42 lines, and 40 live chunk lines in memory
  When  the subtitle panel picks what to render
  Then  the 42 file lines are shown; file lines are ignored (empty) and the merged live lines are used only when the file list is empty; fallback chunk lines are used only when both are empty.
**Parameters:** lines = fileLines.length ? fileLines : liveLines.length ? liveLines : fallbackLines(chunks)
**Edge cases handled:** If reading the SRT fails, fileError is shown in the footer and rendering falls through to the live/fallback lists (task.tsx:164-168, 234).; The file is only fetched for a non-running, done, srt_exists task, so during a run the live list is always the source.
**Confidence:** High

### RULE-005: Transcript text source: saved TXT file beats chunk text
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/task.tsx:269-273`
**Plain English:** The transcript panel shows the saved plain-text export once it exists, and otherwise concatenates the text of finished chunks in order.
**Specification:**
  Given chunks idx0 text ' 大家好 ' (done), idx1 text '谢谢' (done), idx2 text '...' (running)
  When  the transcript panel builds its content
  Then  fileText is used if the TXT file was fetched; otherwise the panel shows '大家好' and '谢谢' on separate lines (each done chunk text trimmed, joined with a single newline, running/blank chunks excluded).
**Parameters:** Filter chunk.status==='done' && chunk.text.trim(); join with a newline; file text wins whenever non-empty (fileText || chunkText)
**Edge cases handled:** TXT is only fetched when the task is not running, status is done, and txt_exists is true (task.tsx:254-267).; The character counter in the footer counts the resulting string length, not the stored chunk char total.
**Confidence:** High

### RULE-006: SRT parsing: block layout, timestamp format, and dropped entries
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/task.tsx:61-79`
**Plain English:** The viewer parses SRT subtitle files itself: text is split into blocks on blank lines, each block must contain a '-->' timing line with HH:MM:SS,mmm timestamps, and any content line starting with '#' is treated as a comment and removed.
**Specification:**
  Given an SRT file whose bytes start with a BOM and contain '00:00:01,000 --> 00:00:02,500' followed by '你好'
  When  the subtitle panel loads the finished SRT
  Then  the line {start:1,end:2.5,text:'你好'} is produced; start/end in fractional seconds (HH*3600 + MM*60 + SS + ms/1000).
**Parameters:** Timestamp regex ^(\d+):(\d{2}):(\d{2})[,.]\d{3}$ (comma or dot accepted, exactly 2-digit MM/SS and 3-digit ms); block separator /\n\s*\n/; leading BOM and all \r stripped; text lines starting with '#' removed; multi-line text joined with a single space
**Edge cases handled:** A block without '-->' is dropped entirely.; A timestamp that does not match the regex yields NaN and the whole entry is dropped (Number.isFinite check).; An entry whose text is empty after trimming is dropped.; The first line of a block (the sequence number) is ignored because the parser starts reading text after the timing line.
**Confidence:** High

### RULE-007: Only completed chunks feed the live subtitle/text view
**Category:** Calculation
**Priority:** P1
**Source:** `frontend/src/task.tsx:85-102`
**Plain English:** While a transcription is still running, a segment is shown only after the engine has marked that audio chunk finished; unfinished or failed chunks contribute nothing, and a finished chunk with empty text contributes nothing.
**Specification:**
  Given chunks = [{idx:0,status:'done',text:'你好',segments:[],start:0,end:12},{idx:1,status:'running',text:'正在说',segments:[],start:12,end:24},{idx:2,status:'failed',text:'x'}]
  When  the detail page assembles the live subtitle list (mergeChunkLines) or the fallback list (fallbackLines)
  Then  only idx 0 appears, as one line {start:0,end:12,text:'你好'}; idx 1 and idx 2 are dropped; lines are sorted ascending by start. When a done chunk has non-empty segments, those segments are used instead of the chunk-level text.
**Parameters:** Eligibility key: chunk.status === 'done'; blank-text filter: chunk.text.trim() truthy (dropped in both mergeChunkLines and fallbackLines); segment preference: chunk.segments.length > 0; ordering: sort by chunk.start
**Edge cases handled:** A done chunk with segments: [] and blank text is dropped by mergeChunkLines (task.tsx:98-100) and by fallbackLines' filter (task.tsx:87).; fallbackLines is only reached when neither the file SRT nor the merged live lines produced anything (task.tsx:173).; The transcript panel uses the same eligibility but joins with a newline instead of producing timed lines (task.tsx:269-272).
**Suspected defect:** mergeChunkLines keeps the fallback line when chunk.text.trim() is non-empty, but a done chunk carrying both segments and text shows the segments only — the chunk text is silently discarded.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: the code at frontend/src/task.tsx:85-102 does exactly what the card claims. fallbackLines filters 'chunk.status === 'done' && chunk.text.trim()' then flatMaps to chunk.segments when non-empty, else one trimmed chunk-level line, sorted by start; mergeChunkLines filters 'status === 'done'' a…

### RULE-008: Sentence-splitting rules for subtitle lines
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/align.py:118-156`
**Plain English:** A transcript is broken into subtitle lines at sentence-ending punctuation always, at weaker punctuation only when the line is already long enough and does not end on a dangling lead-in word, and forcibly after 15 seconds of speech.
**Specification:**
  Given Text '第一，我们今天讨论预算。第二，明天再看排期。' with character timestamps where the span since the last cut reaches 6.0s at '，' and the tail after that comma is '今天讨论预算' (6 characters)
  When  Sentence ranges are computed for the aligned text
  Then  '。' always ends a line; '，' ends a line only if the window is >= 12 characters or >= 5.0s of speech AND the text after the previous punctuation is >= 4 characters — so '第一，' does not end a line, and the line breaks after '预算。'; if nothing else breaks, a break is forced once the timed span reaches 15.0s
**Parameters:** HARD_BREAK = '。！？!?…\n'; SOFT_BREAK = '，,；;、：:' (align.py:18-19); MAX_SEGMENT_S = 15.0; SOFT_BREAK_MIN_CHARS = 12; SOFT_BREAK_MIN_S = 5.0; MIN_TAIL_CHARS = 4 (align.py:21-25); MIN_SEGMENT_S = 0.35, minimum duration 0.05s (align.py:21,26)
**Edge cases handled:** the punctuation under consideration is excluded when measuring the tail, otherwise the rule could never fire; a window with no known timestamps skips the duration checks and relies on character count / the 15s rule alone; windows that are whitespace-only are removed; trailing text after the last boundary becomes a final range
**Confidence:** High

### RULE-009: Fallback time distribution when no usable timestamps exist
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/align.py:159-222`
**Plain English:** If alignment cannot produce a single timestamp, the text is still emitted in full with nominal, evenly spaced times — losing words is treated as far worse than inaccurate timing.
**Specification:**
  Given Text of 40 characters with no timestamps at all and no fallback_duration supplied
  When  build_segments falls back
  Then  Total nominal duration = max(1.0, 0.25 x 40) = 10.0s; the text is split into its sentence ranges and each piece gets step = max(0.35, 10.0/number_of_pieces) seconds in sequence starting at the offset
**Parameters:** nominal duration = max(1.0, 0.25 * len(text)) seconds (align.py:213); step = max(min_segment_s, total / len(pieces)) with min_segment_s = 0.35 (align.py:214); a real audio duration is used instead when provided and > 0 (align.py:213); empty text returns no segments (align.py:172-173)
**Edge cases handled:** one enormous piece still gets at least the minimum 0.35s step; the fallback reuses the same sentence-splitting rules as the normal path so output shape is consistent
**Confidence:** High

### RULE-010: Character-level time mapping with interpolation and a monotonic-time invariant
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/align.py:34-104`
**Plain English:** High-quality text without timestamps is mapped onto a word-timestamp skeleton character by character, unfilled characters get interpolated times, and the final segment times are forced to be non-decreasing so players and editors do not discard lines.
**Specification:**
  Given Skeleton characters '今天我们开会' with word times 10.0-10.4, 10.4-10.8, 10.8-11.2 and recognized text '我们今天开会' whose fourth character is flagged as replaced
  When  map_times and enforce_monotonic run
  Then  Matched characters keep their skeleton times; characters inside a 'replace' block are spread proportionally over the skeleton span; unmatched runs are linearly interpolated between known neighbours and flat-extended at the ends; afterwards every segment start is raised to at least the previous segment's end and every end is at least start + 0.05s
**Parameters:** Content characters are isalnum() only — punctuation and whitespace never participate in alignment (align.py:29-31); replace-block placement src = i1 + min(w_len-1, int(offset * w_len / max(1, j2-j1))) (align.py:84-87); MIN_SEGMENT_S = 0.35s, _MIN_DURATION_S = 0.05s (align.py:21,26); times rounded to 3 decimals (align.py:190-191,234-236)
**Edge cases handled:** empty skeleton or empty content returns all-None times, which pushes the caller into the fallback path; a character with no skeleton counterpart is the only case where a word may feel 'misplaced'; the contract is 'imprecise boundary', never a missing or reordered sentence; enforce_monotonic also drops whitespace-only segments
**Confidence:** High

### RULE-011: Chunk plan budget and the chunk-length invariant
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/chunking.py:37-93`
**Plain English:** Audio is cut into pieces whose total length (including the overlap grafted onto each side) never exceeds the chunk limit, and the pieces cover the whole recording with no gaps.
**Specification:**
  Given A 20-minute recording, chunk_min_s=30, chunk_max_s=120, chunk_overlap_s=0.5, so inner budget = 120 - 0.5 = 119.5s
  When  The chunk planner builds the cut plan
  Then  Every returned chunk has duration <= 120.0s; the chunks in order cover [0, duration] with adjacent chunks overlapping 0.5s total; the first chunk starts at 0.0 and the last ends at duration
**Parameters:** min_s default 30.0, max_s default 120.0, overlap_s default 0.5 (config.py:109-111); MIN_GAP_FOR_CUT_S=0.15, MIN_INNER_S=1.0 (chunking.py:16,18); inner = max(1.0, max_s - overlap); half-overlap = overlap/2 (chunking.py:42-46); single-chunk shortcut when duration <= min(min_s, inner) (chunking.py:48-49); pieces shorter than 0.01s dropped (chunking.py:85-86); final float guard end = min(end, start + max_s) (chunking.py:90)
**Edge cases handled:** duration <= 0 returns an empty plan; min_s <= 0 or max_s < min_s raises ValueError instead of planning; if every piece is filtered out, a single chunk covering the whole file is returned as a last resort; start is only extended leftward, end only rightward, so the plan never leaves [0, duration]
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: I read /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/chunking.py:37-93 and /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/config.py:109-111. With defaults min_s=30, max_s=120, overlap_s=0.5, the code computes inner = max(1.0, 120-0.5) = 119.5 (lin…

### RULE-012: Cut points land on silence gaps in preference to hard cuts
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/chunking.py:53-79`
**Plain English:** Where possible a cut is placed in the middle of a detected pause, but only a pause that still leaves the piece within budget; otherwise the audio is cut at a fixed position.
**Specification:**
  Given Speech spans with a 1.2s silence between them, cursor at 60.0s, inner budget 119.5s, target = min(30.0, 119.5) = 30.0s
  When  The planner looks for the next cut position
  Then  The cut is placed at the midpoint of a silence gap of at least 0.15s that is still <= cursor + inner; if no such gap exists (continuous speech) the cut is placed at cursor + inner; the cut is clamped to >= cursor + 1.0s and <= duration
**Parameters:** MIN_GAP_FOR_CUT_S = 0.15s (chunking.py:16); MIN_INNER_S = 1.0s (chunking.py:18); target = min(min_s, inner) (chunking.py:46); scan stops early once accumulated speech >= target at a silence (chunking.py:67-69) or >= inner without one (chunking.py:70-71)
**Edge cases handled:** a silence whose midpoint would exceed the budget breaks the scan and the best candidate found so far is used; span lists are sorted and clamped into [0, duration]; spans with end <= start are dropped; the span cursor advances past every span that ends at or before the new cut, so no span is considered twice
**Confidence:** High

### RULE-013: Speaker label assignment by longest overlap
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/diar.py:193-211`
**Plain English:** Each transcript segment is labelled with the speaker whose diarization turns cover the most of that segment's time; segments with no speaker activity keep no label.
**Specification:**
  Given A transcript segment from 10.0s to 14.0s, with diarization turns speaker 1 at 10.0-11.5 (1.5s overlap) and speaker 2 at 11.0-14.0 (3.0s overlap)
  When  Speaker labels are assigned
  Then  The segment is labelled 'speaker_2' (largest overlapping duration wins); a segment overlapping no diarization turn keeps speaker None
**Parameters:** Overlap weight = min(seg.end, de) - max(seg.start, ds), counted only when > 0 (diar.py:206-208); label format f'speaker_{n}' from the library's 1-based generic speaker integer (diar.py:32,210); ties resolve to whichever speaker the counter saw first; the library runs the 'v3-offline' preset with gpu=0/Metal (diar.py:121-132)
**Edge cases handled:** speaker numbers are file-local and do not identify a person across files; assignment mutates the segments in place and returns the same list
**Confidence:** High

### RULE-014: Effective chunk length cap is the smaller of the configured max and the engine's declared limit
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/base.py:163-171`
**Plain English:** You cannot ask an engine to transcribe a longer piece of audio than it accepts: the chunk ceiling is whichever is smaller, your configured chunk_max_s or the engine's own limit.
**Specification:**
  Given config.chunk_max_s = 120.0 and the DashScope engine declares max_chunk_s = 300.0
  When  the pipeline asks how long a chunk may be for the resolved engine
  Then  the effective cap is 120.0s; for an engine declaring 300.0 with chunk_max_s = 600.0 the cap is 300.0s; for an engine declaring no limit (offline, bcut, openrouter) the cap is the configured 120.0s (bcut.py:49, offline.py:75, openrouter.py:42)
**Parameters:** config.chunk_max_s default 120.0, chunk_min_s default 30.0, chunk_overlap_s default 0.5 (config.py:109-111); DASHSCOPE_MAX_CHUNK_S = 300.0 seconds (config.py:55, dashscope.py:46); bcut.py:49, offline.py:75, openrouter.py:42 all declare max_chunk_s = None (no known ceiling)
**Edge cases handled:** A None engine limit means 'no known ceiling', so the configured value wins (base.py:169-170); the pipeline independently re-checks every planned chunk against the engine limit and aborts the whole task rather than sending a request the upstream will reject (pipeline.py:262-287; cited for cont…; if the engine limit is below chunk_min_s the pipeline lowers the minimum to match (pipeline.py:269-270)
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: base.py:163-171 chunk_max_for() returns config.chunk_max_s when the engine spec's max_chunk_s is None, else min(config, engine); pipeline.py:264-270 applies the identical clamp on the engine instance (getattr(engine,'max_chunk_s',None)) plus chunk_min = min(config.chunk_min_s, chunk_max).…

### RULE-015: Bcut upload splits the audio into server-sized pieces and chains their ETags
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/bcut.py:138-184`
**Plain English:** The tool asks the service how big each upload piece may be, cuts the file into pieces of exactly that size, uploads them in order and submits the concatenated ETags to complete the upload.
**Specification:**
  Given a 5,000,000-byte mp3 and a server-issued per_size of 1,000,000 with 5 upload URLs
  When  the upload step runs
  Then  piece i is payload[i*per_size : (i+1)*per_size] and is PUT to upload_urls[i] with the shared headers; piece 0 is bytes 0–999,999 and piece 4 is bytes 4,000,000–4,999,999; the ETags are joined with ',' and sent to /resource/create/complete along with InBossKey, ResourceId and UploadId
**Parameters:** Upload model_id '8' (bcut.py:37, 61); query model_id 7 (bcut.py:38, 201); declared ResourceFileType 'mp3', type 2, name 'audio.mp3' (bcut.py:142-148); missing upload_urls or per_size raises a fatal error echoing the first 200 chars of the response (bcut.py:151-155)
**Edge cases handled:** a zero-length ETag header is accepted as an empty string (bcut.py:166); a piece-upload network failure is classified recoverable (retried); an HTTP >= 400 piece upload goes through the 412/banned path first (bcut.py:164-165); a response without download_url after completion is fatal (bcut.py:179-183)
**Confidence:** Medium — Citation was corrected by referee (The cited path does not exist as written. 'legacy/transcript/projects/engines/bcut.py' is not in the tree — the only bcut.py under legacy/transcript/ is '/Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/engines/bcut.py' (252 lines; byte-identical to '/Users/jasper/Documents/Transcript/src/transcript/engines/bcut.py'). The rule's text is correc…

### RULE-016: Bcut utterances become segments: milliseconds to seconds, empty ones dropped, text concatenated without separator
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/bcut.py:238-252`
**Plain English:** Each subtitle utterance from the free engine becomes one segment at sentence granularity, with times converted from milliseconds and blank utterances discarded.
**Specification:**
  Given utterances [{transcript: '你好', start_time: 1200, end_time: 3400}, {transcript: '  ', start_time: 3400, end_time: 4000}, {transcript: '世界', start_time: 4000, end_time: 6000}]
  When  the bcut response is converted to a result
  Then  two segments are produced: 1.2s–3.4s '你好' and 4.0s–6.0s '世界'; the result text is '你好世界' (raw concatenation, no separator), language defaults to 'zh', audio_seconds is the last segment's end (6.0), cost is 0.0 because the interface is free, and has_timestamps is True
**Parameters:** millisecond divisor 1000.0 (bcut.py:247-248); missing start_time/end_time default to 0 via 'or 0' (bcut.py:247-248); default language 'zh' (bcut.py:129); cost_usd 0.0 (bcut.py:131)
**Edge cases handled:** whitespace-only transcripts are skipped (bcut.py:242-244); an empty utterance list is a fatal error rather than an empty transcript (bcut.py:124-125); audio_seconds comes from the transcript timeline, not from a usage field; if every utterance's text is blank, the empty-result fatal fires
**Confidence:** High

### RULE-017: DashScope word-level timestamps are converted from milliseconds and the text is recovered through a fallback chain
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/dashscope.py:155-188`
**Plain English:** DashScope returns character-level timings in milliseconds; the tool converts them to seconds and picks the transcript text from the first place it can find it.
**Specification:**
  Given a response whose inner output has sentence.words [{text: '你', begin_time: 1500, end_time: 1700}, {text: '  ', ...}] and text '你好'
  When  the response is parsed
  Then  one word is emitted: '你' at 1.5s–1.7s with probability None (blank word texts are skipped); the result text is '你好'; if the text field were absent the tool would join the sentence texts, and failing that the word texts
**Parameters:** millisecond divisor 1000.0 (dashscope.py:177-178); blank word texts skipped (dashscope.py:171-173); probability always None for this engine (dashscope.py:179); the response is read from the nested output.output first, falling back to the outer mirror, to tolerate version differences (dashscope.py:162-164); a single sentence object is wrapped into a list (dashscope.py:165-166)
**Edge cases handled:** a response with no usable text at all is a fatal error echoing 200 chars of the payload (dashscope.py:113-114); segments are only built when the caller asked for timestamps; the txt path returns an empty segment list (dashscope.py:118); audio_seconds comes from usage.duration, and cost is deliberately left unknown (dashscope.py:116-124); has_timestamps reflects whether segments were actually produced, not what the engine declared (dashscope.py:126)
**Confidence:** High

### RULE-018: Offline transcription takes its text from the local ASR model and its timeline from a separate alignment model
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/offline.py:84-120`
**Plain English:** Offline mode runs two models: one produces the good text, the other produces the timings, and the tool aligns them; the timeline model is only paid for when the task needs timestamps.
**Specification:**
  Given an offline srt task on a 60s chunk (want_timestamps True) and a Qwen pass returning text with punctuation
  When  the offline engine transcribes the chunk
  Then  the Qwen model supplies the text and the reported language (taken from the first element if the model returns a list of languages, otherwise the string itself), the whisper alternates model supplies word timings, and the two are aligned into segments; for a txt task the whisper pass is skipped entirely and the result reports has_timestamps False
**Parameters:** offline model default mlx-community/Qwen3-ASR-1.7B-8bit, timing model default mlx-community/whisper-large-v3-turbo (config.py:30-31); cost 0.0 and audio_seconds None for this engine (offline.py:116-117); hotwords are forwarded to the ASR model when present (offline.py:89); the caller decides whether timestamps are needed: srt artifact or speaker separation (pipeline.py:469)
**Edge cases handled:** want_timestamps defaults to False in this engine, unlike the online engines; an empty transcript produces no segments at all; the alignment module maps the punctuation-free timing skeleton onto the punctuated text by character similarity, interpolating unmatched characters and then breaking by punctuation with a hard per-se…; if alignment produces no segments the engine makes a second identical call and re-aligns (see the dedicated rule)
**Confidence:** High

### RULE-019: Cost attribution differs per engine: local and anonymous are free, the paid srt engine reports its own cost, DashScope'…
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/openrouter.py:112-113`
**Plain English:** Only one engine tells the tool what the call cost; the local engine and the free anonymous engine report zero, and the token-priced engine deliberately reports nothing rather than guessing.
**Specification:**
  Given four engines transcribing the same audio
  When  each returns its result
  Then  the OpenRouter result carries the exact usage.cost from the response; the offline result reports cost_usd = 0.0; the bcut result reports cost_usd = 0.0 because the interface is free; the DashScope result reports cost_usd = None with the comment that the per-second price varies by account and promotion
**Parameters:** openrouter.py:113 (cost_usd from usage.cost), offline.py:117 (0.0), bcut.py:131 (0.0), dashscope.py:124 (None); the calling layer keeps a separate estimate for OpenRouter of about $0.1 per hour of audio, which is applied only to OpenRouter and to auto-routed srt tasks (pipeline.py:97-106)
**Edge cases handled:** a None cost means 'unknown', not 'free', in every downstream total; the calling layer's hourly estimate and the engine's reported cost are separate numbers that can disagree; the estimated rate is a hardcoded constant in the calling layer, not derived from the engine registry's cost note; DashScope's registry cost note is a token price (input ¥0.8/M, output ¥2.7/M) which the engine never converts into a per-task cost; bcut's true cost — uploading the audio to a third-party store — is not expressible as a monetary field at all
**Confidence:** High

### RULE-020: OpenRouter returns sentence-level segments and the authoritative cost of the call
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/engines/openrouter.py:94-116`
**Plain English:** The srt engine reports both segment timings and the dollar cost of the call, which the tool records; the transcript text is taken from the response or rebuilt from the segments.
**Specification:**
  Given verbose_json segments [{start: 0.0, end: 3.2, text: '第一句'}, {start: 3.2, end: 4.0, text: '  '}] and usage {seconds: 4.0, cost: 0.000111}
  When  the response is parsed
  Then  one segment is kept (0.0s–3.2s '第一句'; the blank one is dropped), text falls back to joining the kept segments when the top-level text is empty, audio_seconds = 4.0, cost_usd = 0.000111, language comes from the response payload, and has_timestamps is True
**Parameters:** response_format 'verbose_json' (openrouter.py:58); a zero or missing cost stays None rather than 0 (openrouter.py:113); timestamps and cost guide the global cost-accounting decision below (openrouter.py:112-113)
**Edge cases handled:** text and segments can disagree, in which case the top-level text wins; a missing usage block leaves both audio_seconds and cost_usd as None; the request always declares the multipart content type audio/mpeg regardless of the real container (openrouter.py:75); a non-JSON 200 response is fatal (openrouter.py:89-92)
**Confidence:** High

### RULE-021: Hot-word list composition and caps
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/glossary.py:150-158`
**Plain English:** Bare glossary lines and both spellings of each correction pair are handed to the engine as hot words and to the summarizer as writing hints, de-duplicated in order and capped in size.
**Specification:**
  Given Glossary with bare words '小新', '集成' and a rule '艾麦' -> '集诚'
  When  The hot-word list is built for an engine call or for the summary prompt
  Then  The list is ['小新', '集成', '集诚', '艾麦'] (bare words first, then each rule's correct spelling then its wrong spelling, duplicates dropped); for summarization each word is cut to 40 characters and the list to 80 words
**Parameters:** Order: bare hot words, then right, then wrong, per rule (glossary.py:155); dedupe preserves first occurrence (glossary.py:156-157); optional limit parameter truncates from the front (glossary.py:158); summary caps MAX_HOT_WORDS = 80 and MAX_HOT_WORD_CHARS = 40 (summary.py:24-25,47); the transcript-fallback hot-word path passes the same list to the engine (pipeline.py:432,464-469)
**Edge cases handled:** a word longer than 40 characters is silently truncated when used for summarization, which can turn it into the wrong term; an empty or missing glossary file yields an empty list and no hot words are passed
**Confidence:** High

### RULE-022: Glossary replacement order and change counting
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/glossary.py:161-175`
**Plain English:** Post-transcription replacements are applied deterministically, longest wrong spelling first, and every replacement is counted so the user can see exactly what was changed.
**Specification:**
  Given Rules '集成' -> '集诚' and '成' -> '诚', text '我们把集成做完了'
  When  apply_rules runs over the merged text
  Then  '集成' is replaced first (2 characters before 1), giving '我们把集诚做完了'; '成' then finds no occurrence so no further change; changes = [Integration→集诚 x1]
**Parameters:** Sort key = len(rule.wrong) descending (glossary.py:170); replacement is plain str.replace, so all occurrences in one pass (glossary.py:172-174); only surviving occurrences are recorded (glossary.py:171); count is the number of occurrences replaced (glossary.py:174)
**Edge cases handled:** rules are also applied separately to each merged segment for the SRT (pipeline.py:358-361) while the reported counts come only from the whole-text pass, so per-segment totals need not equal the repor…; a rule whose wrong form is a substring of another wrong form is protected only by the longest-first ordering; rules are never applied twice to the same text
**Confidence:** High

### RULE-023: Cost is summed across chunks, but audio seconds are never aggregated
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/merge.py:122-144`
**Plain English:** Per-chunk reported costs are added up (a reported $0.00 stays $0.00), while the 'audio seconds' each engine reports is deliberately discarded because each engine counts it differently.
**Specification:**
  Given Four chunks reporting costs 0.02, 0.02, None, 0.02 USD
  When  merge_results combines chunk results
  Then  cost_usd = 0.06 (only reported values summed; if no chunk reported a cost the total is None); audio_seconds = None; engine = 'dashscope' (distinct engine names joined with '+'); has_timestamps = True if any chunk had timestamps
**Parameters:** ONLINE_PRICE_PER_HOUR = 0.1 USD/hour (pipeline.py:37) is the reference price used elsewhere; None costs are excluded (merge.py:131); Bcut's 0.0 is kept as a genuine zero (merge.py:140-141)
**Edge cases handled:** a result list of only None entries yields cost_usd=None rather than 0; true task duration comes from ffprobe on the source file, not from summed chunk usage
**Confidence:** High

### RULE-024: Overlap detection between consecutive chunks (dedup judgement)
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/merge.py:13-67`
**Plain English:** Two chunks of transcript are considered to repeat each other only when the earlier chunk's ending and the later chunk's beginning match, and almost all of the matched region really lines up character for character.
**Specification:**
  Given Previous chunk tail '…我们今天讨论第一段。' and next chunk head '第一段。接下来…' (tail/head window = last/first 240 characters)
  When  The merger looks for the duplicated boundary text
  Then  The exact suffix/prefix match 'k' characters long is returned (searched from the longest possible down to 4 characters); if no exact match exists, a fuzzy match is accepted only if it starts within 1 character of the new chunk's start, ends within 4 characters of the previous tail, has gaps of at most 1 character between matched blocks, and >= 80% of the covered head region matches; otherwise 0
**Parameters:** window = 240 chars (merge.py:21); _MIN_OVERLAP_CHARS = 4; _TAIL_TOLERANCE = 3; _HEAD_TOLERANCE = 1; _GAP_TOLERANCE = 1; _MIN_COVERAGE = 0.8 (merge.py:14-18)
**Edge cases handled:** '第一段。' vs '第二段。' shares only '第' (coverage 0.75) and is correctly rejected — the deliberate counter-example for over-eager dedup; either side empty returns 0 immediately; matched blocks after a gap larger than 1 character are discarded, which is what enforces anchoring
**Suspected defect:** The docstring says the fuzzy match requires 'at least 70%' coverage (merge.py:27) but the constant is 0.8 (80%) (merge.py:18). Code and comment disagree; the code is the stricter of the two.
**Confidence:** High

### RULE-025: SRT timestamp format and rounding
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/models.py:100-110`
**Plain English:** Seconds are converted to the HH:MM:SS,mmm form SRT requires, with negative times clamped to zero and millisecond carry handled, so a rounded-up second becomes the next second instead of ':1000'.
**Specification:**
  Given A segment boundary at 59.9996 seconds
  When  The SRT timestamp is rendered
  Then  Milliseconds round to 1000, carrying +1 second, giving 00:01:00,000 (never 00:00:59,1000); a negative input renders as 00:00:00,000
**Parameters:** Separator defaults to ',' (SRT) but is a parameter (models.py:100); hours/minutes/seconds zero-padded to 2 digits, milliseconds to 3 (models.py:110)
**Edge cases handled:** fractional seconds are rounded with Python's round(), which is round-half-to-even rather than strict half-up — an exact .5 millisecond value (e.g. an underlying value that computes to exactly 0.5ms)…; the carry branch only fires when the rounded millisecond count is exactly 1000
**Suspected defect:** The comment says '四舍五入进位' (round half up) but Python's round() is round-half-to-even, so an exact half-millisecond can round down.
**Confidence:** Medium — Should sub-millisecond halves always round up (half-up) rather than Python's half-to-even? For subtitle timing a systematic half-to-even tie-break is unusual; confirm the intended rounding rule.

### RULE-026: Cost pre-estimate per engine and artifact
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/pipeline.py:92-106`
**Plain English:** The tool only quotes a price when it has a measured unit price: offline and Bcut are free, OpenRouter is quoted at about $0.10 per hour of audio, and DashScope is left as 'unknown' rather than guessed.
**Specification:**
  Given A 45-minute audio file (2700s), mode online, artifact srt, online_engine auto
  When  The cost estimate is requested before running
  Then  Estimate = round(0.1 * 2700 / 3600, 6) = $0.075 (because auto + srt routes to OpenRouter); with artifact txt and engine auto the answer is None (DashScope pricing is account-dependent); with mode offline or engine bcut the answer is 0.0
**Parameters:** ONLINE_PRICE_PER_HOUR = 0.1 USD (pipeline.py:37); auto routes txt->dashscope and srt->openrouter (pipeline.py:103-104); rounding to 6 decimals (pipeline.py:105); DashScope token pricing is stated separately as input ¥0.8/M, output ¥2.7/M in the engine registry, not used here
**Edge cases handled:** an explicitly specified dashscope engine returns None even for srt; the estimate never blocks a run — it is display-only
**Confidence:** High

### RULE-027: Summary input batching and compression loop
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/summary.py:219-251`
**Plain English:** Long transcripts are summarized batch by batch and the resulting notes are re-summarized until they fit in a single model call; if a round of summarization does not actually shrink the material, the summary fails instead of silently truncating the tail.
**Specification:**
  Given A transcript of 60,000 characters with MAX_BATCH_CHARS = 24,000
  When  summarize_stream runs
  Then  The text is split into 3 batches; each is summarized to a JSON note, the notes are joined with newlines, and re-batched; the loop repeats while more than one batch remains; if the combined notes are >= the combined input length of that round, the call raises 'material cannot be compressed to summary length' rather than dropping text
**Parameters:** MAX_BATCH_CHARS = 24,000 (summary.py:21); REQUEST_TIMEOUT_S = 180.0 (summary.py:26); PARTIAL_THROTTLE_S = 0.15 for streaming callbacks (summary.py:27); max_tokens = 8000, temperature = 0.2, response_format json_object (summary.py:75-81); non-streaming final call when no partial callback is supplied (summary.py:239-247)
**Edge cases handled:** empty or whitespace-only transcript raises 'transcript is empty'; the final call is streaming only when the caller supplied a partial callback, and an empty streamed body is treated as a format error
**Confidence:** High

### RULE-028: Speech activity gating: drop micro-spans and bridge short pauses
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/vad.py:31-61`
**Plain English:** The voice-activity detector's output is cleaned: spans shorter than a quarter second are discarded and pauses shorter than 0.4s are treated as part of the same speech, so sentence-level pauses do not become chunk boundaries.
**Specification:**
  Given Raw VAD timestamps in sample counts at 16000 Hz including a 0.1s blip and two speech spans separated by a 0.3s pause
  When  speech_spans processes the detector output
  Then  The 0.1s blip is dropped; the two spans 0.3s apart are merged into one span from the earlier start to the later end; the result is sorted by start time
**Parameters:** min_speech_s = 0.25s (drop threshold), max_gap_s = 0.4s (merge threshold) (vad.py:35-36); sample rate defaults to 16000 if the model does not report one (vad.py:44); spurious results <= max_gap_s even when overlapping are merged via max(last_end, end) (vad.py:57-58)
**Edge cases handled:** empty detector output yields an empty span list, which the planner then treats as continuous speech; spans are treated as closed intervals; a gap exactly equal to 0.4s still merges
**Confidence:** High

### RULE-029: 任务进度百分比由已完成分片数推算
**Category:** Calculation
**Priority:** P1
**Source:** `src/transcript/web/jobs.py:92-104`
**Plain English:** 进度不是「跑到第几片」，而是「已完成几片 ÷ 总片数」；在线分片乱序完成，所以必须数库里状态为 done 的行，否则进度会倒退或跳变。
**Specification:**
  Given 一个任务共 10 片，其中第 1、2、5、7 片已 done（当前完成的是第 5 片）
  When  引擎回报一次 stage=chunk 的进度事件
  Then  事件里 current=4，任务表 progress 更新为 40.0，并把该分片的最新内容一并推给页面
**Parameters:** progress = 已完成分片数 / 总片数 × 100；仅当 total > 0 时写库；完成数取 store.done_chunk_indices() 的行数
**Edge cases handled:** chunk_index 与 chunk/chunk_failed 两个 stage 同时成立时才附上分片详情; 并行完成顺序与分片下标无关，所以下标不能当完成数
**Confidence:** High

### RULE-030: Streaming summary shows title/overview/key points as soon as each field closes
**Category:** Calculation
**Priority:** P2
**Source:** `frontend/src/lib/summary-stream.ts:80-91`
**Plain English:** While the model is still writing its JSON answer, the page extracts whatever of title, overview, key points and action items has already arrived so the user sees progress.
**Specification:**
  Given buffer = '{"title":"周会","overview":"讨论预算\\u4f1a","key_points":["成本",""]'
  When  parsePartialSummary runs on the buffer
  Then  title='周会' with titleComplete=true; overview='讨论预算会' with overviewComplete=false (unterminated string); keyPoints=['成本'] because the blank item is dropped; actionItems=[] because "action_items" has not appeared yet
**Parameters:** surfaced fields: title, overview, key_points, action_items (snake_case in wire, camelCase in UI); escapes: \n→newline, \t→tab, \r→dropped, \uXXXX decoded only when the next 4 chars are hex, any other \x → literal x; every returned string is trimmed
**Edge cases handled:** Field lookup is raw indexOf on the whole buffer, not a JSON parse: a value already received that contains the literal text "title" can hijack a later lookup; First occurrence wins and array scanning stops at the first non-string token, so duplicate/nested keys are misread; A trailing backslash or a partial \uXXXX yields the string so far with complete=false; hasPartialContent (summary-stream.ts:93-97) is the display gate: false only when all four fields are empty
**Suspected defect:** findStringField/findArrayField (summary-stream.ts:46-78) search the raw stream with indexOf, so transcript-derived text containing a quoted field name can redirect what the progress view shows — worth a targeted test.
**Confidence:** High

### RULE-031: Model list filtering and display cap of 60
**Category:** Calculation
**Priority:** P2
**Source:** `frontend/src/task.tsx:384-394`
**Plain English:** The model picker filters the fetched model catalogue by case-insensitive substring on either the model id or the display name, and never shows more than 60 entries at once.
**Specification:**
  Given a catalogue of 200 models, 80 of which contain 'gpt' in the id or name
  When  the user types 'GPT' in the model field
  Then  80 models match and the first 60 are listed; the header shows '60 / 200 个模型'; an empty query shows the first 60 of all models.
**Parameters:** Cap 60 (magic number, task.tsx:393); match = id.toLowerCase().includes(query) || name.toLowerCase().includes(query); query trimmed and lowercased
**Edge cases handled:** A free-text model id that is not in the catalogue is still submittable.; The selected id is highlighted through highlight state which clamps to the filtered list length (task.tsx:408-411).
**Suspected defect:** The 60-entry cap is applied before the count is displayed, so the user can be told '60 / 200' while their match sits at position 61 and is unreachable by scrolling.
**Confidence:** High

### RULE-032: Progress percentage: from SSE current/total, clamped at the card
**Category:** Calculation
**Priority:** P2
**Source:** `frontend/src/task.tsx:948-951`
**Plain English:** Overall progress is computed as finished work over total work, clamped to 0-100, and the denominator is never smaller than the number of chunks the page already knows about.
**Specification:**
  Given task.progress = 104.6 and 12 chunks, with 9 chunks marked done
  When  the progress card renders
  Then  shown percent = 100, total = max(streamTotal, 12), done count = 9 and the counter reads '9 / 12 个音频片段'.
**Parameters:** pct = min(100, max(0, round(t.progress))); total = Math.max(totalOverride, chunks.length); progress bar driven by transform: scaleX(pct/100) with a 200 ms transition; negative progress clamps to 0
**Edge cases handled:** total = 0 switches the caption to '正在分析音频…'.; The console page computes its own percentage inline as round(current/total*100) and applies no clamp (main.tsx:249).; The server pushes progress % on each progress event (task.tsx:1083).
**Confidence:** High

### RULE-033: Small corner radii are derived from a single radius token
**Category:** Calculation
**Priority:** P2
**Source:** `frontend/tailwind.config.js:88-92`
**Plain English:** Only one corner-radius value is configured; the medium and small steps are computed by subtracting fixed pixel amounts from it.
**Specification:**
  Given --radius = 8px
  When  a rounded-md or rounded-sm element is rendered
  Then  rounded-md = calc(8px - 2px) = 6px and rounded-sm = calc(8px - 4px) = 4px; rounded-lg = var(--radius) = 8px
**Parameters:** lg = var(--radius); md = calc(var(--radius) - 2px); sm = calc(var(--radius) - 4px). Subtracted amounts: 2px and 4px, hardcoded. Base radius defined in src/index.css (outside this file set).
**Edge cases handled:** No lower bound or clamp: if --radius is set below 4px, border-radius sm becomes zero or negative, which browsers clamp to 0 or reject.; The 2px/4px steps are fixed while the base radius is a variable, so the scale is not proportional — shrinking the base radius compresses the steps toward equality.
**Confidence:** High

### RULE-034: 模型清单里的每百万 token 单价
**Category:** Calculation
**Priority:** P2
**Source:** `src/transcript/web/app.py:552-570`
**Plain English:** 把上游返回的「每 token 输入价」换算成「每百万 token 价格」给设置页显示，换算不了就显示空值。
**Specification:**
  Given OpenRouter 返回某个模型 pricing.prompt = "0.0000005"
  When  调用 GET /api/summary-models
  Then  price_per_million_prompt = 0.5；若 pricing 缺失或不是数字，该字段为 null
**Parameters:** price_per_million_prompt = float(pricing["prompt"]) × 1,000,000；取不到时 null；返回字段还有 id、name（缺省用 id）、context_length、reasoning（supported_parameters 含 'reasoning'）
**Edge cases handled:** pricing 里没有 prompt 或值为非数字 → null，不报错; items 不是列表、或条目不是字典、或缺 id 时整条跳过; 清单结果按 id 升序排列
**Confidence:** Medium — pricing.prompt 的币种与口径是否恒为「USD / 每 token 输入」？非数值/缺字段时应该显示「未知」还是显示 0？

## Validation

### RULE-035: Saved preference is only accepted as an exact, known value
**Category:** Validation
**Priority:** P1
**Source:** `frontend/public/theme.js:7-14`
**Plain English:** The stored theme value is honoured only if it is exactly the string 'light' or 'dark'; anything else is treated as no preference at all.
**Specification:**
  Given localStorage['transcript-theme'] holds 'Light', 'auto', '', or any other value that is not exactly 'light' or 'dark'
  When  readPreference() is called at load, on DOMContentLoaded, or on a storage event
  Then  the read returns null, the stored value is discarded, and resolution falls back to the OS preference / dark default
**Parameters:** Accepted literals: exactly 'light' or 'dark' (line 10); storageKey = 'transcript-theme' (line 3)
**Edge cases handled:** Case-sensitive: 'Light' is rejected; A stored value is never repaired or normalized in place — the bad value stays in localStorage until the user next clicks the toggle
**Confidence:** High

### RULE-036: A row offers Stop while it is running and Delete only when it is not
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/components/history-sidebar.tsx:153-168`
**Plain English:** The action offered on a history row is determined solely by whether the task currently has a live process: a running task can be stopped, and any other task can only be deleted — interrupted, failed and completed tasks get no resume action from the sidebar.
**Specification:**
  Given A task row rendered by the history island
  When  The row renders its action control
  Then  t.running = true renders a Stop button calling POST /api/tasks/{id}/cancel; t.running = false renders the two-step Delete button
**Parameters:** Eligibility flag = task.running only (not cancelling, not is_terminal). Stop action = cancelTask(id) -> POST /api/tasks/{id}/cancel (lib/api.ts:38-40). Resume exists in the API client (lib/api.ts:42-44) but is never wired to this sidebar.
**Edge cases handled:** A task in the cancelling state normally still has running = true, so the Stop button remains clickable and repeated cancels are possible; is_terminal is not consulted here even though the polling loop uses it; An interrupted task (running = false, status = running) shows Delete only, so it cannot be resumed from the sidebar; Delete/Stop controls are hidden behind hover styling on lg screens (opacity-0 until group hover/focus-within), a presentation detail
**Confidence:** High

### RULE-037: The component layer performs no validation; all field rules are the caller's
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/components/ui/input.tsx:6-21`
**Plain English:** The shared input controls declare no required, length or format rules of their own - they forward every native HTML attribute untouched - so every check on what the user typed lives in the calling form, not in this design system.
**Specification:**
  Given A transcript name field rendered as a bare <Input /> with no extra props, and a user submitting it empty
  When  The form is submitted
  Then  The component itself performs no check and shows no error state; whether an empty name is rejected is decided entirely by the caller (browser-native `required` only fires if the caller passed it)
**Parameters:** input.tsx forwards `...props` straight onto <input>, with only `type` destructured and re-supplied (no default, so absent type means the browser's "text"). textarea.tsx:8-20 and the Select trigger (select.tsx:13-31) do the same for their primitives. No `required`, `pattern`, `minLength`, `maxLength`, `min`, `max`, `step` or `inputMode` defaults exist anywhere in these files, and there is no aria-invalid / error-border variant in the cva definitions.
**Edge cases handled:** type="number" is passed through with no numeric keyboard hint and no min/max; an empty or whitespace-only value is indistinguishable from a valid one at this layer; because no error styling variant exists, invalid-field presentation must be built by callers using raw classes (which then fights twMerge override order); Label (label.tsx:9-17) renders a plain <label> with no htmlFor/aria wiring of its own, so field-to-label association is also the caller's responsibility
**Suspected defect:** No aria-invalid or error-state styling variant exists in the design system, so every caller inventing its own invalid styling is the only supported path - a likely source of inconsistent validation feedback after the rewrite.
**Confidence:** Medium — Where do the actual field rules live (which fields are required, maximum lengths, allowed characters, numeric ranges, file type/size for uploads), and are any of them currently enforced only by browser-native attributes rather than application code? Also: are there input types (number, email, password) whose native browser validation must be preserved?

### RULE-038: One error contract for every API call
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/lib/api.ts:12-19`
**Plain English:** Any failed API call becomes a thrown error carrying the server's own message, with a generic Chinese fallback when the server said nothing.
**Specification:**
  Given GET /api/tasks/7/summary returns HTTP 404 with body {"error":"任务不存在"}
  When  the client parses the response
  Then  Error('任务不存在') is thrown; if the body is non-JSON or empty the thrown message is 请求失败（404）; any 2xx returns the parsed body unchanged
**Parameters:** fallback template 请求失败（{status}） (api.ts:15); unparseable body degrades silently to {} (api.ts:13) rather than raising a parse error
**Edge cases handled:** fetchOutput (api.ts:56-60) is the exception: on success it returns raw text, and only calls the JSON parser to raise the server error when !res.ok — a non-JSON txt/srt body must not go through parse; cancel/resume/delete/reveal all funnel their failures through this same thrown Error; output kind is restricted to 'txt' / 'srt' by the type signature (api.ts:56)
**Confidence:** High

### RULE-039: Agent summary settings: accepted fields, key retention, prompt fallback
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/lib/api.ts:66-80`
**Plain English:** Saving the model settings applies model, base URL, prompt and hot words, keeps the API key unless a new one is typed, and always answers with the full refreshed settings.
**Specification:**
  Given the user edits 模型设置 and saves with model/base_url/prompt/hot_words and no api_key
  When  saveSummarySettings PUTs /api/summary-settings
  Then  model, base URL, prompt and hot words are applied, the existing key is kept, the cached model list is cleared, and the response is the fresh SummarySettingsPayload
**Parameters:** request keys model, base_url, api_key?, prompt, hot_words (api.ts:66-72); response shape types.ts:108-125; custom_prompt = prompt is non-blank, so blanking the prompt silently restores the built-in default prompt (src/transcript/web/app.py:385-387); the response only ever exposes api_key_configured / api_key_masked
**Edge cases handled:** hot_words is a flat list of correct spellings; saving rewrites only that block of the glossary file and preserves existing 错词 -> 正确词 rules and comments; API key is omitted rather than blanked when the user did not change it (see the secret-retention rule)
**Confidence:** High

### RULE-040: Saving secrets: a blank field keeps the stored secret and a masked preview is never written back
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/lib/api.ts:94-105`
**Plain English:** Submitting the credential form with an untouched (blank) key field keeps the existing key, only an explicit clear list wipes one, and the displayed mask can never overwrite a real secret.
**Specification:**
  Given the OpenRouter key is already stored; the form shows the masked placeholder and the user presses save without typing anything
  When  POST /api/credentials {keys:{openrouter_api_key:""}} (or PUT /api/summary-settings with api_key omitted/empty) runs
  Then  the stored key is unchanged; only entries in clear [] blank a credential; the response returns credentials, key_fields and online_engines for re-rendering
**Parameters:** mask status text 已配置（尾号 XXXX） and input placeholder = 8 bullets + last 4 chars (src/transcript/config.py:58-73); value ≤512 chars and must contain no whitespace, control chars or '=' (src/transcript/web/app.py:717-718); keys/clear validated against the server's allowed attr set before anything is written (src/transcript/web/app.py:707-710); summary-settings writes the key only when non-empty (src/transcript/web/app.py:514)
**Edge cases handled:** The whole request is rejected (400) if any attr is unknown, and nothing is persisted; Masked preview is a visual placeholder only — only the last 4 characters are ever echoed back
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful. The cited client (frontend/src/lib/api.ts:94-105) is a thin POST wrapper, but the behavior it encodes is real on the server: app.py:713-716 skips empty 'keys' values ("留空 = 保持现状"), app.py:720-721 maps only 'clear' entries to "", app.py:726-731 mirrors the same skip into the live Config, an…

### RULE-041: Engine is selectable only when ready; missing credentials are named
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/main.tsx:20-25`
**Plain English:** In online mode the engine dropdown lists every engine, but an engine whose credentials are not configured cannot be chosen, and its label names exactly which keys are missing.
**Specification:**
  Given an engine {id:'whisper', label:'Whisper 云端', ready:false, needs_key:['api_key','org_id']}
  When  the engine dropdown renders
  Then  the option is rendered disabled with label 'Whisper 云端（缺 API_KEY、ORG_ID）'; a ready engine renders enabled with no suffix.
**Parameters:** disabled = !e.ready; suffix '（缺 ' + needs_key.map(toUpperCase).join('、') + '）'; values come from the status payload's online_engines
**Edge cases handled:** The dropdown is populated through a portal into the static <select id="onlineEngine">, so a non-ready engine can still be the value already selected by defaults (main.tsx:122-123).; The whole engine field is hidden unless mode is online (main.tsx:130-138).
**Confidence:** High

### RULE-042: Audio source is required and an attached file beats a typed path
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/main.tsx:203-219`
**Plain English:** A transcription job can only be submitted with an audio source: either a dropped/selected file or a typed local file path. If both are given the file wins; if neither is given the request is still sent with no source field and the server is left to reject it.
**Specification:**
  Given the new-transcription form with file input #file and path input #sourcePath
  When  the user submits the form
  Then  if a file is attached, multipart field 'file' is sent; otherwise if the trimmed path is non-empty, field 'source_path' is sent; otherwise neither is sent. No client-side error message is produced for the empty case.
**Parameters:** Field names 'file' / 'source_path'; path trimmed before sending; the form always also carries mode, artifact, language, online_engine
**Edge cases handled:** File attached AND path typed -> the file only; the path is ignored.; Whitespace-only path counts as empty (trim).; A rejected empty submission surfaces only through the progress message '失败：…' from the SSE result event (main.tsx:258).
**Suspected defect:** No client-side guard: an accidental submit with no source round-trips to the server before failing.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: legacy/transcript/frontend/src/main.tsx:203-219 does exactly what the card says — reads #file and #sourcePath, always appends mode/artifact('srt', hardcoded line 206)/language/online_engine, then appends 'file' when fileInput.files?.[0] exists (line 215-216), else 'source_path' from the tr…

### RULE-043: Credential save/clear payload: empty input still saves an empty key
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/main.tsx:42-55`
**Plain English:** Saving a key sends whatever is currently in the box (possibly an empty string); clearing is a separate explicit action available only once a value is configured, and both report success or the server error inline.
**Specification:**
  Given a key field 'api_key' shown as 已配置 AKIA**** with an empty input box
  When  the user clicks 保存 (not 清除)
  Then  the request body is {"keys":{"api_key":""}} — an empty value is sent rather than a no-op; clicking 清除 instead sends {"clear":["api_key"]}. On success the input box is emptied and the message reads '已保存' / '已清除'; on failure the server message is shown.
**Parameters:** Payload shapes {keys:{attr:value}} and {clear:[attr]}; value defaults to '' when the box is untouched; the clear button is only rendered when f.configured; success clears the local input
**Edge cases handled:** There is no client-side non-empty check, so an accidental 保存 on an empty box may overwrite or blank a stored credential depending on the server.; Only the three status slices returned by the endpoint (credentials, key_fields, online_engines) are merged back into page state (main.tsx:286-287).
**Suspected defect:** Saving with an empty box is allowed and sends an empty key value, which can destroy a working credential; a non-empty guard or an explicit 'no change' is expected.
**Confidence:** High

### RULE-044: Saved output files are only read for a finished, non-running task
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/task.tsx:157-170`
**Plain English:** The finished SRT/TXT exports are downloaded only when the task is not running, its status is done, and the corresponding file exists; otherwise the panels fall back to live data or an empty state.
**Specification:**
  Given a task with status 'running', running=true, srt_exists=true
  When  the subtitle panel effect runs
  Then  no /output/file request is made, fileLines is cleared, and the panel shows live chunk lines; once the task reaches done with srt_exists=true the SRT is fetched.
**Parameters:** Guard: task.running || task.status !== 'done' || !task.srt_exists (SRT, task.tsx:160) and task.running || task.status !== 'done' || !task.txt_exists (TXT, task.tsx:258); endpoint GET /api/tasks/{id}/output/file?kind=srt|txt
**Edge cases handled:** Reading failures are surfaced as text in the panel footer, not as a blocking error.; Switching tasks re-runs the effect (task.id is in the dependency list) and the previous read is discarded via the active flag.; The copy-to-clipboard text is built from the SRT parsed to plain text under the same guard (task.tsx:1050-1062).
**Confidence:** High

### RULE-045: Model list cannot be fetched while the connection settings have unsaved edits
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/task.tsx:343-361`
**Plain English:** The picker refuses to query a model catalogue against unsaved connection settings: the user must save the Base URL / API key first, or type the model id by hand.
**Specification:**
  Given saved base_url = 'https://api.example.com/v1', the input box contains 'https://api.example.com/v1/' and the API key box is empty
  When  the user opens the model dropdown or clicks 刷新
  Then  the request is blocked and the message reads '连接设置有未保存的修改。请先保存，再获取该服务的模型列表；也可直接手填模型 ID。' With apiKey non-empty, or any other URL difference, the same block applies.
**Parameters:** connectionDirty = baseUrl.trim().replace(/\/+$/,'') !== settings.base_url || !!apiKey.trim(); the comparison strips trailing slashes only from the typed value; cache-busting refresh adds ?refresh=1
**Edge cases handled:** Before settings have loaded (settings null) the comparison is against undefined, so the state is dirty.; On any error the model list is emptied and the error text is shown in place of the list.; Editing Base URL or API key clears the previously fetched catalogue (task.tsx:484, 502).
**Suspected defect:** Only the typed URL has trailing slashes stripped, not the saved one; if the server stored a trailing slash the form reports 'unsaved changes' forever and the model list can never be fetched.
**Confidence:** Medium — Does the server normalise the stored Base URL (strip trailing slashes) on save? If not, the dirty check must normalise both sides.

### RULE-046: Hot words: separators, 40-character truncation, exact-match dedupe, 80-word cap
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/task.tsx:420-433`
**Plain English:** Hot words (domain terms fed to the summariser) are entered comma/space separated; each entry is trimmed, cut to a maximum length, ignored if it duplicates an existing word, and the list stops growing at a maximum count.
**Specification:**
  Given existing hot words ['小新'] and the user types '小新, 蜡笔小新x' plus 45 more characters
  When  the user presses Enter, types a Chinese comma/顿号, or leaves the field (blur)
  Then  '小新' is skipped as a duplicate, the long entry is stored truncated to its first 40 characters, and once the list holds 80 words any further entry is silently dropped; the draft box is emptied.
**Parameters:** Separator regex /[,，、\s]+/; max words = settings.max_hot_words (client fallback 80); per-word char cap = settings.max_hot_word_chars (client fallback 40); input maxLength = cap + 2 (task.tsx:630); Backspace on an empty draft removes the last word (task.tsx:625-627)
**Edge cases handled:** A paste of several separators yields an empty parts array and the call returns without clearing anything.; Truncation happens before the duplicate check, so two long words sharing their first 40 characters count as duplicates.; The words are saved as a list on the settings form; removing a word is a chip X or the Backspace rule above.
**Suspected defect:** The fallbacks (80 / 40) are duplicated in three places (commitHotWords defaults, input maxLength, tooltip text), so a server-side change to either limit can leave the UI enforcing a stale value.
**Confidence:** High

### RULE-047: Summary settings can only be saved with a non-empty model and Base URL
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/task.tsx:641`
**Plain English:** The settings form refuses to save until both a model id and a Base URL are present, and every field is length-capped before it reaches the server.
**Specification:**
  Given the settings form with model = '   ' and the Base URL filled in
  When  the user inspects or clicks the save button
  Then  the button stays disabled; with model and Base URL both non-blank the button is enabled unless a save is in flight. Saving sends model, base_url, api_key, prompt and hot_words; on success the API key box is cleared, the cached model list is discarded and the list is closed.
**Parameters:** Disabled when saving || loading || !model.trim() || !baseUrl.trim(); maxLength Base URL 500 (task.tsx:485), API key 512 (task.tsx:503), model id 200 (task.tsx:517), prompt = settings.max_prompt_chars (task.tsx:592); Base URL and model id are HTML-required
**Edge cases handled:** An empty API key field means 'keep the existing key' — the placeholder says replacing requires pasting a new one (task.tsx:506).; '恢复默认值' only fills the boxes; nothing is persisted until 保存 is clicked.
**Confidence:** High

### RULE-048: Summary cannot be started until a working model connection exists
**Category:** Validation
**Priority:** P1
**Source:** `frontend/src/task.tsx:753-755`
**Plain English:** If the summariser reports itself unavailable (no usable model connection), the panel offers to open settings instead of a start button.
**Specification:**
  Given a task whose summary payload has available=false, status='disabled'
  When  the 总结 tab renders
  Then  the text '先配置模型连接，再开启总结。' plus a 去设置 button is shown and no enable action is offered; when available=true and status is disabled the 开启自动总结 button is shown instead.
**Parameters:** unavailable = summary && !summary.available; status falls back to 'disabled' when no summary payload exists; the enable action is POST /api/tasks/{id}/summary
**Edge cases handled:** While the summary payload is still null the panel shows the default (start) state rather than the unavailable state.; The '去设置' button switches the tab to the settings tab, it does not open a dialog.
**Confidence:** Medium — What exactly makes the server report summary.available=false — a missing API key, a missing Base URL, or both? The UI only mirrors the flag.

### RULE-049: Working-copy audio contract and its verification
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/audio.py:162-178`
**Plain English:** Every engine receives a re-encoded working copy whose codec, sample rate and channel count are checked after ffmpeg runs, so 'ffmpeg did not error' is never accepted as proof that the file is correct.
**Specification:**
  Given A successful wav normalization, expected pcm_s16le / 16000 Hz / 1 channel
  When  verify is called on the produced file
  Then  Pass silently if all three match; otherwise raise 'file does not match the wav16k contract' listing each mismatch (e.g. 'channels=2!=1'); an empty or missing output file also raises
**Parameters:** wav16k = -ac 1 -ar 16000 -c:a pcm_s16le (audio.py:23); mp3_64k = -ac 1 -ar 16000 -c:a libmp3lame -b:a 64k (audio.py:24); expected pairs wav16k=(pcm_s16le,16000,1) and mp3_64k=(mp3,16000,1) (audio.py:165); online runs use the mp3 copy, offline the wav copy (pipeline.py:248-258)
**Edge cases handled:** only the first audio stream is mapped (-map 0:a:0) and video is dropped (-vn); an unknown kind raises rather than skipping verification; the original file is never modified; all artefacts live in a temp workdir removed at the end
**Confidence:** High

### RULE-050: Input file eligibility check
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/audio.py:44-91`
**Plain English:** A file is only accepted when it exists, is non-empty, contains an audio stream and has a determinable non-zero duration; containers with video only, or with no readable duration, are rejected up front.
**Specification:**
  Given A .mp4 file with only a video stream
  When  The file is probed before the run starts
  Then  The task fails with 'no audio track' (InputError, non-retryable) and no engine is called and no money is spent; an empty file fails with 'file is empty', a missing file with 'file does not exist', a zero/unknown duration with 'duration could not be determined'
**Parameters:** Duration is the max of format-level and stream-level 'duration'/'Duration' values (audio.py:73-77); size_bytes from stat, megabytes = bytes / 1_000_000 (models.py:96-97); has_audio = an ffprobe stream with codec_type 'audio' exists (audio.py:71,87)
**Edge cases handled:** a probe failure returns a failed RunResult (task_id may be 0) instead of raising to the caller (pipeline.py:187-191); unparsable ffprobe JSON is treated as a failed probe; missing ffmpeg/ffprobe binaries are reported before any work happens (audio.py:38-41)
**Confidence:** High

### RULE-051: Credential value sanitization on save
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/config.py:213-246`
**Plain English:** Saving a key refuses any value containing whitespace or '=', writes the change atomically with owner-only permissions, preserves every other line and comment, and treats an empty value as clearing that setting.
**Specification:**
  Given An update of DASHSCOPE_API_KEY to a value containing a space, in a file that also has a hand-written comment and an ONline_engine override
  When  save_credentials writes the file
  Then  The write is refused with '<NAME> may not contain whitespace or an equals sign'; with a clean value only that key's line is replaced (or appended if absent), all other lines and comments are preserved, the file ends with exactly one newline, and the replacement lands atomically via a 0600 temp file
**Parameters:** Rejected characters: any whitespace or '=' (config.py:230-231); key match is on the text before the first '=' of a non-comment line (config.py:232-238); the temp file is chmod 600 before os.replace (config.py:242-245); the target directory is created if missing (config.py:225); an empty string or None clears the entry's value (config.py:229,240)
**Edge cases handled:** a value is never logged, stored in SQLite or written into artefacts — this function prints nothing and returns only the path; lines without '=' and comment lines are skipped when searching for the key; clearing a value leaves the line as 'KEY=' rather than deleting the line
**Confidence:** High

### RULE-052: A task only starts if the credentials the chosen engine actually needs are present
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/base.py:155-160`
**Plain English:** The system refuses to start an online task when the credential its engine needs is missing, instead of failing later mid-request.
**Specification:**
  Given artifact = 'srt', mode = 'online', engine resolves to openrouter, and openrouter_api_key is empty
  When  the user starts the task
  Then  the required-key set is ('openrouter_api_key',), the missing key is reported as an HTTP 400 listing the environment variable name, and no request is made; with the key present the set is satisfied and the task proceeds
**Parameters:** Required keys per engine: dashscope → ('dashscope_api_key',), openrouter → ('openrouter_api_key',), offline and bcut → () (base.py:76-104); the check compares against config attributes and treats empty string as missing (web/app.py:294-307, cli-visible via engine_catalog)
**Edge cases handled:** offline mode requires no keys at all; bcut requires no keys (anonymous public interface); a per-task override changes which key set is required, because resolution runs first; the engine-level guard repeats the check at request time (dashscope.py:62-65, openrouter.py:53-56)
**Confidence:** High

### RULE-053: Online capability is 'ready' when at least one online engine needs no credentials
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/base.py:206-210`
**Plain English:** The 'can we go online at all' light turns on if any one online engine is usable without keys — in practice the free anonymous one.
**Specification:**
  Given no API keys configured at all, but the bcut engine requires no credentials
  When  the UI asks whether online mode is available
  Then  online_ready returns True, because bcut has an empty required-key tuple; the per-engine catalog rows separately show each keyed engine as not ready (base.py:190-202)
**Parameters:** Any engine with all required_keys satisfied counts; an empty required_keys tuple is trivially satisfied (base.py:208-210)
**Edge cases handled:** removing bcut from the spec table would flip this to 'not ready' with no keys configured; the aggregate 'ready' flag for the synthetic 'auto' row is stricter: it needs every key of every online engine (base.py:187)
**Confidence:** Medium — Citation was corrected by referee (The cited range frontend/src/lib/types.ts:12-36 contains only TypeScript interface declarations (EngineEntry at 12-20; StatusPayload.online_ready/online_engines at 29-36) — no executable logic implements readiness or the chunk cap there. The only runtime code in the range is the __BOOT__ fallback at types.ts:172-186, which hard-codes online_ready:false when no p…

### RULE-054: Bcut rejects anything that is not a non-empty mp3 before opening the network call
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/bcut.py:98-107`
**Plain English:** The free engine declares its upload as mp3, so the tool only sends mp3 files with content and refuses anything else up front.
**Specification:**
  Given an audio path ending in '.wav'
  When  the chunk is submitted to the bcut engine
  Then  a fatal error is raised saying the interface declares mp3 and the online path must use a 64k mp3 working copy; for a file ending '.MP3' with non-zero bytes the upload proceeds; for a zero-byte mp3 a fatal 'empty audio' error is raised
**Parameters:** Suffix comparison is case-insensitive via .lower() (bcut.py:99); the online path always produces the mp3 working copy before chunking (pipeline.py:254-257, cited for context)
**Edge cases handled:** a file with no suffix reports '(无后缀)' in the message; emptiness is judged by the in-memory payload, not by file size on disk (bcut.py:105-107)
**Confidence:** High

### RULE-055: DashScope upstream error codes are mapped to actionable fatal errors before generic classification
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/dashscope.py:129-146`
**Plain English:** Two known DashScope failures are recognised by their error code or message text and reported with a specific remedy; anything else falls through to the generic retry/reject classifier.
**Specification:**
  Given an HTTP 400 whose body contains code AUDIO_DURATION_TOO_LONG (or that literal text)
  When  the non-200 response is classified
  Then  a fatal error is raised naming the engine's chunk ceiling and quoting the upstream body; a body naming UNSUPPORTED_FORMAT or 'format is empty' raises a fatal error explaining that parameters.format is required and suggesting the probe command; any other status goes to the shared classifier, where 408/409/425/429 or >= 500 become retryable and the rest become fatal upstream errors
**Parameters:** body preview truncated to 600 chars for the code scan, 200 chars in the message (dashscope.py:130, 139-144); recovery mapping lives in errors.classify_http: statuses 408/409/425/429 and >= 500 are retryable (errors.py:48-52)
**Edge cases handled:** a non-JSON error body yields code = None and relies on substring matching; the retryable/fatal decision directly controls whether the chunk is retried, because only retryable errors enter the backoff loop; the format-empty branch exists because a caller that rebuilds the request body by hand can drop the format field
**Confidence:** High

### RULE-056: DashScope container whitelist decides the declared audio format and rejects unknown containers
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/dashscope.py:66-73`
**Plain English:** The DashScope request must declare the audio container explicitly, so only a fixed set of known extensions is accepted and everything else is refused locally.
**Specification:**
  Given a chunk file named 'chunk_0003.wav'
  When  the DashScope request is assembled
  Then  audio_format = 'wav' and the request carries parameters.format = 'wav'; for '.m4a'/'.aac'/'.flac'/'.mp3' the mapped format is used; for '.ogg' or no suffix a fatal error is raised telling the user to normalise with ffmpeg (the pipeline does this automatically)
**Parameters:** Mapping {'.mp3': mp3, '.wav': wav, '.m4a': m4a, '.aac': aac, '.flac': flac} (dashscope.py:29); suffix is lowercased before lookup (dashscope.py:67); omitting parameters.format makes the upstream reply UNSUPPORTED_FORMAT 'format is empty' (dashscope.py:32-33, 91-98)
**Edge cases handled:** uppercase extensions are accepted via .lower(); the audio is embedded as a base64 data URL, so no pre-upload to object storage is needed (dashscope.py:149-152)
**Confidence:** High

### RULE-057: DashScope blocks a chunk longer than its 300s ceiling locally instead of spending a paid call
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/dashscope.py:75-82`
**Plain English:** Before sending audio to the paid engine, the tool measures it and refuses locally if it exceeds the model's single-call ceiling, since the upstream would only reject it and still cost time.
**Specification:**
  Given a chunk of 330.5s and the engine cap of 300.0s
  When  the chunk is submitted to DashScope
  Then  a fatal error is raised quoting the measured duration and the 300s ceiling and suggesting the user lower CHUNK_MAX_S; a chunk of 300.4s passes (the tolerance is 0.5s) and the request is sent
**Parameters:** tolerance 0.5s added to the cap in the comparison (dashscope.py:78); DASHSCOPE_MAX_CHUNK_S = 300.0 (config.py:55); the upstream code quoted in the message is AUDIO_DURATION_TOO_LONG, measured at 330s (dashscope.py:32, 11-12)
**Edge cases handled:** the check is skipped entirely when max_chunk_s is None, which happens if a caller constructs the engine without a cap (dashscope.py:46, 76); the duration is obtained by probing the file, so a probe failure surfaces before the request; the same condition is still handled if it reaches the upstream, for defence in depth (dashscope.py:136-140)
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (The Given/When/Then is faithful to dashscope.py:75-82: 330.5 > 300.5 raises FatalError quoting duration (330.5s via :.1f) and the cap (300s via :.0f) and naming CHUNK_MAX_S; 300.4 > 300.5 is false so the request proceeds to the POST at line 104. (Minor: the message also cites upstream code AUDIO_DUR…

### RULE-058: Upload-size rejections from the srt engine are recognised by message text and reported as fatal with the file size
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/engines/openrouter.py:80-87`
**Plain English:** The srt engine enforces a size limit rather than a duration limit, so the tool detects the oversize wording in the error body and tells the user to shorten or shrink the audio instead of retrying.
**Specification:**
  Given an HTTP 413 whose body contains 'does not support large audio inputs'
  When  the non-200 response is classified
  Then  a fatal error is raised reporting the chunk's size in MB and advising a shorter chunk or lower bitrate, quoting the first 200 chars of the upstream body; a 500 or 429 with the same body shape is retried only if it reaches the shared classifier, so the oversize branch takes precedence for those statuses too
**Parameters:** recognised hints: 'does not support large audio inputs', 'request body of', 'exceeds the maximum allowed size' (openrouter.py:22-26); measured limits in comments: request body 50MiB, model-side audio ≈15.4MB accepted / 18.4MB rejected (openrouter.py:7-8, 40-42); the engine deliberately declares max_chunk_s = None because the limit is bytes, not seconds (openrouter.py:40-42); size reported as bytes / 1e6 (openrouter.py:84)
**Edge cases handled:** the body is lowercased before hint matching, so case differences in the upstream message do not matter; 'request body of' is a deliberately loose hint that could match unrelated wording; a non-JSON error body still reaches this branch because it is text-matched first; the byte limit is not enforced locally, so an oversize chunk always costs one round trip
**Confidence:** High

### RULE-059: HTTP failure classification: retryable or fatal
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/errors.py:40-52`
**Plain English:** An upstream HTTP failure is judged retryable only for rate limits, request timeouts/conflicts and server errors; anything else (bad parameters, auth, quota) is surfaced immediately rather than retried.
**Specification:**
  Given An upstream response with status 429 and body containing \"code\":\"Throttling\"
  When  The engine classifies the failure
  Then  A RecoverableError is raised with message 'upstream temporarily unavailable (HTTP 429 Throttling)' and the retry policy may run again; a 400 or 401 raises the fatal UpstreamError 'upstream rejected the request (HTTP 400 ...)' which is never retried
**Parameters:** Retryable statuses: 408, 409, 425, 429, and any status >= 500 (errors.py:48); everything else is fatal (errors.py:50-52); the upstream error code is extracted from the raw body by looking for '"code":"' or '"code": "' (errors.py:43-46); error messages must not contain credentials (errors.py:31-37, config.py:1-7)
**Edge cases handled:** a body that is not JSON still yields a usable message, only without the upstream code; the classification is used by the dashscope, openrouter and bcut adapters alike; non-HTTP transport failures are mapped to their own retryable paths by the callers
**Confidence:** High

### RULE-060: Glossary file grammar and entry validation
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/glossary.py:49-140`
**Plain English:** Each glossary line is either a bare hot word (accepted, no replacement) or a 'wrong -> right' pair; malformed or contradictory pairs are reported with their line number instead of silently doing nothing.
**Specification:**
  Given Glossary lines: '小新' / '艾麦 -> 集诚' / '-> 集诚' / '集诚 = 集诚' / '艾麦 -> 集成' / '艾麦 => 艾麦科技  # 公司简称'
  When  The glossary is parsed (and validated before saving)
  Then  '小新' is a legal bare hot word; '艾麦 -> 集诚' becomes a rule; '-> 集诚' and '集诚 = 集诚' are reported as issues ('both sides required' / 'wrong and right must differ'); the second '艾麦' line is reported as already defined on the earlier line and the first definition wins; the '# 公司简称' tail is stripped only because the '#' follows whitespace
**Parameters:** Separators tried in order: '->', '=>', '→', '=', tab, '|' — first match wins (glossary.py:21,67); '#' starts an inline comment only at line start or preceded by whitespace (glossary.py:54-56); blank and '#'-leading lines are skipped (glossary.py:64-65); duplicate wrong spellings keep the first occurrence (glossary.py:117-125,135-140); a missing file yields no rules and no error (glossary.py:143-147)
**Edge cases handled:** a bare hot word containing '/' or '=' is misparsed as a rule pair because the separator search runs before the hot-word test; an embedded '#' not preceded by whitespace stays part of the term; empty left or right side after stripping is rejected at validation time
**Confidence:** High

### RULE-061: An srt task is refused when the engine cannot supply timestamps
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/pipeline.py:347-352`
**Plain English:** A subtitle request fails outright if the merged result carries no timestamps, instead of writing an untimed or empty subtitle file.
**Specification:**
  Given artifact = srt and a merged result whose has_timestamps is False
  When  The pipeline is about to write products
  Then  The task is marked failed with 'engine X provides no timestamps, cannot produce srt' and neither txt nor srt is written; with artifact = txt the same engine is allowed to proceed
**Parameters:** has_timestamps of the merge is True if any chunk reported timestamps (merge.py:143); the timestamp requirement is also passed down as want_timestamps = (artifact == 'srt' or enable_diar) so extra timing work is only requested when needed (pipeline.py:440,469)
**Edge cases handled:** both .txt and .srt are always written on success regardless of the requested artifact (pipeline.py:363-366), so a txt run still produces an .srt file; for a txt run with an engine that has no timestamps, the empty srt is written silently
**Suspected defect:** artifact only gates the timestamp requirement and the engine's timing work; both .txt and .srt are always written (pipeline.py:365-366). An engine without timestamps on a txt task therefore leaves an empty .srt next to the transcript.
**Confidence:** Medium — When artifact is 'txt' the code still writes a .srt file — an empty one for engines without timestamps. Is the txt task supposed to emit an empty .srt, or should .srt be written only for srt tasks?

### RULE-062: SRT refuses inverted timestamps and numbers only surviving lines
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/render.py:28-48`
**Plain English:** A subtitle file is never written with a segment that ends before it starts, and subtitle numbering counts only the lines actually emitted, so skipping an empty line cannot leave a gap in the numbering.
**Specification:**
  Given Segments [empty text, (start 12.0, end 20.0), (start 30.0, end 29.0)]
  When  The SRT body is rendered
  Then  The empty segment is skipped, the second becomes entry 1, and the inverted third raises ValueError causing the task to fail with no SRT written (rather than emitting a corrupt file); if nothing survives, an empty string is returned
**Parameters:** Numbering starts at 1 and is assigned after filtering (render.py:40-44); glossary change notes are emitted first as '# <line>' comment blocks (render.py:42-43); comment lines are dropped when there are no bodies (render.py:46-48)
**Edge cases handled:** a segment with end == start is accepted (only strictly inverted times raise); text is stripped before writing; the block separator is a blank line
**Confidence:** High

### RULE-063: 提交任务前的输入校验（模式 / 产物 / 在线引擎 / 源文件）
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/app.py:256-292`
**Plain English:** 建任务前必须确认模式只有 offline/online、产物只有 txt/srt、在线引擎在允许清单内，且音频文件必须真实存在并且能被读取出时长；任何一条不满足就 400 拒绝，不创建任务。
**Specification:**
  Given 浏览器提交 mode=online、artifact=srt、online_engine=auto、source_path=/tmp/a.m4a（3.5MB、时长 3600s）
  When  调用 POST /api/tasks
  Then  校验通过并建任务；若 mode=stream 则返回 400「mode 只能是 offline / online，收到：stream」；若路径不存在则 400「文件不存在：…」；若文件存在但不是可解析音频则 400 带探针错误信息
**Parameters:** mode ∈ {offline, online}；artifact ∈ {txt, srt}；online_engine ∈ ONLINE_ENGINES = auto(默认) | dashscope | openrouter | bcut；language 默认 zh 且不做校验
**Edge cases handled:** 无上传文件且 source_path 为空白 → 400「请提供文件或路径」; source_path 会先 strip() 再 expanduser()，所以 '~/x.m4a' 与 ' /x.m4a ' 都能用; language 是自由字符串，直接透传给引擎，无白名单
**Suspected defect:** store.create_task 落库时状态写 'running'（store.py:171-189），而同一个接口对外返回 status='pending'（app.py:324），DB 与接口首答不一致。
**Confidence:** High

### RULE-064: 上传文件 2GB 上限
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/app.py:265-281`
**Plain English:** 通过网页上传的音频在写入磁盘过程中一边累加字节数，一旦超过 2GB 立即中止并删掉半个文件，防止把磁盘写满。
**Specification:**
  Given 上传一个 2.5GB 的 m4a 文件到 POST /api/tasks
  When  服务端按 1MB 一块读取并写入 uploads 目录
  Then  累计读取到 2*1024**3+1 字节时中断，返回 400「文件超过 2GB 上限」，且已写入的部分文件被 unlink 删除
**Parameters:** MAX_UPLOAD_BYTES = 2 * 1024**3 = 2,147,483,648 字节；读取块 1,048,576 字节；落盘文件名 = uuid4().hex 前 8 位 + '-' + 原文件名（目录部分被 Path(...).name 去掉）；目录 = <state.db 所在目录>/uploads
**Edge cases handled:** 文件正好 2GB 整可以通过（判定是 > 而不是 >=）; 上传的文件名里带路径会被剥掉，只剩最后一段; 走 source_path 直接引用本机文件时不受此上限约束
**Suspected defect:** 同一文件里的 POST /api/upload（app.py:645-656）完全没有大小上限、也不做音频探针、失败时也不清理半成品，且写入同一个 uploads 目录——这是一条绕过 2GB 限制的旁路。
**Confidence:** High

### RULE-065: Base URL 校验：只允许干净的本机/服务地址
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/app.py:457-477`
**Plain English:** 总结服务的 Base URL 必须是 http 或 https、必须有主机名、端口在 1–65535 之间，并且不能内嵌用户名密码、不能带查询参数或锚点，长度不超过 500；存库前会统一去掉结尾斜杠。
**Specification:**
  Given 提交 base_url="https://user:pw@host:99999/api?x=1#frag"
  When  调用 PUT /api/summary-settings
  Then  返回 400「Base URL 必须是无凭据、无查询参数的 HTTP(S) 地址」；换成 "https://openrouter.ai/api/v1/" 则通过并存成 "https://openrouter.ai/api/v1"（去掉结尾斜杠）
**Parameters:** scheme ∈ {http, https}；hostname 非空；port 为空或 1–65535；username / password / query / fragment 必须为空；长度 ≤ 500；含空白直接拒绝；存储前 rstrip('/')；解析用 urlsplit，ValueError 一律视为非法
**Edge cases handled:** 端口超出范围在 urlsplit 解析阶段就抛 ValueError，走同一个失败分支; 本机地址（http://127.0.0.1:8000/v1）合法，允许指向本地兼容服务
**Confidence:** High

### RULE-066: Prompt and hot-word limits
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/app.py:480-504`
**Plain English:** The prompt and the hot-word list are size-limited and their limits are published to the UI so the form can enforce them before saving.
**Specification:**
  Given prompt of 12,001 characters, or a hot-word list of 81 entries, or one hot word containing a space or '='
  When  the settings are saved
  Then  the request is rejected with 400 and nothing is written; valid input is stored and echoed back in the payload
**Parameters:** max_prompt_chars = 12_000, max_hot_words = 80, max_hot_word_chars = 40 (src/transcript/summary.py:22-25, exposed via types.ts:108-125); prompt may not contain \x00; hot words may not contain whitespace or '='; duplicate hot words are dropped keeping the first occurrence; blank entries are skipped; credential value ≤512 chars
**Edge cases handled:** The limits travel to the frontend in the settings payload (max_prompt_chars/max_hot_words/max_hot_word_chars), so the UI is expected to enforce exactly what the server enforces; Values are trimmed before length checks and before storage
**Confidence:** Medium — Citation was corrected by referee (The cited lines 108-125 of frontend/src/lib/types.ts are only the TypeScript interface 'SummarySettingsPayload' — a type declaration with no logic. It declares 'max_prompt_chars: number', 'max_hot_words: number', 'max_hot_word_chars: number' (lines 118, 122, 123), so it confirms only the "limits are published to the UI" half of the rule; it implements none of th…

### RULE-067: 内联到页面的 JSON 必须转义尖括号与行分隔符
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/app.py:73-82`
**Plain English:** 内联进 script 标签的启动状态数据要把尖括号、& 和 U+2028/U+2029 转成 Unicode 转义，杜绝数据里出现 </script> 提前闭合脚本标签。
**Specification:**
  Given 任务标题里含字符串 "</script><script>alert(1)</script>"
  When  打开任务页，启动状态被内联进 HTML 的 window.__BOOT__
  Then  页面源码里出现的是转义后的 u003c/scriptu003e，脚本标签不被提前闭合，数据仍能被前端正确解析还原
**Parameters:** 转义映射：< 转 u003c（统一 JSON 转义形式）、> 转 u003e、& 转 u0026、U+2028 与 U+2029 同样转义；JSON 以 ensure_ascii=False 序列化
**Edge cases handled:** 插入位置优先 </head> 前，找不到 </head> 时插到最前面（构建产物正常一定找得到）; 启动数据固定包含 status、task、tasks 三块，首页的 task 为 null
**Confidence:** High

### RULE-068: 服务启动时的前端产物完整性硬门槛
**Category:** Validation
**Priority:** P1
**Source:** `src/transcript/web/frontend.py:29-50`
**Plain English:** 服务启动前必须确认构建产物完整：manifest 存在且能解析、两个入口都带 isEntry 标记、入口引用的 js/css 文件都真实存在；缺任何一项直接启动失败，并给出可操作的修复命令。
**Specification:**
  Given dist 目录里有 index.html，但 manifest 里引用的 assets/index-abc.js 不存在
  When  启动服务（create_app 调用 validate_dist）
  Then  抛出 RuntimeError「前端产物缺失或不完整（入口 index.html 引用的 assets/index-abc.js 不存在）。修复：在 frontend/ 下执行 npm ci && npm run build（需要 Node ≥ 20）；服务启动不会自动下载依赖。」，服务不启动
**Parameters:** 入口集合 = (index.html, task.html)；manifest 路径 = dist/.vite/manifest.json；每个入口必须 isEntry 为真；引用清单 = entry.file + entry.css + （HTML 里出现 /static/dist/theme.js 时）theme.js
**Edge cases handled:** HTML 不存在时不检查 theme.js（只对存在的入口文件做文本扫描）; 半成品（HTML 在、js 不在）被明确拒绝，避免白屏
**Confidence:** High

### RULE-069: Export actions appear only for artifacts that actually exist
**Category:** Validation
**Priority:** P2
**Source:** `frontend/src/task.tsx:1002-1013`
**Plain English:** Download links are offered only for files the task has actually produced; the subtitle row shows a disabled placeholder instead of a broken link, while the transcript row is simply absent.
**Specification:**
  Given a done task with srt_exists=false and txt_exists=true
  When  the export card renders
  Then  the subtitle area shows the non-clickable text '字幕尚未生成' and the transcript area shows a download link to /api/tasks/{id}/output/file?kind=txt&download=true; the copy button appears only when there is text to copy.
**Parameters:** SRT link when srt_exists; TXT link when txt_exists; also '在访达中显示' only when out_dir is set (task.tsx:1021); copy button only when the computed subtitle text is non-empty
**Edge cases handled:** Parsing the SRT for the copy text can fail silently, leaving the copy button hidden even though the SRT link works.; The reveal action posts a path to the server, so it is unavailable for records without an output directory.
**Confidence:** High

### RULE-070: Summary result normalization and length caps
**Category:** Validation
**Priority:** P2
**Source:** `src/transcript/summary.py:109-137`
**Plain English:** Whatever the summary model returns is trimmed to the house limits and coerced into the expected shape; an over-long answer is truncated rather than failing the whole summary.
**Specification:**
  Given A model response {"title": "", "overview": "关于预算和排期的讨论…", "key_points": [10 items], "action_items": "准备材料"}
  When  The response is parsed
  Then  title falls back to the first 30 characters of the overview; overview is capped at 2000 characters; each list is capped at 8 entries and a bare string is wrapped into a one-item list; the summary is stored as done
**Parameters:** title <= 80 chars, overview <= 2000 chars, key_points and action_items <= 8 each (summary.py:125-133); the declared schema SummaryContent allows max 8 list items with title 1-80 and overview 1-2000 (summary.py:34-39); MAX_REASONING_CHARS = 40,000 (summary.py:23,136)
**Edge cases handled:** a response where both title and overview are empty raises a format error; a non-dict JSON body raises a format error; the system prompt asks for at most 5 points while the parser accepts 8 — the parser is the more permissive of the two
**Suspected defect:** Prompt (summary.py:63-64, '最多5个') and parser/schema (summary.py:37-38,132-133, max 8) disagree on the allowed number of key points and action items.
**Confidence:** High

### RULE-071: Summary output contract handed to the model
**Category:** Validation
**Priority:** P2
**Source:** `src/transcript/summary.py:34-68`
**Plain English:** The summarizer is told exactly which JSON fields to produce, is given the user's own summary instructions plus the glossary terms, and is instructed to treat the transcript as data rather than as commands.
**Specification:**
  Given A configured prompt file and a glossary containing '集诚' and '艾麦'
  When  The system prompt is composed
  Then  The prompt contains the user's instructions (or the default 'Chinese summary, title <= 30 characters, at most 5 key points, only explicitly stated action items'), a JSON output contract for title/overview/key_points/action_items, a statement that the transcript is material to analyse and not instructions, and a term list requiring the correct spellings to be used consistently
**Parameters:** DEFAULT_SUMMARY_PROMPT (summary.py:28-31); fallback when the user prompt is empty (summary.py:51); glossary hint appended only when terms exist (summary.py:53-58); MAX_PROMPT_CHARS = 12,000 declared but not enforced on the prompt text in this path (summary.py:22)
**Edge cases handled:** the user's stored prompt is treated as requirements, explicitly not as a permission change; the term list is built from bare glossary words plus every rule's correct spelling
**Confidence:** High

## Lifecycle

### RULE-072: Task and chunk status lifecycle; no partial products
**Category:** Lifecycle
**Priority:** P0
**Source:** `src/transcript/pipeline.py:316-326`
**Plain English:** A task is only marked done when every chunk succeeded; if even one chunk failed the task is marked failed and neither the text nor the subtitle file is written, so a consumer can never mistake a completed-looking transcript for a whole one.
**Specification:**
  Given A 6-chunk task where chunks 0-4 succeeded and chunk 3 failed
  When  The chunk phase returns
  Then  The task's status is 'failed' with the message listing the failed chunk numbers and how many succeeded, no .txt/.srt is written, the successful chunks stay in the database, and the result status reported to the caller is 'failed'; all chunks successful -> status 'done' with txt/srt/raw paths, character count, duration and cost recorded
**Parameters:** Task is created with status 'running' (store.py:171-189) and updated to running with engine and duration at start (pipeline.py:209-211); terminal statuses are exactly {done, failed} (store.py:71,100-102); an empty result set fails with 'no usable transcription results' (pipeline.py:325-326); a probe failure fails before a task row exists, with task_id 0 (pipeline.py:187-191,661-665)
**Edge cases handled:** the stored character count is the length after stripping non-word characters for comparison, not the raw length (pipeline.py:391); the task row keeps its engine name even on failure, which is what the resume path uses to reuse the same engine; progress is a separate stored column defaulting to 0
**Confidence:** Medium — P0 panel doubts spec fidelity: P0 is justified: this is one of the four hard invariants the module declares in its own docstring (pipeline.py:6) and it is the pipeline's exit contract for the whole product. A truncated-but-complete-looking transcript is a wrong, silently shipped output (data integrity), and the failure branch is also what makes resume-without-repaying work; there is no downstream…

### RULE-073: Theme changes propagate across tabs
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/public/theme.js:84-89`
**Plain English:** When the stored theme changes in another tab — or is cleared entirely — every other open tab re-reads the preference and re-applies the theme.
**Specification:**
  Given Two tabs of the app are open and both use the same localStorage origin
  When  A 'storage' event fires whose key is 'transcript-theme' or whose key is null (storage cleared)
  Then  the tab replaces its in-memory preference with the freshly read value and calls apply(), so all tabs end up on the same theme
**Parameters:** Trigger keys: storageKey === 'transcript-theme', or key === null meaning clear() was called (line 85)
**Edge cases handled:** key === null causes the tab to re-read and get null, dropping it back to the OS preference / dark default; The handler does not consult the transition lock, so a cross-tab update can apply while a local wipe transition is mid-flight
**Confidence:** High

### RULE-074: Chunk-level transcription state
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/lib/types.ts:74-84`
**Plain English:** Each audio chunk has its own status and attempt counter, and only chunks marked done contribute text to the final transcript and to Agent summary.
**Specification:**
  Given a task detail whose chunks each carry status, attempts, error, chars, segments and text
  When  the detail is read or the summary falls back to chunk text
  Then  a chunk counts as done only when status=='done'; only done chunks' text is concatenated; attempts shows how many tries that chunk consumed; error holds the last failure message for a failed chunk
**Parameters:** ChunkItem fields types.ts:74-84; chars is computed server-side as len(text) (src/transcript/store.py:117-131); default retry budget max_attempts=3 with backoff_base 1.0 s (src/transcript/config.py:105-106)
**Edge cases handled:** Chunk text is the summary fallback when the task's txt file is absent (src/transcript/summary.py:341-345); segments carry per-line start/end/text used for subtitle reconstruction
**Confidence:** Medium — When a chunk exhausts its retry budget, does the whole task fail (and stay resumable) or does the task continue with the gap? Which upstream failures count as retryable versus fatal?

### RULE-075: Console submission lifecycle: queue, stream, and terminal outcome
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/main.tsx:243-267`
**Plain English:** After submitting, the console shows a progress bar fed by the task event stream, ends the display at 100% when the result says done, and shows the failure reason otherwise.
**Specification:**
  Given a created task id 412 with the progress panel visible at 0%
  When  the stream sends {type:'progress',current:3,total:4} and later {type:'result',status:'done'}
  Then  the bar moves to 75%, the message shows the event text (or the stage name); on result the stream is closed and the bar is set to 100% with '完成'. If status is anything but done the message reads '失败：{error}' or '失败：未知错误'. A broken stream only changes the text to '进度连接中断，正在重连…'.
**Parameters:** Event types handled: progress / result / close; percent = total ? round(current/total*100) : (bar unchanged); result failure text = '失败：' + (error || '未知错误'); a link to /t/{task_id} is revealed after creation; any previous stream is closed before submitting
**Edge cases handled:** A 'close' event closes the stream without changing the displayed message, so an aborted run can leave the last progress text on screen.; The submit button is re-enabled in a finally block, so a failed request does not lock the form.; The bar's width is set directly as a percentage string here (CSS transition 500 ms), unlike the detail card which drives transform.
**Suspected defect:** On a 'close' event the console keeps showing '已排队，等待启动…' as if work were still pending; nothing marks the run as ended.
**Confidence:** High

### RULE-076: Detail-page event stream connects only while work is live and closes on result
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:1064-1099`
**Plain English:** The live progress connection is opened only for a task that is running or stopping, and it is torn down as soon as the run ends; each event updates the on-screen counter, the chunk list, or triggers a full refresh.
**Specification:**
  Given a task detail with running=true
  When  progress events arrive over /api/tasks/{id}/events
  Then  a 'progress' event sets the last message, raises the known total, and upserts its chunk; an event with stage='plan' forces a full detail re-fetch; a 'result' or 'close' event closes the stream and re-fetches; a broken stream (onerror) also re-fetches. When the task is neither running nor cancelling no stream is opened at all.
**Parameters:** Endpoint SSE /api/tasks/{id}/events; connect guard detail.running || detail.cancelling; total accumulates as max(known total, event total); unparsable events are ignored without closing the stream
**Edge cases handled:** An unparsable event is swallowed so a bad heartbeat cannot blank the subtitles already received.; Setting running=true locally on any progress event keeps the live view alive even if the fetched detail said otherwise.; Cleanup closes the stream whenever the task id or the busy flags change.
**Confidence:** High

### RULE-077: Chunk list merge keyed by chunk index
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:1085-1090`
**Plain English:** Progress events carrying a chunk replace the existing row with the same index and keep the list ordered by index, so repeated events for one audio slice update rather than duplicate it.
**Specification:**
  Given existing chunks [{idx:0},{idx:2}] and a progress event carrying chunk {idx:1}
  When  the event is applied
  Then  the list becomes [0,1,2] sorted ascending; a later event for idx:1 with new text replaces the stored row in place.
**Parameters:** Match on chunk.idx; new chunks appended then sorted ascending by idx; no dedupe on any other field
**Edge cases handled:** A chunk event arriving before the plan refresh inserts a row that the next full detail fetch will also contain — the idx match keeps it from doubling.; Attempt counters and per-chunk errors from the event payload overwrite the stored row.
**Confidence:** High

### RULE-078: Summary lifecycle and 700 ms polling, ending in a task-title refresh
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:718-739`
**Plain English:** The summary moves disabled -> waiting -> running -> done/failed; while it is waiting or running the page re-reads it every 0.7 s, and the moment it completes the page re-fetches the task so the new auto-generated project title replaces the file name.
**Specification:**
  Given a summary in status 'running'
  When  700 ms elapse
  Then  the summary endpoint is polled again; polling continues while status is waiting or running and stops on done/failed/disabled. When a poll returns done, a window-level 'task-title-updated' event is dispatched, which makes the detail page re-fetch the task.
**Parameters:** Poll interval 700 ms; polled statuses ['waiting','running']; on done dispatch new Event('task-title-updated') (task.tsx:722) which triggers fetchTaskDetail (task.tsx:1034-1040); while running the panel shows 流式生成中 / 思考中 / 等待首个片段 (task.tsx:767)
**Edge cases handled:** A poll error only sets an error string; polling is not stopped by an error, it stops by status.; The title event listener is re-registered whenever the task id changes.; Live partial text is derived from the summary payload's partial content, not from a second stream.
**Confidence:** High

### RULE-079: Enable / regenerate / retry summary all use the same enable action
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:741-751`
**Plain English:** Starting a summary for the first time, regenerating a finished one, and retrying a failed one are the same operation: a POST that re-enables the summary and replaces its previous result.
**Specification:**
  Given a summary in status 'failed'
  When  the user clicks 重试总结 (or 重新生成 on a done summary, or 开启自动总结 on a disabled one)
  Then  POST /api/tasks/{id}/summary is issued, the returned payload replaces the local summary, and the button is disabled while the call is in flight. The failure branch also renders the stored summary error, or '总结未完成。' when none is present.
**Parameters:** Single call enableSummary(task.id); in-flight guard = working state; failure text = summary.error || '总结未完成。'
**Edge cases handled:** Regenerating a completed summary discards one that may already have been paid for; there is no confirmation step (contrast the resume confirmation rule).; Errors from the call itself are shown only when the summary payload carries no error of its own (task.tsx:832).
**Suspected defect:** Regenerate is a one-click destructive overwrite of a paid result with no confirmation, unlike resume which requires a second click.
**Confidence:** High

### RULE-080: Resuming an online task costs money and needs an explicit second confirmation
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:913-932`
**Plain English:** Resuming a partially finished online task re-uploads the audio and is billed again, so the first click only arms a confirmation: the user must click again within a few seconds, and is told about the re-upload and the per-usage charge.
**Specification:**
  Given a failed/interrupted task with resumable=true and mode='online'
  When  the user clicks 继续未完成的分段
  Then  the button turns destructive and reads 确认续跑, a warning '在线续跑会重新上传音频并按量计费。' appears, and resumeTask is only called on the second click within 4000 ms; after 4000 ms the button silently reverts. For mode='offline' the first click resumes immediately.
**Parameters:** Confirmation window 4000 ms; the button is only rendered when t.resumable is true (task.tsx:1160); endpoint POST /api/tasks/{id}/resume
**Edge cases handled:** Original (first-run) submission is not gated by any cost confirmation — only resume is (main.tsx:198-237).; If resumable is false the resume block is not rendered at all, only the failure explanation.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/task.tsx:913-932 matches the card exactly. 'const costs = task.mode === 'online'' (915); first click on online sets 'confirming' true (926), swapping variant to 'destructive' and label to 确认续跑 (925, 928) and rendering the wa…

### RULE-081: A running task with no live process is reported as interrupted, not as running
**Category:** Lifecycle
**Priority:** P1
**Source:** `frontend/src/task.tsx:945-951`
**Plain English:** The page treats the live-process flag as the truth: if the stored status says running but there is no live worker and no cancellation in progress, the task is shown as interrupted (and offers resume) rather than pretending transcription is still going.
**Specification:**
  Given a task with status 'running', running=false, cancelling=false
  When  the detail page renders the status dot, the outcome heading and the failed banner
  Then  outcome = '已中断', the status mark is red and the failure panel with 继续未完成的分段 is displayed; with running=true the same record shows '转录中' with a pulsing dot.
**Parameters:** busy = t.running || t.cancelling; failed = t.status==='failed' || (t.status==='running' && !busy); done = t.status==='done'; label map {pending:等待中, running:转录中, done:已完成, failed:失败}; label precedence cancelling > failed > stored status
**Edge cases handled:** status 'done' always wins the label even if a worker flag is stale.; cancelling=true shows '停止中' and suppresses the failure styling.; The same derivation is duplicated for the header block (task.tsx:1111-1113) and re-stated in the sidebar (components/history-sidebar.tsx:29-43).
**Suspected defect:** The identical four-way derivation exists in three places; a change to one leaves the others disagreeing. | Interruption is only inferred on the client from running/cancelling flags; nothing in this file transitions the stored status out of "running", so the bad state persists until the server corrects it.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: task.tsx:945-951 matches the rule text exactly — busy = running//cancelling, failed = status==='failed' // (status==='running' && !busy), outcome precedence cancelling>failed>STATUS_LABEL, red mark via StatusMark (task.tsx:119 bg-destructive on failed, ping only when busy, 113-128), and th…

### RULE-082: Resuming an interrupted task keeps the engine it originally ran on instead of re-resolving 'auto'
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/engines/base.py:147-152`
**Plain English:** When a task is resumed after a crash or stop, the system reuses the engine recorded on the task rather than re-deciding from config, so already-paid chunks are not re-billed on a different engine.
**Specification:**
  Given a stored task row with engine = 'dashscope:qwen-audio-3.1-asr-flash' and the user's config since changed to online_engine = 'openrouter'
  When  the task is resumed
  Then  the engine family 'dashscope' is recovered from the stored name and used for the remaining chunks; the config change does not redirect the run
**Parameters:** Derivation takes the substring before the first ':' and accepts it only if present in the registry (base.py:151-152); callers pass the recovered kind only for online tasks (web/app.py:364-365)
**Edge cases handled:** an empty or missing stored engine name yields None, so the caller falls back to fresh resolution; a stored name whose family is no longer registered yields None (treated as not resumable to that engine); a model override inside the stored name (after ':') is not used by this recovery, only the family
**Confidence:** High

### RULE-083: Retry policy: exponential backoff for recoverable errors only
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/pipeline.py:109-134`
**Plain English:** Each chunk may be retried up to three attempts with doubling waits, but only for errors classified as recoverable — parameter, format and quota errors fail immediately rather than burning three identical attempts.
**Specification:**
  Given max_attempts = 3, backoff_base = 1.0, and a chunk failing with 429 errors on the first two attempts
  When  The chunk is transcribed
  Then  Attempts happen at 0s, then after 1s, then after 2s (delay = 1.0 x 2^(attempt-1)); a third failure ends the chunk as failed with attempts = 3; if the first failure is a FatalError subclass it propagates immediately with attempts = 1
**Parameters:** max_attempts default 3, backoff_base default 1.0 (config.py:105-106); delay formula backoff * 2**(attempt-1) (pipeline.py:129); attempts is clamped to at least 1 (pipeline.py:122); the per-chunk attempt count is stored on the chunk row (pipeline.py:511,534)
**Edge cases handled:** a user cancellation is not an error and is never retried (pipeline.py:493-502); the retry event is surfaced to the UI with the wait in whole seconds; the offline engine holds a model lock, so retries of a corrupt file just repeat the same failure
**Confidence:** High

### RULE-084: Cancellation semantics: stop at a chunk boundary and keep what is done
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/pipeline.py:312-314`
**Plain English:** Stopping a run takes effect before the next chunk starts, keeps every finished chunk, writes no products, and leaves the task in the failed state so it can be resumed.
**Specification:**
  Given A 10-chunk online run where the user stops after 4 chunks
  When  The cancel signal is observed
  Then  No new chunk is started, the 4 completed chunks remain in the database, the task is marked failed with a message stating how many chunks completed, and no txt/srt is written; re-running the task reuses those 4 chunks
**Parameters:** The cancel flag is a threading.Event checked before each chunk (pipeline.py:164,455-461,555-556) and before the retry-able work of a chunk (pipeline.py:459-461); cancellation is translated into a failed task, not a distinct status (pipeline.py:312-314); in-flight chunks are allowed to finish
**Edge cases handled:** a cancellation raised inside the thread pool is re-raised after the pool map unwinds, abandoning the remaining queued chunks; the CLI renders status 'failed' with the error text and exit code 1; a cancelled task is resumable because completed chunks are persisted individually
**Confidence:** High

### RULE-085: Speaker separation is gated and never blocks the transcript
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/pipeline.py:331-345`
**Plain English:** Speaker labelling runs only for offline runs with the feature enabled and segments present, and any failure in it is reported and skipped rather than failing the transcription.
**Specification:**
  Given enable_diar = true, mode = offline, merged segments exist, and the diarization library raises an error
  When  The pipeline reaches the diarization step
  Then  The failure is emitted as 'speaker separation skipped (<reason>)' and the run continues to write the txt/srt unchanged; on success the speaker count is reported as 'detected N speakers'
**Parameters:** Gate: config.enable_diar AND mode == 'offline' AND merged.segments non-empty (pipeline.py:331); all exceptions are swallowed deliberately (pipeline.py:344-345); the library and model come from the local NeMo installation paths (config.py:35-44); the speaker count is the number of distinct non-null labels (pipeline.py:342)
**Edge cases handled:** no speaker separation is attempted for online runs even when enabled; enabling diarization also forces want_timestamps for the engines and adds the missing-segments re-run exception to the resume logic; the offline-only restriction exists because the online engines have no diarization hook in this code
**Confidence:** High

### RULE-086: Resume reuses completed chunks and re-runs only two special cases
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/pipeline.py:428-457`
**Plain English:** A restarted run reuses every chunk already recorded as done without paying for it again, except when the stored text is empty or when timestamps are needed but were never stored.
**Specification:**
  Given A previous run left chunks 0,1,2 with status done; chunk 1 stored an empty text; the run needs timestamps (srt or speaker separation) and chunk 2 stored no segments
  When  The chunk phase plans its work
  Then  Chunk 0 is reused as-is (no engine call); chunks 1 and 2 are pushed back into the pending queue and transcribed again; results are assembled in chunk-index order regardless of completion order
**Parameters:** Reuse set = chunks with status 'done' (store.py:366-372); exceptions: stored text empty, or need_ts (artifact == 'srt' or enable_diar) and no stored segments (pipeline.py:440-442); each chunk is persisted the moment it completes, status 'done' or 'failed' plus attempt count (pipeline.py:504-535); only footer/plumbing rows carry status 'pending' initially (store.py:343-350)
**Edge cases handled:** chunk timing parameters may change between runs; ensure_chunk never overwrites an existing row, so old chunks keep their original start/end and index; a chunk that is not in the plan anymore simply never runs; a reused chunk still counts toward the character total and the merged text
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: every element of the rule is exactly what pipeline.py:428-457 does. Reuse set comes from store.done_chunk_indices (store.py:366-372, status='done'); the reuse branch (pipeline.py:436-449) rebuilds a TranscriptResult from state.text/state.segments with no engine call; the two exceptions are…

### RULE-087: Concurrency policy: serial offline, parallel online
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/pipeline.py:545-557`
**Plain English:** Online chunks are transcribed in parallel up to the configured worker count, while offline chunks run one at a time because the local model is exclusive.
**Specification:**
  Given mode = online, online_concurrency = 4, 9 chunks still pending
  When  The chunk phase dispatches work
  Then  A thread pool of at most 4 workers processes the pending chunks concurrently; with mode = offline, or with only one pending chunk, or with online_concurrency = 1 the chunks run strictly one after another; merged output is ordered by chunk index regardless of finish order
**Parameters:** online_concurrency default 4 (config.py:104); the parallel branch requires mode == 'online' AND online_concurrency > 1 AND more than one pending chunk (pipeline.py:545); each worker uses its own SQLite connection in WAL mode (store.py:157-167)
**Edge cases handled:** the cached-chunk scan happens before dispatching, so a full cache means no engine work at all; worker count is a config value; the engine's own rate limits are not modelled
**Confidence:** High

### RULE-088: Agent summary state machine
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/summary.py:280-366`
**Plain English:** A summary moves disabled -> waiting -> running -> done or failed, streams partial text while running, and any run interrupted by a restart is marked failed so the user can retry.
**Specification:**
  Given a task whose summary status is one of disabled | waiting | running | done | failed
  When  the flow runs
  Then  enable → waiting; job start → running (partial {content, reasoning} streamed meanwhile); successful generation → done with content {title, overview, key_points, action_items, reasoning?}; no text available → failed '转录内容为空，无法总结。'; provider error → failed with the upstream message; unexpected exception → failed '总结未完成，请稍后重试。'
**Parameters:** content keys title/overview/key_points/action_items/reasoning (types.ts:145-151); reasoning is capped at 40_000 chars (src/transcript/summary.py:23); on app restart every row still in running becomes failed '总结被中断，请重试。' (src/transcript/store.py:284-288); text source = the task's txt file if it exists, otherwise the concatenated text of done chunks (src/transcript/summary.py:341-345)
**Edge cases handled:** Re-enabling a summary already in done does not restart it (start_if_enabled skips status=='done'); The stored model is preferred over the current setting when displaying an old summary (payload falls back to the configured model when the row has none)
**Suspected defect:** The summary endpoint comment says each task is explicitly authorized 'independent of transcription status', but auto-start requires task.status == 'done' (src/transcript/summary.py:322) — a task stopped mid-run is written as failed, so it never auto-summarizes even though it has partial output.
**Confidence:** Medium — Should a task that was stopped or failed mid-transcription be eligible for Agent summary of its partial transcript, or is done the only trigger? / Citation was corrected by referee (The rule as stated (per-task summary state machine disabled/waiting/running/done/failed, gating on transcription success + API key, content payload keys, startup sweep of stale running rows) does NOT live at the cited…

### RULE-089: Task lifecycle flags drive cancel/resume/delete
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/web/app.py:143-175`
**Plain English:** Each task carries computed flags that decide whether the UI may offer stop, resume or delete; a stopped task stays resumable and a finished one never is.
**Specification:**
  Given a task record with status in {pending, running, done, failed} (there is no separate cancelled value — stopping a run writes failed so the task remains resumable)
  When  the task payload is built
  Then  is_terminal = status in {done, failed}; running = a worker holds the task right now; cancelling = a stop was requested but the worker has not stopped; resumable = not running AND status in {pending, running, failed}; txt_exists/srt_exists = a path is recorded AND that file exists; src_exists = the source audio still exists
**Parameters:** terminal set {done, failed} (src/transcript/store.py:71); 409 refusals: stop when not running, resume while running, delete while running (src/transcript/web/app.py:344-354, 358-377); a task left in running after a crash is therefore resumable and is the recovery path
**Edge cases handled:** A done task is never resumable even if its txt/srt file was deleted from disk (resume is gated on status, existence flags are display-only); resumable is false while running, so the UI must not offer resume during a live run; After a successful stop the status is failed and the task appears in the 更早/本周 history buckets under whatever day it was created
**Confidence:** Medium — Citation was corrected by referee (The cited lines frontend/src/lib/types.ts:59-65 are only the TypeScript interface field declarations (is_terminal, running, cancelling, resumable, txt_exists, srt_exists, src_exists) — no logic, no status set, no file-existence checks. The behavior described by the rule is real but implemented in the backend: src/transcript/web/app.py:143-175 is _task_payload, w…

### RULE-090: SSE 进度流：先补历史，再实时推，空闲时心跳
**Category:** Lifecycle
**Priority:** P1
**Source:** `src/transcript/web/jobs.py:172-199`
**Plain English:** 订阅进度时先把该任务已有的历史事件全部补发（刷新页面不丢进度），再推送实时事件；任务已结束或历史里已有收尾事件就直接补一个 close 并断开，空闲 15 秒发一次保活注释。
**Specification:**
  Given 任务 7 正在跑，此前已产生 30 条进度事件，页面刷新后重新订阅 /api/tasks/7/events
  When  建立 SSE 连接
  Then  先收到 30 条历史事件，随后实时收到新事件；收到 close 即结束；15 秒内无事件时收到保活注释行
**Parameters:** 心跳间隔 heartbeat_s = 15.0 秒；事件格式 data: 加 JSON 后空行（ensure_ascii=False）；每任务事件日志上限 MAX_EVENTS_PER_TASK = 500 条（超出丢最旧的）；连接断开时把自己从订阅者列表移除
**Edge cases handled:** 任务已在本次进程里跑完（finished 集合）→ 只补发历史再补一个 close; 历史里已含 close 事件 → 同样立刻收尾; 订阅队列无容量上限，入队不阻塞、不做网络 I/O
**Confidence:** High

### RULE-091: Transition lock is always released, with a hard timeout backstop
**Category:** Lifecycle
**Priority:** P2
**Source:** `frontend/public/theme.js:46-53`
**Plain English:** The theme toggle can never get permanently stuck: the lock is released when the animation reports it finished, and unconditionally after 1.5 seconds no matter what.
**Specification:**
  Given A wipe transition was started and the lock flag has been set
  When  Either transition.finished settles, or 1500 ms elapse without it
  Then  running is reset to false, any pending timer is cleared, and the data-theme-transition attribute is removed from the root element
**Parameters:** Timeout = 1500 ms (line 65); cleanup clears releaseTimer and deletes root.dataset.themeTransition (lines 46-53); release is also called on a startViewTransition throw (line 71)
**Edge cases handled:** release() is idempotent — it may run twice (timer then finished) and clearing an undefined timer is guarded by the '!== undefined' check; If startViewTransition is absent the lock is never taken, so the timeout path is not used either
**Confidence:** High

### RULE-092: Toggle flips to the opposite of the currently applied theme
**Category:** Lifecycle
**Priority:** P2
**Source:** `frontend/public/theme.js:79-82`
**Plain English:** A click on the theme toggle sets the theme to the opposite of whatever is currently on screen, and the toggle button only becomes clickable after the page is parsed.
**Specification:**
  Given The root element currently carries the class 'light'
  When  The user clicks the 'themeToggle' element
  Then  wipeTheme('dark') is requested, i.e. the next theme is derived from the committed DOM class rather than from the stored preference
**Parameters:** Next value derived from root.classList.contains('light') (line 80); handler is attached inside a DOMContentLoaded listener registered with { once: true } (lines 77-82)
**Edge cases handled:** Deriving from the DOM class means that if the DOM class and the stored preference ever diverge (the storage-event handler updates preference then reapplies), the click still targets the visible oppos…; The click listener is bound once and never rebound, so the button element must exist at DOMContentLoaded
**Confidence:** High

### RULE-093: Stop is not applied optimistically; row state changes only on the next poll
**Category:** Lifecycle
**Priority:** P2
**Source:** `frontend/src/components/history-sidebar.tsx:104-111`
**Plain English:** Clicking Stop only sends the cancel request — the row keeps showing its current state until the next poll brings back the server's view; nothing in the UI flips the task to "stopping".
**Specification:**
  Given A running task row
  When  The user clicks Stop
  Then  POST /api/tasks/{id}/cancel is awaited, the local task list is left untouched, and the label/dot only change when a later poll returns cancelling = true (or the task leaves "running")
**Parameters:** No local mutation of the tasks array on success; on failure an alert shows the server error message. Visible change therefore lags by up to the busy poll interval of 2000 ms (see the cadence rule, lines 77-86).
**Edge cases handled:** A cancel that the server accepts but never reflects (task never leaves running) leaves the Stop button visible indefinitely; A cancel error is surfaced by alert but the row is not refreshed or rolled back; Contrast with delete, which does update the local list immediately on success
**Confidence:** Medium — Is it intended that requesting stop never optimistically updates the row (state only arrives via the 2 s poll), or should the row show a pending-stop state immediately after the user clicks Stop?

### RULE-094: Dialogs are always modal with an overlay and an always-present close control
**Category:** Lifecycle
**Priority:** P2
**Source:** `frontend/src/components/ui/dialog.tsx:26-48`
**Plain English:** Every dialog from this layer is modal: it renders into a portal above a full-screen dimming overlay and always carries a close control with an accessible name, and this layer offers no switch to make a dialog persistent or remove that close affordance.
**Specification:**
  Given A confirmation dialog opened from anywhere in the app
  When  It mounts (state becomes open)
  Then  A fixed full-screen overlay at 80% black sits at z-50 with animated fade-in, the content is centred at max-w-lg with a fade/zoom/slide entrance, and a Close control (icon plus screen-reader-only label "Close") is rendered at top-right; on close the reverse animations run
**Parameters:** Overlay: fixed inset-0 z-50 bg-black/80, data-[state=open]:fade-in-0 / data-[state=closed]:fade-out-0. Content: fixed centred via left/top 50% + translate(-50%,-50%), w-full max-w-lg (512px), duration-200, closed-state zoom-out-95 and slide-out offsets [48%] 1/2. Close: absolute right-4 top-4, opacity-70 -> hover:opacity-100, h-4 w-4 icon, sr-only label "Close". DialogContent always renders DialogOverlay itself (dialog.tsx:30-31), so no caller can have content without the backdrop. Escape / outside-click dismissal and any non-dismissible mode come from the Radix Root defaults (dialog.tsx:6) and are not configured here.
**Edge cases handled:** the overlay is rendered unconditionally by DialogContent, so a caller cannot opt out; no variant exists that suppresses the Close control, so a modal that must be answered cannot be built from this layer alone; open/closed state is owned by Radix Root; this file only styles data-[state=...], so no transition side-effect (focus restore, scroll lock) is authored here; max-w-lg is fixed at 512px with no size variants, so wide tables must override it via className
**Suspected defect:** With only fixed animation classes for open/closed showing, the dialog ignores prefers-reduced-motion, unlike Button which explicitly guards it. A dialog cannot be made non-dismissible at this layer, so an irreversible-action confirmation can still be closed with Escape unless the caller intercepts it.
**Confidence:** Medium — May a dialog be dismissed with Escape or a click on the backdrop, and does that answer differ for destructive confirmations (for example deleting a transcript or overwriting an existing file)? If any dialog must be answered explicitly, the rewrite needs a non-dismissible variant this layer does not provide.

## Policy

### RULE-095: Theme preference resolution precedence
**Category:** Policy
**Priority:** P1
**Source:** `frontend/public/theme.js:15-21`
**Plain English:** The active theme is the user's saved preference if one exists, otherwise the operating system's light/dark setting, and if the OS reports no light preference the app defaults to dark.
**Specification:**
  Given A browser with no saved preference under the key 'transcript-theme' and the OS color-scheme media query NOT matching '(prefers-color-scheme: light)'
  When  The script loads or apply() runs
  Then  the root element receives class 'dark' (and loses 'light'), and root.style.colorScheme is set to 'dark'
**Parameters:** storageKey = 'transcript-theme' (line 3); system query = '(prefers-color-scheme: light)' (line 5); fallback default = 'dark' (line 18: system.matches ? 'light' : 'dark'); root element = document.documentElement (line 4)
**Edge cases handled:** A saved preference of 'light' wins over the OS setting even when the OS reports dark; If the OS media query does not match, the ternary yields 'dark' rather than null — the effective default is dark, not system-light; apply() is invoked at load (line 31) and again on DOMContentLoaded (line 78), so the resolution must be idempotent
**Confidence:** High

### RULE-096: Storage unavailability degrades to session-only theming
**Category:** Policy
**Priority:** P1
**Source:** `frontend/public/theme.js:33-37`
**Plain English:** If the browser blocks reading or writing localStorage, the theme toggle still works for the current page but the choice is not remembered across reloads.
**Specification:**
  Given Timers and storage access throw (private mode, storage disabled, quota error)
  When  The user clicks the theme toggle and setTheme() attempts localStorage.setItem
  Then  the click is not blocked or surfaced as an error; the in-memory preference and the applied theme still change, but nothing is persisted
**Parameters:** Read failure path returns null (lines 11-13); write failure path is an empty catch (line 36)
**Edge cases handled:** Read failure and write failure are handled independently — a read failure yields null preference, which then makes the OS setting authoritative until the user toggles
**Confidence:** High

### RULE-097: Live OS theme changes are honoured only without an explicit user preference
**Category:** Policy
**Priority:** P1
**Source:** `frontend/public/theme.js:83`
**Plain English:** Once the user has chosen a theme, the app stops following the operating system; if they never chose, the app follows the OS live.
**Specification:**
  Given A saved preference exists in localStorage (preference is truthy)
  When  The OS color-scheme media query fires its 'change' event
  Then  nothing happens — the saved preference keeps the theme fixed
**Parameters:** Guard is the truthiness of the in-memory `preference` variable, which is null when unset (lines 10, 15); the preference variable is updated by setTheme (line 34) and by the storage handler (line 86)
**Edge cases handled:** A preference of 'light' or 'dark' is truthy and always wins over the OS; Because preference is pre-populated at load (line 15), an OS change arriving before any user interaction is still ignored when a saved value exists
**Confidence:** High

### RULE-098: Permanent delete requires a second click within a 4-second window
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/components/history-sidebar.tsx:46-66`
**Plain English:** Deleting a history entry is permanent, so the delete button must be clicked twice: the first click only arms a confirmation, and if the second click does not come within 4 seconds the button returns to normal.
**Specification:**
  Given A non-running task row in the sidebar
  When  The user clicks the delete (trash) icon
  Then  The button switches to a check-mark confirm state for 4000 ms; a click inside that window issues DELETE /api/tasks/{id} and drops the row from the list, a click after expiry is treated as the first click again
**Parameters:** Confirmation window = 4000 ms (hardcoded). Destructive call = deleteTask(id) -> DELETE /api/tasks/{id} (lib/api.ts:46-48). Local list update = remove the row with the matching id.
**Edge cases handled:** Timer is per-button component state; leaving the page or unmounting clears it, so navigating away disarms the confirmation; Only a timeout disarms the confirmation; there is no pointer-leave or Escape handling; A failed DELETE raises an alert and the row stays in the list (the list is only filtered after the call resolves); The in-file comment states the delete removes the record only and leaves media files untouched (line 45) — that is a backend claim, not verifiable from this file
**Confidence:** Medium — Confirm the delete endpoint only removes the task record and never deletes the source audio/output files — the UI comment asserts this but the frontend cannot verify it.

### RULE-099: Button style contract: pill shape, weight 400, no shadow, and only the primary variant is filled
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/components/ui/button.tsx:7-38`
**Plain English:** Every button is the same full-radius pill at normal weight with no drop shadow, and only the primary (default) variant is a solid fill; destructive and outline actions must stay as thin hairline outlines with red or body-coloured text rather than a solid coloured button.
**Specification:**
  Given A delete/confirm action rendered as <Button variant="destructive">Delete</Button> and a primary submit rendered as <Button>Extract</Button>
  When  Both are rendered
  Then  Delete is a transparent, hairline-bordered red-text pill that tints red only on hover (hover:bg-destructive/10); Extract is the only solid fill (bg-primary with near-black text, hover:bg-ink-hover)
**Parameters:** Shared: rounded-full (pill, 9999px), font-normal (weight 400), no shadow classes, text-sm, whitespace-nowrap, active:scale-[0.97] with duration-150 ease-out, motion-reduce:active:scale-100, disabled:opacity-50 + disabled:pointer-events-none, focus-visible ring-1 ring-ring. Variants: default = bg-primary/text-primary-foreground; destructive = border-hairline bg-transparent text-destructive; outline = border-hairline bg-canvas; secondary = bg-secondary; ghost = text-body hover:bg-canvas-soft; link = text-foreground underline-offset-4. Sizes: default h-9 px-5, sm h-8 px-4 text-[13px], lg h-11 px-8, icon h-9 w-9. Defaults: variant "default", size "default".
**Edge cases handled:** variant omitted -> filled default pill; this is the only filled treatment available; size omitted -> default h-9 px-5 (36px tall); asChild=true -> styles are applied to the child element via Radix Slot instead of a <button>, so no disabled/type semantics come from this file; caller className is merged last by twMerge (frontend/src/lib/utils.ts) and can override any of these tokens; icon size is h-9 w-9 with no icon-specific padding, so px-5 is dropped
**Suspected defect:** The comment on button.tsx:10 states 160ms for the press feedback but the actual class on line 11 is duration-150 (150ms); the comment also claims destructive is outline-only, which matches the code, but the design brief in DESIGN.md:459/464 is a prose claim while the code is authoritative. Also DESIGN.md:344 says mobile touch targets are inflated to 44x44px WCAG minimum, yet sm (h-8 = 32px) and default (h-9 = 36px) sizes carry no mobile override.
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (NOT P0. This is presentation-layer styling (class strings for button variants) in /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/components/ui/button.tsx:9-38. Nothing here moves money, enforces a legal/regulatory duty, guards data integrity, security or safety, or is the central…

### RULE-100: Fallback console state when the boot payload is missing
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/lib/types.ts:172-186`
**Plain English:** If the page was served without the embedded boot data, the console starts from a fixed offline default state instead of failing.
**Specification:**
  Given the page is opened against an old artifact or a test stub where window.__BOOT__ is undefined
  When  the console calls boot()
  Then  it gets online_ready=false, online_engines=[], credentials={}, key_fields=[], defaults={mode:'offline', artifact:'srt', language:'zh', online_engine:'auto'}, stats={}, task=null, and must fetch /api/tasks itself because the sidebar list is absent
**Parameters:** default literal at types.ts:180; sidebar fetch default limit=20 (api.ts:21) while the server default for the same list is 50 — one screen, two different defaults
**Edge cases handled:** tasks on the boot payload is optional; when present it must be used directly so the sidebar is not repainted after a later /api/tasks response
**Confidence:** High

### RULE-101: Console defaults: offline by default, and the credentials deep link forces online
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/main.tsx:104-125`
**Plain English:** The console starts in offline mode as the product default, then applies whatever defaults the server bootstrapped; landing on the credentials deep link switches the form to online so the key panel is reachable.
**Specification:**
  Given a freshly loaded console with boot defaults {mode:'offline', artifact:'srt', language:'zh', online_engine:'auto'}
  When  the page mounts, or the URL hash is '#credentials'
  Then  the offline radio is checked and the hidden artifact input matching the boot default is selected; with the '#credentials' hash the online radio is checked instead, which reveals the engine field and the key panel.
**Parameters:** Fallback defaults when no boot payload exists (lib/types.ts:172-186): mode offline, artifact srt, language zh, online_engine auto; deep-link trigger window.location.hash === '#credentials'
**Edge cases handled:** Any submitted-run form default not present in the DOM is silently ignored (the query returns null).; The static HTML skeleton ships with offline already checked, so the product default holds even if boot data never arrives.
**Confidence:** High

### RULE-102: API keys are paste-only and never rendered back in clear
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/main.tsx:69-80`
**Plain English:** Credential values are write-only from the browser's point of view: key boxes are password inputs, the page only ever shows the server-provided masked preview, and after a successful save the box is emptied.
**Specification:**
  Given a key field reported by the server as configured, masked 'AKIA****'
  When  the key panel or the summary settings render
  Then  the box is type='password' with autoComplete off (and 'new-password' for the summary key), the only echo of the value is the masked string in the badge or beside the label, and after a successful save the local value is cleared.
**Parameters:** Badge text = '已配置 ' + f.masked (main.tsx:71); the summary key label shows settings.api_key_masked (task.tsx:496); input autoComplete 'off' / 'new-password'; the key value is not part of any status slice other than the masked preview
**Edge cases handled:** The clear action is only offered for an already-configured field (main.tsx:84-88).; The typed key is held in component state and is dropped after a successful save; a failed save keeps it for retry.
**Confidence:** High

### RULE-103: Restoring defaults does not touch the API key or the hot words
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/task.tsx:439-446`
**Plain English:** Loading the shipped defaults refills only the model id, Base URL and prompt; the stored key and the user's hot-word list are deliberately left alone, and nothing is persisted until the settings are saved.
**Specification:**
  Given settings with default_model 'gpt-4o-mini', default_base_url 'https://api.example.com/v1', a custom prompt, stored API key, and hot words ['小新']
  When  the user clicks 恢复默认值
  Then  model, Base URL and prompt fields are replaced by the defaults, the key field and the hot-word chips are unchanged, and the message reads '已载入默认值，点击保存后生效。'
**Parameters:** Reset fields: model <- default_model, base_url <- default_base_url, prompt <- default_prompt; untouched: api_key (still 'keep existing' when blank), hot_words
**Edge cases handled:** If the settings payload failed to load, the action does nothing.; Saving after restore writes the default URL and prompt but still keeps the previously stored key.
**Confidence:** High

### RULE-104: Enabling a summary discloses transcript text and key to the configured Base URL
**Category:** Policy
**Priority:** P1
**Source:** `frontend/src/task.tsx:819`
**Plain English:** The product tells the user up front that turning on summarisation sends the transcribed text, the current prompt and the API key to the configured Base URL, and that the audio itself is not uploaded.
**Specification:**
  Given a task with a transcript and a configured summary model/Base URL
  When  the user enables auto-summary
  Then  the pre-start panel has stated: '启用后会把转录文字、当前提示词和 API 密钥发送到配置的 Base URL，不上传音频。'
**Parameters:** Disclosure text at task.tsx:819; the actual outbound payload is built by the backend, which is outside this file set
**Edge cases handled:** The settings page carries the same warning about OpenAI-compatible endpoints receiving the key (task.tsx:491).; Nothing in these two files shows what the backend actually transmits, so the disclosure copy and the implementation can diverge silently.
**Confidence:** Medium — Does the backend summary request send exactly the transcript text, the prompt and the API key — and nothing else (no audio, no file paths, no task titles)? The UI states this but does not enforce or verify it.

### RULE-105: Configuration precedence and legacy settings compatibility
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/config.py:131-201`
**Plain English:** Values in config.env win, the prompt file next to it wins over an old JSON settings file, and the legacy file is only consulted when the new settings are absent or unreadable.
**Specification:**
  Given config.env without SUMMARY_MODEL, a legacy summary-settings.json containing model 'z-ai/glm-5.3-flash' and a prompt, and no summary-prompt.txt
  When  Configuration is loaded
  Then  The legacy model and prompt are adopted; if summary-prompt.txt exists the legacy prompt is ignored; if SUMMARY_MODEL is present in config.env the legacy model is ignored; a legacy file that is unreadable, not an object, or whose model/prompt has the wrong type raises a ValueError instead of loading defaults
**Parameters:** Defaults: DEFAULT_CONFIG_PATH = ~/.config/transcript/config.env, DEFAULT_STATE_DB = ~/Documents/Transcript/state.db, DEFAULT_OUTPUT_DIR = ~/Documents/Transcript/output, glossary = ~/.config/transcript/glossary.txt (config.py:20-22,100-102); truthy parsing for ENABLE_DIAR is '1'/'true'/'yes' case-insensitive (config.py:157); numeric overrides parsed for ONLINE_CONCURRENCY, MAX_ATTEMPTS, BACKOFF_BASE, CHUNK_MIN_S, CHUNK_MAX_S, CHUNK_OVERLAP_S (config.py:189-200); bases have trailing slashes stripped (config.py:147-149); Paths are expanduser'd
**Edge cases handled:** a numeric setting that fails to parse is silently discarded and the default is used with no warning; empty values fall back to defaults via 'values.get(name) or default'; the prompt file is read with UTF-8 encoding when present
**Suspected defect:** Numeric config parsing is wrapped in contextlib.suppress(ValueError) (config.py:197-200), so a typo like CHUNK_MAX_S=12O silently reverts to the default with no diagnostic.
**Confidence:** High

### RULE-106: Credentials are only ever shown masked and never persisted outside the config file
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/config.py:58-73`
**Plain English:** Key values appear nowhere except the owner-only config file: any UI, log or artefact shows only a status plus the last four characters, and an unset key shows as 'not configured'.
**Specification:**
  Given A configured key ending in 'XY9Z' and an unset key
  When  Credential status is rendered for the page or CLI self-check
  Then  The configured key renders as 'configured (last 4: XY9Z)' and the input placeholder as eight dots plus 'XY9Z'; the unset key renders as 'not configured' and an empty placeholder; no plaintext value is ever returned by these functions
**Parameters:** mask() -> 'configured (last 4: xxxx)' / 'not configured' (config.py:58-62); mask_preview() -> '••••••••' + last 4 (config.py:65-73); credential_status returns only masked values plus paths and model names (config.py:118-129); the project boundary states keys, summary model and base URL live in ~/.config/transcript/config.env and keys are never read from environment variables of the same name (config.py:1-7)
**Edge cases handled:** a key shorter than 4 characters would still be printed in full by the tail slice — not guarded; the status payload deliberately includes no base URL or key material beyond the tail; SQLite schema stores only paths, statuses and metrics, never keys (store.py:5-7)
**Confidence:** High

### RULE-107: Engine resolution: mode, artifact and per-task override decide which engine runs
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/engines/base.py:128-144`
**Plain English:** Offline mode always uses the local engine; online mode uses 'auto' (txt goes to DashScope, srt goes to OpenRouter) unless a per-task choice or the config overrides it.
**Specification:**
  Given config.online_engine = 'auto', artifact = 'txt', mode = 'online', no per-task override
  When  a transcription task is started
  Then  the engine id resolves to 'dashscope'; with artifact='srt' it resolves to 'openrouter'; with mode='offline' it always resolves to 'offline'; an explicit override of 'BCUT ' or 'DashScope' resolves (case-insensitive, trimmed) to that engine; an unrecognised override raises ValueError listing the allowed choices
**Parameters:** AUTO_BY_ARTIFACT = {txt: dashscope, srt: openrouter} (base.py:109); allowed online values = auto + every spec with online=True (base.py:112); unknown artifact falls back to 'dashscope' via dict .get default (base.py:141); engine id may carry a model override as 'family:model' (base.py:122-125)
**Edge cases handled:** mode='offline' short-circuits before any override is considered (base.py:137-138); blank/whitespace override falls back to config.online_engine, then to 'auto' (base.py:139); an unknown artifact string silently becomes dashscope rather than raising; a 'family:model' kind is split at the first colon and the model part is passed to the engine constructor (base.py:124-125); unknown engine id at lookup time raises ValueError('未知引擎') (base.py:115-119)
**Suspected defect:** AUTO_BY_ARTIFACT.get(artifact, 'dashscope') means a typo'd artifact silently routes to a paid engine instead of failing fast; the selector then selects the missing key at request time.
**Confidence:** Medium — Citation was corrected by referee (The cited path does not exist: there is no 'projects/' directory under legacy/transcript/ (or the workspace root), and no file 'projects/engines/base.py'; the engines registry lives at legacy/transcript/src/transcript/engines/base.py (identical copy at src/transcript/engines/base.py). At that real location, lines 128-144 are exactly the cited range and the rule…

### RULE-108: Bcut task result is polled every 1.5s until state 4 or a 300s deadline
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/engines/bcut.py:195-223`
**Plain English:** After submitting, the tool polls the result endpoint every 1.5 seconds and gives up after 5 minutes, treating the timeout as a retryable upstream slowness rather than a hard failure.
**Specification:**
  Given a submitted task whose state stays at 1
  When  the poll loop runs
  Then  it queries /task/result with model_id=7 and the task_id every 1.5s, stops as soon as state == 4, and after 300s of waiting raises a recoverable error naming the task id (so the chunk may be retried and the upload reused)
**Parameters:** POLL_INTERVAL_S = 1.5, POLL_TIMEOUT_S = 300.0, TASK_DONE_STATE = 4 (bcut.py:39-42); elapsed time is accumulated as a float counter, and the injected sleep makes it testable (bcut.py:56, 66)
**Edge cases handled:** state 4 with a dict result is returned as-is; a string result is parsed as JSON and invalid JSON is fatal (bcut.py:210-217); a poll HTTP >= 400 goes through the ban classifier (bcut.py:206-207); a poll network error is recoverable (bcut.py:204-205)
**Confidence:** High

### RULE-109: A 412 ban from the free anonymous engine triggers a 90-second self-imposed cooldown with fail-fast
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/engines/bcut.py:72-88`
**Plain English:** If the free anonymous service rate-limits the tool, the tool stops calling it for 90 seconds and fails the remaining chunks immediately instead of making the ban worse.
**Specification:**
  Given the bcut endpoint returns HTTP 412 with body 'request was banned' on the task-creation step
  When  the engine attempts a request
  Then  a fatal (non-retryable) error is raised telling the user to wait, resume later or switch engine, and the engine instance records a cooldown until now + 90s; every later chunk on that instance fails immediately without a network call and re-arms the cooldown
**Parameters:** BAN_COOLDOWN_S = 90.0 seconds (bcut.py:34); measured real-world ban lift ≈40 minutes (comment, bcut.py:76-79); detection is status 412 OR the literal body text 'request was banned' (bcut.py:81); the message steers the user to resume with the same engine or switch to DashScope/OpenRouter (bcut.py:83-87, 108-114)
**Edge cases handled:** the cooldown is per engine instance, so a new instance starts clean; the check is a monotonic-clock comparison, immune to wall-clock changes (bcut.py:108); 412 arriving during chunk upload is handled by the same path (bcut.py:164-165); the cooldown failure is classified fatal, so the retry loop does not sleep-and-retry it
**Confidence:** Medium — P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (FAITHFUL — yes. I read /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/engines/bcut.py:72-114 and errors.py:15-24, 40-52. The cited lines do exactly what the card says: '_raise_for_status' (bcut.py:81) triggers on 'status == 412 or "request was banned" in body', sets 'self._banne…

### RULE-110: 本机配置文件写入策略：原子替换、600 权限、保留用户内容
**Category:** Policy
**Priority:** P1
**Source:** `src/transcript/web/app.py:679-696`
**Plain English:** 写 config.env、提示词或词表时都保留用户手写的其他行与注释，只改目标项；先写临时文件、设成 600、再原子替换，中途失败不会留下半个文件，也不会出现短暂可被同机其他用户读到的窗口。
**Specification:**
  Given config.env 里有用户自写的注释和 OPENROUTER_BASE 行，接口保存 SUMMARY_MODEL 与 OpenRouter 密钥
  When  PUT /api/summary-settings 或 POST /api/credentials
  Then  注释与其他行原样保留；SUMMARY_MODEL 行被原地替换（没有则追加到末尾）；新文件权限 600，替换后再次 chmod 600
**Parameters:** 替换规则：匹配 strip() 后以 'ENV=' 开头的行，替换成 'ENV=值'；临时文件 = 原文件名 + '.tmp'；权限 0o600（写临时文件后与替换后各设一次）；提示词与词表同样走临时文件 + chmod 600 + 原子替换
**Edge cases handled:** 写失败时删除临时文件并转成 500「本机设置保存失败，请检查配置目录权限。」; manifest/提示词写入失败不会部分回滚已写入的 config.env（三步依次执行）; 热词块重写会把已有的热词行整段替换，规则行与注释保留，末尾空行被裁掉再补一块标准表头
**Suspected defect:** 写 config.env、summary-prompt.txt、glossary.txt 三步非事务：前两步成功、第三步失败时会返回 500，但磁盘已被部分更新（内存 config 也未更新），存在短暂不一致。
**Confidence:** High

### RULE-111: One theme wipe transition at a time; clicks during a transition are dropped
**Category:** Policy
**Priority:** P2
**Source:** `frontend/public/theme.js:55-62`
**Plain English:** Rapid repeated clicks on the theme toggle do not stack overlapping wipe animations — only the first click is acted on until the current transition finishes.
**Specification:**
  Given A wipe transition is in progress (running === true)
  When  The user clicks the theme toggle again before the transition completes
  Then  the click is silently discarded — wipeTheme returns immediately and the theme does not change
**Parameters:** Lock flag `running` (lines 43, 57, 62); the lock is only taken on the animated path, so feature-less / reduced-motion environments (lines 58-61) never queue clicks
**Edge cases handled:** Dropped clicks mean the toggle can end up in the opposite state from a naive click count — user intent is not queued or coalesced; The lock is a module-level variable, so it is per-page not per-button
**Confidence:** High

### RULE-112: Animation is skipped when unsupported or when reduced motion is requested
**Category:** Policy
**Priority:** P2
**Source:** `frontend/public/theme.js:58-61`
**Plain English:** The wipe animation only runs where the browser supports view transitions and the user has not asked for reduced motion; otherwise the theme still switches, just instantly.
**Specification:**
  Given document.startViewTransition is not a function, OR the media query '(prefers-reduced-motion: reduce)' matches
  When  The user clicks the theme toggle
  Then  setTheme(next) is called directly with no lock, no data-theme-transition attribute, and no animation
**Parameters:** Capability check captured once at load: canWipe = typeof document.startViewTransition === 'function' (line 42); reduced-motion query = '(prefers-reduced-motion: reduce)' (line 6)
**Edge cases handled:** canWipe is evaluated once at script load, so a browser that gains the API later is never upgraded in this page session; reducedMotion.matches is read at click time, so toggling the OS setting takes effect without reload
**Confidence:** High

### RULE-113: Sidebar refresh cadence: 2 s while work is in flight, 10 s otherwise
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/history-sidebar.tsx:74-93`
**Plain English:** The history list re-polls every 2 seconds while anything is running, being cancelled, or not yet finished, and drops to every 10 seconds when everything is settled.
**Specification:**
  Given A fetched task list
  When  The polling tick completes
  Then  If any task has running = true, cancelling = true, or is_terminal = false, the next fetch is scheduled in 2000 ms; otherwise in 10000 ms
**Parameters:** Busy interval = 2000 ms; idle interval = 10000 ms; interval after a failed request = 10000 ms. Busy predicate = running || cancelling || !is_terminal (evaluated across the whole list, any single busy task speeds up all polling). First fetch fires immediately on mount.
**Edge cases handled:** A failed fetch falls back to the idle 10000 ms cadence with no backoff and no user-visible error; is_terminal comes from the server, so a task left non-terminal by a crash keeps the sidebar in 2 s polling indefinitely; Polling stops when the component unmounts (alive flag plus clearTimeout), which is the only shutdown condition
**Confidence:** High

### RULE-114: History list is capped at the 50 newest tasks
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/history-sidebar.tsx:79`
**Plain English:** The sidebar only ever loads the 50 most recent tasks; older history is not reachable from this island.
**Specification:**
  Given The sidebar mounted with more than 50 tasks stored on the server
  When  The sidebar fetches the task list
  Then  GET /api/tasks?limit=50 is issued and only those 50 tasks are grouped and rendered
**Parameters:** Page size = 50 (hardcoded at the call site; the API client default is 20, lib/api.ts:21). Ordering is the server's, this file does not sort.
**Edge cases handled:** A task older than the 50 newest simply disappears from the sidebar with no paging or "load more" affordance; The inline boot() task list (line 72) is not subject to the 50 cap if the server embedded more
**Confidence:** High

### RULE-115: Badge colour contract: no coloured background, destructive is red text on a hairline only
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/ui/badge.tsx:6-22`
**Plain English:** Status badges never use a coloured fill: the default and outline badges are hairline-bordered neutral chips, and even the destructive badge is red text with a faint red hairline border instead of a red background.
**Specification:**
  Given A status badge for a failed transcription rendered as <Badge variant="destructive">Failed</Badge> and a neutral one as <Badge>Idle</Badge>
  When  Both render
  Then  Failed shows text-destructive with border-destructive/40 on the normal canvas with no fill; Idle shows border-hairline bg-canvas-soft with body-coloured text
**Parameters:** Shared: rounded-full, inline-flex, text-xs, font-normal (weight 400), px-2.5 py-0.5, border, transition-colors. Variants: default = border-hairline bg-canvas-soft text-body; secondary = border-transparent bg-secondary text-secondary-foreground (the only filled variant); destructive = border-destructive/40 text-destructive; outline = border-hairline text-body. Default variant = "default". Rendered as a plain <div>, not a button or a live region.
**Edge cases handled:** variant omitted -> neutral hairline chip; secondary is the sole filled variant and uses theme tokens, not red/green; no colour exists for "success"/"warning" states, so those must fall back to neutral or destructive styling; focus:outline-none is declared but a non-focusable div never focuses
**Suspected defect:** The comment on badge.tsx:6 states badges rely on hairline + grayscale text with no colour, but the destructive variant on line 14 sets text-destructive and a red border - the comment and the code disagree about whether colour is allowed. Separately, status is carried only by text and a 40%-opacity border colour: no icon, no aria role/status, so a failed job and a running job are distinguishable in greyscale only by their words.
**Confidence:** High

### RULE-116: Elevation model: hairline borders inline, shadows only on floating overlays
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/ui/dropdown-menu.tsx:51-67`
**Plain English:** Depth is signalled by surface type rather than decoration: inline surfaces (cards, alerts, fields, buttons) sit flat with a 1px hairline border and no shadow, while content that floats above the page (dropdown menus, select lists, dialogs, toasts) is portaled at z-50 with a real shadow.
**Specification:**
  Given A dropdown menu opened over a page containing a Card
  When  The menu content renders
  Then  The menu is portaled with rounded-md (6px), border, bg-popover, shadow-md, min-w-[8rem], sideOffset 4 and z-50, while the Card underneath keeps only its hairline border and no shadow
**Parameters:** Dropdown content (dropdown-menu.tsx:51-67): z-50, min-w-[8rem] (128px), rounded-md, border, bg-popover, shadow-md, sideOffset default 4, portal-mounted. Select content (select.tsx:33-61): rounded-md, border, bg-popover, shadow-md, position "popper", viewport sized to the trigger. Dialog (dialog.tsx:11-48): overlay fixed inset-0 z-50 bg-black/80, content shadow-lg, max-w-lg, centred via translate hacks. Toast (toast.tsx:24-39): shadow-lg, rounded-md. Card (card.tsx:9-17): rounded-lg border border-hairline bg-card, no shadow. Alert (alert.tsx:5-19) and Input (input.tsx:11-21): hairline border, no shadow. DESIGN.md:349-352 states the brand uses no shadows at all with hairline borders carrying elevation.
**Edge cases handled:** dropdown SubContent uses shadow-lg while top-level Content uses shadow-md; popover fills are bg-popover whereas inline fields use bg-canvas-soft and cards use bg-card - three near-black surfaces in play; radius is inconsistent: cards/alerts/inputs rounded-lg (8px), popovers rounded-md (6px), buttons/badges rounded-full
**Suspected defect:** Token drift against DESIGN.md: the brand spec lists only radii 0px / 8px / 9999px and says no shadows are used, yet this layer introduces rounded-md (6px) popovers and shadow-md/shadow-lg overlays. Also min-w-[8rem] uses rem while every DESIGN spacing token is px (2/4/8/12/16).
**Confidence:** Medium — Do floating overlays keep their elevated shadows in the rewrite, or does the brand's "no shadows anywhere, hairline borders carry elevation" rule apply to popovers and dialogs too? DESIGN.md and this code disagree, and it decides whether menus/dialogs are portaled shadow surfaces or flat hairline surfaces.

### RULE-117: Form-field chrome is identical across text input, textarea and select trigger
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/ui/input.tsx:5-24`
**Plain English:** Text inputs, textareas and select triggers all wear the same field skin: soft dark fill, hairline border, 8px corners, no shadow, muted placeholder, and a single thin focus ring with the native outline suppressed.
**Specification:**
  Given A form row containing a text input and a select trigger, both idle
  When  They render, and then the text input receives keyboard focus
  Then  Both are 40px tall (h-10), rounded-lg, border-hairline, bg-canvas-soft, text-sm with muted placeholders; on focus the border shifts to canvas-mid and a 1px ring-ring appears with no native outline
**Parameters:** Control height h-10 (40px) for input and select trigger; textarea min-h-[60px] with no fixed height; padding px-4 py-2; radius rounded-lg (8px = DESIGN rounded.sm); border border-hairline; background bg-canvas-soft; placeholder:text-mute; focus -> focus-visible:border-canvas-mid focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring; disabled -> cursor-not-allowed opacity-50 (select also disabled:opacity-50); no shadow utilities anywhere. Same skin repeated at select.tsx:19-22 and textarea.tsx:12-14.
**Edge cases handled:** caller className merges last via twMerge, so any of these can be overridden (e.g. h-11 for larger fields); textarea deliberately has no h-10 so it can grow with content beyond 60px; input has file:* overrides for file inputs (borderless, transparent, text-sm); select trigger uses 'focus:' while input/textarea use 'focus-visible:' - the same skin behaves differently for mouse users
**Suspected defect:** Pseudo-class inconsistency: select.tsx:20 uses focus:outline-none focus:ring-1, so clicking a select with the mouse draws a focus ring, while input.tsx:15 and textarea.tsx:13 use focus-visible: and only ring on keyboard focus. DESIGN.md:246/309 also specifies weight 400 everywhere and DESIGN.md:386-393 gives the input spec, but the code adds no error/invalid border treatment, so validation feedback has no home in this layer.
**Confidence:** High

### RULE-118: Toast auto-dismiss duration and swipe axis are library defaults, not stated in code
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/ui/toast.tsx:24-39`
**Plain English:** This component sets no on-screen lifetime for a toast and no swipe-direction policy: if the user does nothing, the toast disappears on the underlying primitive's default timer, and the only close affordance authored here is an icon that stays invisible until the toast is hovered or focused.
**Specification:**
  Given An error toast shown with no duration prop passed by the caller
  When  The user neither hovers nor clicks anything
  Then  The toast is removed automatically after the primitive's default timeout (Radix default 5000 ms) - a value that appears nowhere in this codebase's toast component
**Parameters:** No `duration` value is supplied anywhere in toast.tsx; Radix Toast defaults (duration 5000 ms, swipeDirection right) are inherited. Close control (toast.tsx:56-71) is opacity-0 and only becomes visible via group-hover:opacity-100 or focus:opacity-100, is positioned absolute right-1 top-1, and carries toast-close="" plus an icon only (no visible text label).
**Edge cases handled:** a close button that is invisible until hover is not discoverable on touch devices, where hover does not exist; swipe offsets are read from --radix-toast-swipe-move-x / -end-x, so the gesture axis is decided by the primitive; hover/focus pausing of the dismiss timer (if any) comes from the primitive, not from this file
**Suspected defect:** Auto-dismissing an error toast after a library-default 5s with no duration set anywhere means every failure notification - including long extraction failures - vanishes on a timer nobody chose. The close control is also opacity-0 until hover/focus, which is unreachable on touch.
**Confidence:** Low — How long should a toast stay on screen, and should the timer pause while the user hovers or focuses it? Should error toasts persist until dismissed while success toasts auto-dismiss? And should dismissing be a swipe gesture at all on touch devices where the close button never becomes visible?

### RULE-119: Single toast region: full-width top on phones, bottom-right capped at 420px on desktop
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/components/ui/toast.tsx:9-22`
**Plain English:** All toasts land in one fixed notification region - across the top of the screen on phones, and pinned to the bottom-right corner with a 420px cap on screens 768px and wider - ordered so the newest toast sits nearest that edge.
**Specification:**
  Given A 1200px-wide desktop window and a newly opened toast
  When  The toast opens
  Then  It is at most 420px wide, anchored bottom-right, stacked so the newest is nearest the bottom, and slides in from the bottom; on a 375px phone the region is full-width at the top and the toast slides in from above
**Parameters:** Viewport: fixed, z-[100], flex flex-col-reverse, max-h-screen, p-4; mobile-first top-0 full width; sm:bottom-0 sm:right-0 sm:top-auto sm:flex-col; md:max-w-[420px] (420px cap). Toast root: rounded-md, border, p-4 pr-6, shadow-lg, and state animations data-[state=open]:slide-in-from-top-full (mobile) / sm:slide-in-from-bottom-full (desktop), data-[state=closed]:slide-out-to-right-full + fade-out-80, plus data-[swipe=move|cancel|end] transitions (toast.tsx:32).
**Edge cases handled:** one ToastProvider/ToastViewport is expected for the whole app; two would create competing regions; column-reverse means DOM order is oldest-first and the newest toast appears closest to the anchored edge; a cancelled swipe animates back to translate-x-0 (data-[swipe=cancel]:translate-x-0); mobile maximum height is clamped to the viewport (max-h-screen) with no internal scroll
**Suspected defect:** No limit on how many toasts may be stacked at once; with max-h-screen on a phone a burst of notifications can fill the whole viewport. Nothing in this file deduplicates repeats (e.g. the same transcription error reported by several polls).
**Confidence:** High

### RULE-120: History is bucketed by local calendar day: today / yesterday / last 7 days / earlier
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/lib/task-groups.ts:22-34`
**Plain English:** History entries are grouped under 今天, 昨天, 本周 and 更早 based on how many local calendar days ago they were created, and empty groups are not drawn.
**Specification:**
  Given A task with created_at = an ISO timestamp carrying a timezone offset (e.g. 2026-10-17T09:30:00+00:00) and a local clock of 2026-10-17
  When  The sidebar groups the task list for display
  Then  Whole-day difference <= 0 groups as 今天, exactly 1 as 昨天, 2 through 6 as 本周, 7 or more as 更早; groups with no items are omitted
**Parameters:** Bucket boundaries: 0 / 1 / 2-6 / >=7 days, computed with bucket index `days <= 0 ? 0 : days === 1 ? 1 : days <= 6 ? 2 : 3`. DAY_MS = 86,400,000. Day difference = round((start of today - start of the task's local calendar day) / DAY_MS), using local midnight timestamps so DST does not distort the day count. Group keys: today/yesterday/week/earlier. Bucketing lives in lib/task-groups.ts:22-34; this file only calls it.
**Edge cases handled:** 2 through 6 days is a rolling window, so an entry counts as 本周 even if it falls in the previous calendar week; A created_at that will not parse (dirty data) is pushed into 更早 rather than dropping the whole list; A future-dated created_at (day difference <= 0) is bucketed as 今天; Ordering within a group is the server's order, not re-sorted by this code
**Suspected defect:** The label 本周 means "this week" but the implementation is a rolling 6-day window (days <= 6), so a Monday-created entry shows under 本周 the following Monday.
**Confidence:** Medium — Citation was corrected by referee (The rule is real and implemented faithfully, but not at the cited location. history-sidebar.tsx:125 is merely the invocation 'groupTasks(tasks).map((group) => (', which renders groups it is handed (group.key/group.label/group.items at lines 126-127) and holds no bucketing logic; empty-group suppression is likewise a property of the returned array. The actual log…

### RULE-121: Online mode alone exposes the engine picker and the credential panel
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/main.tsx:127-143`
**Plain English:** Switching the mode lever rewrites the form: the engine field and the key panel exist only for online runs, the advanced section opens automatically, and the hint and submit button are reworded to match what will actually happen.
**Specification:**
  Given the console with the offline radio selected
  When  the user switches the lever to online
  Then  the engine field and key panel become visible, the 更多设置 section is expanded, the hint becomes '上传音频到云端引擎，按量计费。' and the button becomes '开始在线转录'; switching back to offline hides both and restores '本机跑，不联网，不花钱。' / '开始离线转录'.
**Parameters:** Gate on checked radio value === 'online'; elements #engineField, #credentials; hint and submit text pairs as quoted
**Edge cases handled:** The credentials container is hidden by default in the static HTML, so offline users never see it even before React attaches.; The online engine value is submitted even for offline runs (main.tsx:214), where the server is expected to ignore it.
**Confidence:** High

### RULE-122: Subtitle vs transcript classification drives the default tab and the ready label
**Category:** Policy
**Priority:** P2
**Source:** `frontend/src/task.tsx:185-186`
**Plain English:** A task is treated as subtitle-producing when the SRT export exists or the requested artifact was SRT; otherwise it counts as transcript-shaped, which changes the default tab and the wording throughout the page.
**Specification:**
  Given a done task with artifact='txt' and srt_exists=false
  When  the result tabs first render
  Then  the 文稿 tab is selected by default and the panel footer reads 'TEXT · CHUNK · n 个片段'; with srt_exists=true the 字幕 tab is selected instead and the footer reads 'SRT · TIMED · n 条字幕'.
**Parameters:** defaultTab = (artifact === 'txt' && !srt_exists) ? 'transcript' : 'subtitle'; timed = srt_exists || artifact === 'srt'; the header badge uses the same test (task.tsx:1136) as does the info line (task.tsx:1141)
**Edge cases handled:** The same test appears four times in the file, so the classification can drift between the tab, the badge and the meta line.; The artifact is always 'srt' for jobs created from the console (main.tsx:206), so a console-created job lands on the subtitle tab.
**Confidence:** High

### RULE-123: UI colors resolve through CSS custom-property tokens, never literal values
**Category:** Policy
**Priority:** P2
**Source:** `frontend/tailwind.config.js:11-63`
**Plain English:** Every UI color is named once as a semantic token whose value is a CSS variable, so a theme (light/dark) is switched by redefining variables rather than editing any component code.
**Specification:**
  Given the design tokens are consumed as Tailwind utility classes (bg-canvas-card, text-ink, border-hairline, ...) across index.html, task.html, public/theme.js and src/**
  When  the app is rendered or the theme is toggled
  Then  each utility resolves to var(--<token>) defined in src/index.css, and the same variable name resolves differently per theme; no component contains a hardcoded hex value for these tokens
**Parameters:** Token namespaces in use: shadcn-style set (border, input, ring, background, foreground, primary/secondary/destructive/muted/accent/popover/card, each with a -foreground pair) + design-language set (canvas, canvas-soft, canvas-card, canvas-mid, hairline, surface-hover, surface-selected, ink, ink-hover, body, mute, sunset, sunset-soft, dusk, twilight, breeze, midnight). All values are indirection only — actual colors live in src/index.css (outside this file set). Theme JS is shared: public/theme.js, consumed by both index.html and task.html.
**Edge cases handled:** Two overlapping color vocabularies are both declared: a component-library set and a bespoke design-language set; nothing in these files says which one is authoritative.; Token comments cite /DESIGN.md as the source of truth for the design language; the actual variable values are not in this file set (src/index.css).; Two pages (index.html, task.html) share one theme implementation (public/theme.js), so a theme change is cross-page, not per-page.
**Confidence:** Medium — Are the 12 shadcn-style tokens (border/input/ring/background/foreground/primary/secondary/destructive/muted/accent/popover/card) actually used, or is the live palette the DESIGN.md set (canvas/ink/hairline/sunset/...)? Which of the two namespaces is the contract for the rewrite?

### RULE-124: Display/heading typography uses a fixed negative letter-spacing pair
**Category:** Policy
**Priority:** P2
**Source:** `frontend/tailwind.config.js:93-97`
**Plain English:** Large headline text is given a single tightening rule: one negative tracking value for display-size text and a smaller one for headings, so the tight-headline look is uniform across the app rather than hand-set per element.
**Specification:**
  Given any text styled with the display tracking token (or heading token)
  When  the text is rendered at display or heading size
  Then  letter-spacing is -0.02em for display and -0.01em for heading, regardless of the actual font size used
**Parameters:** display = -0.02em; heading = -0.01em. Comment cites the design source as -2.4px@96px ≈ -0.025em and -0.6px@32px ≈ -0.019em.
**Edge cases handled:** Letter-spacing is a fixed em value, not a function of font size, so it is only faithful to the design spec at the one size the design was measured at.; A comment refers to a caption style that uses uppercase mono with 1.2-1.4px tracking; no token implements that spacing in this file.; Design-language comments (near-black canvas, hairline borders, no shadow tiers, 400-weight display) are documentation only — the executable config here implements none of them beyond the color and sp…
**Suspected defect:** Documented design values and implemented tokens disagree by roughly 20-50%: comment states -2.4px@96 ≈ -0.025em and -0.6px@32 ≈ -0.019em, while the tokens are -0.02em and -0.01em (frontend/tailwind.config.js:93-97). The design-language note is only a comment, so the executable config value wins unless an SME says otherwise.
**Confidence:** Medium — The config comment says the design language defines display tracking as about -0.025em (from -2.4px at 96px) but the token is set to -0.02em; heading similarly is documented near -0.019em but set to -0.01em. Which value is correct — is the config intentionally looser than DESIGN.md, or is this a transcription error?

### RULE-125: Frontend build output must land at a fixed path with a Vite manifest for backend validation
**Category:** Policy
**Priority:** P2
**Source:** `frontend/vite.config.ts:16-27`
**Plain English:** The compiled frontend is published under a fixed URL prefix and must emit a manifest file, because the backend refuses or cannot serve a build that lacks it.
**Specification:**
  Given the frontend build runs to completion
  When  the backend validates or serves the compiled assets
  Then  assets are written to src/transcript/web/static/dist (previous contents cleared) and are reachable under the URL prefix /static/dist/, with .vite/manifest.json present at the output root
**Parameters:** base = '/static/dist/'; outDir = '../src/transcript/web/static/dist'; emptyOutDir = true; manifest = true. Backend consumer named in comment: validate_dist. Two named entries are required: main = frontend/index.html, task = frontend/task.html.
**Edge cases handled:** emptyOutDir = true means any hand-placed or previously built asset in the output directory is deleted on every build.; The manifest requirement is only asserted by a source comment; the enforcing backend routine (validate_dist) is outside the files reviewed, so the exact validation is unverified.; Dev-mode API calls are proxied to http://127.0.0.1:8765 with changeOrigin, so dev traffic assumes the backend listens on that fixed port.
**Confidence:** High

### RULE-126: Configuration file permission hygiene
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/config.py:203-210`
**Plain English:** The tool warns when the credential file is readable by group or others, and the generated template is always created with owner-only permissions and never overwritten.
**Specification:**
  Given config.env with mode 0644
  When  The server starts or the self-check runs
  Then  A warning is printed: '<path> is too permissive, run chmod 600 (currently 0o644)'; the warning contains no file contents; if the file does not exist no warning is produced
**Parameters:** Bits checked: S_IRWXG | S_IRWXO (config.py:208); the warning reports the current mode as an octal value; the template writer chmods 0600 unconditionally and only writes when the file is absent so existing keys are never cleared (config.py:249-270)
**Edge cases handled:** the warning is advisory — the file is not auto-chmodded; the config directory is created if missing when writing the template
**Confidence:** High

### RULE-127: The engine chooser shows a fixed catalog with per-engine readiness, limits and cost text
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/engines/base.py:174-203`
**Plain English:** The picker lists 'auto' plus every online engine, each labelled with its limits, its cost note and whether its key is configured.
**Specification:**
  Given an online engine with required_keys = ('dashscope_api_key',) and dashscope_api_key set
  When  the engine catalog is built for the page or the CLI
  Then  the entry appears with has_timestamps True, max_chunk_s 300.0 for dashscope, its cost note, and ready = True; an engine whose key is unset appears with ready = False
**Parameters:** DashScope cost note '按 token 计费（输入 ¥0.8/M，输出 ¥2.7/M）' (base.py:89); OpenRouter '≈$0.1/小时音频' (base.py:96); bcut '免费（音频会上传到 B 站存储）' (base.py:102); the synthetic 'auto' row advertises max_chunk_s = None and needs_key = every key of every online engine (base.py:178-188)
**Edge cases handled:** has_timestamps is hardcoded True for every online entry, including any future engine without timestamps (base.py:186,198); the auto row's advertised max_chunk_s is None even though it will route to DashScope's 300s limit; offline is excluded from the catalog list (base.py:176)
**Suspected defect:** The auto entry's readiness requires all keys of all online engines, so a user with only a DashScope key sees 'auto' greyed out although auto never needs an OpenRouter key for txt artifacts.
**Confidence:** High

### RULE-128: DashScope defaults transcription to Chinese with inverse text normalisation on
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/engines/dashscope.py:91-98`
**Plain English:** Unless the task specifies a language, DashScope transcribes as Chinese and converts spoken numbers and dates into written form.
**Specification:**
  Given a task started with no language selected
  When  the DashScope request body is built
  Then  asr_options.language = 'zh' and asr_options.enable_itn = True; when a language is supplied it replaces 'zh'; the returned result language is reported as the same value ('zh' when unset)
**Parameters:** language default 'zh' (dashscope.py:96, 122); enable_itn hardcoded True (dashscope.py:97)
**Edge cases handled:** the result's language field echoes the requested/default value rather than anything detected by the service; for OpenRouter the language field is omitted unless one is explicitly given (openrouter.py:59-60); offline reports a language detected by the local model instead of a default (offline.py:93-98)
**Confidence:** High

### RULE-129: Offline fallback when no timeline can be produced re-runs the same call and is therefore a no-op
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/engines/offline.py:100-110`
**Plain English:** If the aligned timeline comes back empty, the code is meant to fall back to the timing model's own text, but it re-runs the identical call with the same text, so the fallback cannot change the outcome.
**Specification:**
  Given want_timestamps True and a Qwen text for which build_segments returns an empty list
  When  the fallback branch runs
  Then  the whisper words are fetched a second time with the same repo and language and build_segments is called with the same text, so an identical empty result is produced and the engine returns text with an empty segment list and has_timestamps False
**Parameters:** the comment states the intent is to use whisper's own text when the timeline is unavailable (offline.py:107); the code passes the unchanged `text` variable into the retry (offline.py:109-110); build_segments returns an empty list before any work when the text is blank (align.py:172-173)
**Edge cases handled:** the first and second calls are indistinguishable from the outside, so the duplicate work is invisible in the result; the result still carries the full text, so no content is lost — only the timeline is
**Suspected defect:** The retry is byte-identical to the first attempt except for the recomputed word list, and build_segments is fed the same text, so has_timestamps can never be rescued by this branch; the comment describes behaviour the code does not implement.
**Confidence:** Medium — When character alignment yields no segments, should the fallback really substitute the timing model's own transcript text (which loses punctuation), or should the engine simply emit the segment-free result? The current retry passes the same text twice and cannot succeed on the second attempt. Which behaviour is intended?

### RULE-130: Offline ASR models are cached process-wide and reloaded only when the configured model id changes
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/engines/offline.py:21-35`
**Plain English:** Local models are heavy, so the tool keeps them loaded between chunks and only swaps them when the configured model changes.
**Specification:**
  Given a cached Qwen model loaded for model id A and a request for model id B
  When  a chunk is transcribed offline
  Then  the cached model is replaced with one loaded non-lazily for B and the cached id updates to B; a request for id A while A is cached returns the cached object without loading, so every chunk of one task reuses a single in-memory model
**Parameters:** module-level cache _qwen_model / _qwen_id (offline.py:21-22, 27); load_model(model_id, lazy=False) so the first chunk pays the full load (offline.py:33); comment records ≈4GB resident for both models (offline.py:9)
**Edge cases handled:** a missing mlx-audio installation surfaces as a fatal error with a 'uv sync' hint only at first load; the cache is global, so a model swap affects concurrent tasks in the same process (offline runs serially, online in parallel); the whisper timing model is not cached here at all — each call goes through mlx_whisper.transcribe with a repo path
**Confidence:** Medium — Citation was corrected by referee (The cited path 'projects/engines/offline.py' does not exist anywhere in the repo (verified with find over /Users/jasper/Documents/Transcript/legacy/transcript and the workspace: the only matches are legacy/transcript/src/transcript/engines/offline.py and src/transcript/engines/offline.py; there is no 'projects/' directory at all). So the citation as written poin…

### RULE-131: OpenRouter sends at most 50 hotwords as a prompt prefix
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/engines/openrouter.py:61-62`
**Plain English:** Terminology hints are passed to the srt engine as a prefixed prompt, capped at the first 50 terms.
**Specification:**
  Given a glossary of 80 terms and an srt task
  When  the multipart request is assembled
  Then  the form field prompt is set to '术语参考：' followed by the first 50 terms joined with '、'; with no hotwords the prompt field is omitted entirely
**Parameters:** hard cap 50 terms (openrouter.py:62); separator '、' and literal prefix '术语参考：'; the glossary is loaded by the pipeline and passed as the hotword list (pipeline.py:195, 468)
**Edge cases handled:** an empty hotword list is falsy so no prompt is sent; terms 51 and beyond are silently dropped with no warning to the user; the same hotword list is passed to DashScope, which is not declared to use it in the request body (dashscope.py:54-99) — the parameter is accepted and ignored
**Confidence:** High

### RULE-132: Glossary changes are disclosed in the products
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/glossary.py:178-182`
**Plain English:** Every applied replacement is listed as a comment line at the top of the txt and srt products, while the untouched original transcript is preserved in the raw JSON.
**Specification:**
  Given The run applied '艾麦' -> '集诚' three times
  When  Products are written
  Then  Both the .txt and .srt files start with '# glossary replacements (original transcript in .raw.json): 艾麦→集诚 x3' followed by a blank line; the .raw.json keeps merged_text_before_glossary with the untouched text plus a glossary_changes array of wrong/right/count
**Parameters:** Comment format 'wrong→right xN' (glossary.py:46); header line only added when there is at least one change (glossary.py:180-182); in SRT the comments precede entry 1 and are prefixed with '# ' (render.py:42-43); raw.json records both the pre-glossary text and the final text (pipeline.py:638-643)
**Edge cases handled:** a run with no glossary changes adds no header line; the comment header is dropped from an srt with no bodies at all; the raw JSON also records the resolved engine and chunk parameters for provenance
**Confidence:** High

### RULE-133: Product output directory fallback when the source directory is not writable
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/pipeline.py:565-577`
**Plain English:** Products are written next to the original file when that folder can be written to, and otherwise into a per-source subfolder of the configured output directory, with the user told that the location changed.
**Specification:**
  Given A source file in a read-only folder and OUTPUT_DIR = ~/Documents/Transcript/output
  When  The output directory is resolved
  Then  A probe file is created and deleted in the source folder; if that fails, products land in ~/Documents/Transcript/output/<source stem>/ (created if needed) and an event says 'original folder not writable, products moved to <path>'
**Parameters:** Probe file name '.transcript-write-test-<stem>' (pipeline.py:569); the fallback path is config.output_dir / src.stem, created with parents (pipeline.py:574-575); product names are <source stem>.txt, .srt, .raw.json (pipeline.py:364-370)
**Edge cases handled:** the probe file is touched and unlinked, so a crash between the two leaves a stray empty file; an unwritable fallback directory would raise at write time; products overwrite files with the same stem silently
**Confidence:** High

### RULE-134: Raw JSON provenance record
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/pipeline.py:585-645`
**Plain English:** Alongside the human-readable products, each run writes a raw JSON record that captures which engine, models and chunk parameters produced the result and the per-chunk outcome, so a transcript can be traced back to its inputs.
**Specification:**
  Given A completed run with 6 chunks, 2 of them having needed a retry
  When  The raw artefact is written
  Then  The file contains the task id, source path, mode, artifact, engine name, chunk count, the model and chunk-parameter snapshot, every chunk with its index, times, status, text, attempt count, error and word timings, the pre-glossary merged text, the final text, the segments and the glossary change list
**Parameters:** Config snapshot fields: offline_model, timing_model, vad_model, dashscope_model, openrouter_model, online_engine, chunk_min_s, chunk_max_s, chunk_overlap_s (pipeline.py:606-616); written as UTF-8 JSON with indent 2 and no ASCII escaping (pipeline.py:645); no credentials appear in the payload
**Edge cases handled:** chunk rows are re-read from the database, so they reflect persisted state including attempts and errors; the segment list in the raw record contains only times and text (speaker labels are not included)
**Confidence:** High

### RULE-135: SRT line wrapping for long segments
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/render.py:12-25`
**Plain English:** Subtitle text longer than 42 characters is split into at most two lines, preferring a break at the punctuation nearest after the midpoint.
**Specification:**
  Given A 60-character subtitle line with a comma 3 characters after the exact midpoint
  When  The SRT body is rendered
  Then  The line splits after that comma into two lines (the comma stays on the first line); if no punctuation appears in the 10 characters after the midpoint the line splits at the exact midpoint
**Parameters:** MAX_SRT_LINE_CHARS = 42 (render.py:12); punctuation searched in the 10 characters after the midpoint (render.py:22); Chinese has no spaces so the split is by character count (render.py:16-17); text is stripped before measuring
**Edge cases handled:** a 42-character line is not wrapped at all; only one split is ever made, so a very long line can still exceed 42 characters per line; wrapping counts punctuation and whitespace as characters
**Confidence:** High

### RULE-136: Speaker-labelled text output groups consecutive segments
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/render.py:51-88`
**Plain English:** When speakers are labelled, the text output merges each run of consecutive segments by the same speaker into one block prefixed with the speaker tag, using '?' for segments with no speaker.
**Specification:**
  Given Segments [speaker_1: '你好', speaker_1: '我们开始', speaker_2: '好的', None: '会议结束']
  When  The text product is rendered
  Then  Output blocks are '[speaker_1] 你好我们开始', '[speaker_2] 好的', '[?] 会议结束'; when no segment has a speaker the text is written one segment per line instead, and when the call is made without segments the merged text is written as-is
**Parameters:** Block prefix format '[<speaker>] ' (render.py:74,79); unknown speaker rendered as '?' (render.py:71); segments are concatenated with no separator inside a block; glossary change comments are prefixed with '# ' (render.py:60)
**Edge cases handled:** whitespace-only segments are skipped and do not break a speaker run; segment text is stripped before concatenation; the txt file is written even for srt-oriented runs
**Confidence:** High

### RULE-137: Extracting a summary goes through the stored transcript, not the audio
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/summary.py:336-347`
**Plain English:** Summarization uploads only the finished transcript text, never the audio, and falls back to reassembling the text from completed chunks when no transcript file is available.
**Specification:**
  Given A completed task whose .txt file is missing but whose chunks 0-3 are done
  When  The summary run collects its input
  Then  The text is the newline-joined text of the done chunks; if that is empty the run fails with 'transcript is empty, cannot summarize'
**Parameters:** Preference order: task.txt_path if the file exists, else chunk texts where status is 'done' (summary.py:341-344); the text is stripped before use (summary.py:345); only text is sent, never audio
**Edge cases handled:** the .txt file includes the glossary-change comment header lines, which are therefore sent to the model as part of the material; chunks with status failed are excluded from the fallback text
**Confidence:** High

### RULE-138: 模型清单按 Base URL 缓存 10 分钟
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/web/app.py:524-538`
**Plain English:** 模型清单按 Base URL 缓存 10 分钟，避免每次打开设置页都打上游接口；显式刷新可绕开缓存；拉取失败也缓存一条空清单加提示，页面仍可手填模型 ID。
**Specification:**
  Given 同一 Base URL 刚刚成功拉过一次清单，距上次 30 秒
  When  再次调用 GET /api/summary-models（不带 refresh）
  Then  直接返回缓存内容并标 cached=true，不发上游请求；若距上次超过 600 秒或带 refresh=true，则重新请求
**Parameters:** MODEL_CACHE_TTL_S = 600 秒；缓存键 = config.openrouter_base；上游请求超时 30 秒；失败时缓存 (时间, [], 提示语)
**Edge cases handled:** 没有配置 API Key 时直接返回空清单 + 「尚未配置 API Key 密钥，请先保存连接设置。」，不请求上游; 保存总结设置成功后会整体清空缓存; 上游返回非 200 或响应体损坏也走同一个失败分支，不阻断手填
**Confidence:** High

### RULE-139: 产物正文预览截断到 20 万字符
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/web/app.py:606-612`
**Plain English:** JSON 接口最多只回 20 万字符的产物正文，并明确告诉调用方被截断了；要看全文走单独的整文件下载接口。
**Specification:**
  Given 某任务的 txt 产物大小为 800KB
  When  调用 GET /api/tasks/{id}/output?kind=txt
  Then  返回前 200,000 个字符、truncated=true；完整字节改用 /output/file（带 Cache-Control: no-store，download=true 时作为附件下载）
**Parameters:** OUTPUT_PREVIEW_CHARS = 200,000（读取时多读 1 个字符用于判断是否被截断）；kind 只接受 txt / srt
**Edge cases handled:** kind 传非 txt 的值会被当成 srt 处理，再因属性为空返回 404「这个任务没有 xxx 产物」; 产物文件被移动/删除 → 404「txt 产物已被移动或删除：…」; 读取用 errors='replace' 容错，遇到坏字节不报错
**Confidence:** High

### RULE-140: 控制台默认值：离线优先、srt、中文、引擎自动
**Category:** Policy
**Priority:** P2
**Source:** `src/transcript/web/app.py:68`
**Plain English:** 页面新任务表单的默认选择是：离线模式、srt 产物、中文、在线引擎 auto（auto 时 txt 走百炼、srt 走 OpenRouter）——默认不产生任何在线费用。
**Specification:**
  Given 用户首次打开首页，未改动任何选项
  When  GET /api/status 返回 defaults
  Then  defaults = {"mode":"offline", "artifact":"srt", "language":"zh", "online_engine":"auto"}
**Parameters:** CONSOLE_DEFAULTS 常量即上表；auto 的实际解析规则：txt → dashscope、srt → openrouter（engines/base.py:109）
**Edge cases handled:** 默认离线意味着零成本、零上传，是在线模式必须由用户显式切换; 页面不再重复定义这组默认值，一律以后端返回为准
**Confidence:** High

## Rules requiring SME confirmation

- **RULE-001** (Medium): P0 panel doubts spec fidelity: P0 justified: the rule guards the integrity of the deliverable the tool exists to produce. Dedup happens only at chunk boundaries (merge.py:99-117), a piece is discarded only when the remainder is empty (merge.py:107-117), and the timeline is repaired so the player never shows two lines at once (merge.py:103-104). A wrong result here silently and irreversibly delete…
- **RULE-002** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Read /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/components/ui/progress.tsx (lines 1-27). The cited lines 9-22 do exactly what the rule states: the Radix Indicator is always 'h-full w-full flex-1' (full-width band) and the fill is produced only by 'style={{ transform: 'translat…
- **RULE-007** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: the code at frontend/src/task.tsx:85-102 does exactly what the card claims. fallbackLines filters 'chunk.status === 'done' && chunk.text.trim()' then flatMaps to chunk.segments when non-empty, else one trimmed chunk-level line, sorted by start; mergeChunkLines filters 'status === 'done'' a…
- **RULE-011** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: I read /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/chunking.py:37-93 and /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/config.py:109-111. With defaults min_s=30, max_s=120, overlap_s=0.5, the code computes inner = max(1.0, 120-0.5) = 119.5 (lin…
- **RULE-014** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: base.py:163-171 chunk_max_for() returns config.chunk_max_s when the engine spec's max_chunk_s is None, else min(config, engine); pipeline.py:264-270 applies the identical clamp on the engine instance (getattr(engine,'max_chunk_s',None)) plus chunk_min = min(config.chunk_min_s, chunk_max).…
- **RULE-015** (Medium): Citation was corrected by referee (The cited path does not exist as written. 'legacy/transcript/projects/engines/bcut.py' is not in the tree — the only bcut.py under legacy/transcript/ is '/Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/engines/bcut.py' (252 lines; byte-identical to '/Users/jasper/Documents/Transcript/src/transcript/engines/bcut.py'). The rule's text is correc…
- **RULE-025** (Medium): Should sub-millisecond halves always round up (half-up) rather than Python's half-to-even? For subtitle timing a systematic half-to-even tie-break is unusual; confirm the intended rounding rule.
- **RULE-034** (Medium): pricing.prompt 的币种与口径是否恒为「USD / 每 token 输入」？非数值/缺字段时应该显示「未知」还是显示 0？
- **RULE-037** (Medium): Where do the actual field rules live (which fields are required, maximum lengths, allowed characters, numeric ranges, file type/size for uploads), and are any of them currently enforced only by browser-native attributes rather than application code? Also: are there input types (number, email, password) whose native browser validation must be preserved?
- **RULE-040** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful. The cited client (frontend/src/lib/api.ts:94-105) is a thin POST wrapper, but the behavior it encodes is real on the server: app.py:713-716 skips empty 'keys' values ("留空 = 保持现状"), app.py:720-721 maps only 'clear' entries to "", app.py:726-731 mirrors the same skip into the live Config, an…
- **RULE-042** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: legacy/transcript/frontend/src/main.tsx:203-219 does exactly what the card says — reads #file and #sourcePath, always appends mode/artifact('srt', hardcoded line 206)/language/online_engine, then appends 'file' when fileInput.files?.[0] exists (line 215-216), else 'source_path' from the tr…
- **RULE-045** (Medium): Does the server normalise the stored Base URL (strip trailing slashes) on save? If not, the dirty check must normalise both sides.
- **RULE-048** (Medium): What exactly makes the server report summary.available=false — a missing API key, a missing Base URL, or both? The UI only mirrors the flag.
- **RULE-053** (Medium): Citation was corrected by referee (The cited range frontend/src/lib/types.ts:12-36 contains only TypeScript interface declarations (EngineEntry at 12-20; StatusPayload.online_ready/online_engines at 29-36) — no executable logic implements readiness or the chunk cap there. The only runtime code in the range is the __BOOT__ fallback at types.ts:172-186, which hard-codes online_ready:false when no p…
- **RULE-057** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (The Given/When/Then is faithful to dashscope.py:75-82: 330.5 > 300.5 raises FatalError quoting duration (330.5s via :.1f) and the cap (300s via :.0f) and naming CHUNK_MAX_S; 300.4 > 300.5 is false so the request proceeds to the POST at line 104. (Minor: the message also cites upstream code AUDIO_DUR…
- **RULE-061** (Medium): When artifact is 'txt' the code still writes a .srt file — an empty one for engines without timestamps. Is the txt task supposed to emit an empty .srt, or should .srt be written only for srt tasks?
- **RULE-066** (Medium): Citation was corrected by referee (The cited lines 108-125 of frontend/src/lib/types.ts are only the TypeScript interface 'SummarySettingsPayload' — a type declaration with no logic. It declares 'max_prompt_chars: number', 'max_hot_words: number', 'max_hot_word_chars: number' (lines 118, 122, 123), so it confirms only the "limits are published to the UI" half of the rule; it implements none of th…
- **RULE-072** (Medium): P0 panel doubts spec fidelity: P0 is justified: this is one of the four hard invariants the module declares in its own docstring (pipeline.py:6) and it is the pipeline's exit contract for the whole product. A truncated-but-complete-looking transcript is a wrong, silently shipped output (data integrity), and the failure branch is also what makes resume-without-repaying work; there is no downstream…
- **RULE-074** (Medium): When a chunk exhausts its retry budget, does the whole task fail (and stay resumable) or does the task continue with the gap? Which upstream failures count as retryable versus fatal?
- **RULE-080** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/task.tsx:913-932 matches the card exactly. 'const costs = task.mode === 'online'' (915); first click on online sets 'confirming' true (926), swapping variant to 'destructive' and label to 确认续跑 (925, 928) and rendering the wa…
- **RULE-081** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: task.tsx:945-951 matches the rule text exactly — busy = running//cancelling, failed = status==='failed' // (status==='running' && !busy), outcome precedence cancelling>failed>STATUS_LABEL, red mark via StatusMark (task.tsx:119 bg-destructive on failed, ping only when busy, 113-128), and th…
- **RULE-086** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (Faithful: every element of the rule is exactly what pipeline.py:428-457 does. Reuse set comes from store.done_chunk_indices (store.py:366-372, status='done'); the reuse branch (pipeline.py:436-449) rebuilds a TranscriptResult from state.text/state.segments with no engine call; the two exceptions are…
- **RULE-088** (Medium): Should a task that was stopped or failed mid-transcription be eligible for Agent summary of its partial transcript, or is done the only trigger? / Citation was corrected by referee (The rule as stated (per-task summary state machine disabled/waiting/running/done/failed, gating on transcription success + API key, content payload keys, startup sweep of stale running rows) does NOT live at the cited…
- **RULE-089** (Medium): Citation was corrected by referee (The cited lines frontend/src/lib/types.ts:59-65 are only the TypeScript interface field declarations (is_terminal, running, cancelling, resumable, txt_exists, srt_exists, src_exists) — no logic, no status set, no file-existence checks. The behavior described by the rule is real but implemented in the backend: src/transcript/web/app.py:143-175 is _task_payload, w…
- **RULE-093** (Medium): Is it intended that requesting stop never optimistically updates the row (state only arrives via the 2 s poll), or should the row show a pending-stop state immediately after the user clicks Stop?
- **RULE-094** (Medium): May a dialog be dismissed with Escape or a click on the backdrop, and does that answer differ for destructive confirmations (for example deleting a transcript or overwriting an existing file)? If any dialog must be answered explicitly, the rewrite needs a non-dismissible variant this layer does not provide.
- **RULE-098** (Medium): Confirm the delete endpoint only removes the task record and never deletes the source audio/output files — the UI comment asserts this but the frontend cannot verify it.
- **RULE-099** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (NOT P0. This is presentation-layer styling (class strings for button variants) in /Users/jasper/Documents/Transcript/legacy/transcript/frontend/src/components/ui/button.tsx:9-38. Nothing here moves money, enforces a legal/regulatory duty, guards data integrity, security or safety, or is the central…
- **RULE-104** (Medium): Does the backend summary request send exactly the transcript text, the prompt and the API key — and nothing else (no audio, no file paths, no task titles)? The UI states this but does not enforce or verify it.
- **RULE-107** (Medium): Citation was corrected by referee (The cited path does not exist: there is no 'projects/' directory under legacy/transcript/ (or the workspace root), and no file 'projects/engines/base.py'; the engines registry lives at legacy/transcript/src/transcript/engines/base.py (identical copy at src/transcript/engines/base.py). At that real location, lines 128-144 are exactly the cited range and the rule…
- **RULE-109** (Medium): P0 panel split on whether this is critical to the system's core purpose or a costly-if-wrong rule (FAITHFUL — yes. I read /Users/jasper/Documents/Transcript/legacy/transcript/src/transcript/engines/bcut.py:72-114 and errors.py:15-24, 40-52. The cited lines do exactly what the card says: '_raise_for_status' (bcut.py:81) triggers on 'status == 412 or "request was banned" in body', sets 'self._banne…
- **RULE-116** (Medium): Do floating overlays keep their elevated shadows in the rewrite, or does the brand's "no shadows anywhere, hairline borders carry elevation" rule apply to popovers and dialogs too? DESIGN.md and this code disagree, and it decides whether menus/dialogs are portaled shadow surfaces or flat hairline surfaces.
- **RULE-118** (Low): How long should a toast stay on screen, and should the timer pause while the user hovers or focuses it? Should error toasts persist until dismissed while success toasts auto-dismiss? And should dismissing be a swipe gesture at all on touch devices where the close button never becomes visible?
- **RULE-120** (Medium): Citation was corrected by referee (The rule is real and implemented faithfully, but not at the cited location. history-sidebar.tsx:125 is merely the invocation 'groupTasks(tasks).map((group) => (', which renders groups it is handed (group.key/group.label/group.items at lines 126-127) and holds no bucketing logic; empty-group suppression is likewise a property of the returned array. The actual log…
- **RULE-123** (Medium): Are the 12 shadcn-style tokens (border/input/ring/background/foreground/primary/secondary/destructive/muted/accent/popover/card) actually used, or is the live palette the DESIGN.md set (canvas/ink/hairline/sunset/...)? Which of the two namespaces is the contract for the rewrite?
- **RULE-124** (Medium): The config comment says the design language defines display tracking as about -0.025em (from -2.4px at 96px) but the token is set to -0.02em; heading similarly is documented near -0.019em but set to -0.01em. Which value is correct — is the config intentionally looser than DESIGN.md, or is this a transcription error?
- **RULE-129** (Medium): When character alignment yields no segments, should the fallback really substitute the timing model's own transcript text (which loses punctuation), or should the engine simply emit the segment-free result? The current retry passes the same text twice and cannot succeed on the second attempt. Which behaviour is intended?
- **RULE-130** (Medium): Citation was corrected by referee (The cited path 'projects/engines/offline.py' does not exist anywhere in the repo (verified with find over /Users/jasper/Documents/Transcript/legacy/transcript and the workspace: the only matches are legacy/transcript/src/transcript/engines/offline.py and src/transcript/engines/offline.py; there is no 'projects/' directory at all). So the citation as written poin…

## Rules folded into another

These rules described the same behavior as another rule in a different place, so they were merged into it (the kept rule lists their locations under "Also cited"):

- History is bucketed by local calendar day (今天/昨天/本周/更早) (frontend/src/lib/task-groups.ts:22-34) into History is bucketed by local calendar day: today / yesterday / last 7 days / earlier
- Engine selection by artifact when the engine is set to auto (legacy/transcript/src/transcript/engines/base.py:108-144 (AUTO_BY_ARTIFACT at line 109 and resolve_…) into Engine resolution: mode, artifact and per-task override decide which engine runs
- Agent summary lifecycle and its independence from transcription (src/transcript/summary.py:254-370) into Agent summary state machine
- Agent 总结的独立状态机与启动条件 (legacy/transcript/src/transcript/summary.py:280-334 (SummaryManager.enable + start_if_enabled: key…) into Agent summary state machine
- Enabling Agent summary: prerequisites, deferral, and the waiting state (src/transcript/summary.py:280-300 (enable: key check, 任务不存在, enabled=true/status=waiting/content=nu…) into Agent summary state machine
- Interrupted task is shown as interrupted, never as transcribing (frontend/src/components/history-sidebar.tsx:29-43) into A running task with no live process is reported as interrupted, not as running
- Refuse to send a chunk that exceeds the engine's single-call limit (src/transcript/pipeline.py:262-287) into Effective chunk length cap is the smaller of the configured max and the engine's declared limit
- Online-engine readiness and the effective chunk cap (src/transcript/engines/base.py:206-210 (online_ready), src/transcript/engines/base.py:174-203 (engi…) into Online capability is 'ready' when at least one online engine needs no credentials
- Model list caching and refresh (frontend/src/lib/api.ts:82-84) into 模型清单按 Base URL 缓存 10 分钟
