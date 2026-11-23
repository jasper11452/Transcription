# Data Objects — transcript

## Word
Source: `src/transcript/models.py:11`

| Field | Type | Note |
|---|---|---|
| text | str |  |
| start | float | seconds, absolute to the chunk |
| end | float |  |
| probability | float / None | None for DashScope; 0.0 default for whisper words |

Used by: Character-level time mapping with interpolation and a monotonic-time invariant, Sentence-splitting rules for subtitle lines, Offline transcription takes its text from the local ASR model and its timeline…, DashScope word-level timestamps are converted from milliseconds and the text is…, Raw JSON provenance record, Chunk-level transcription state

## Segment
Source: `src/transcript/models.py:21`

| Field | Type | Note |
|---|---|---|
| start | float |  |
| end | float |  |
| text | str |  |
| words | list[Word] | default_factory=list; empty when the engine reports no word times |
| speaker | str / None | e.g. 'speaker_1'; None = diarisation not done |
| duration | property float | max(0, end-start) |

Used by: Sentence-splitting rules for subtitle lines, Deduplicate only at chunk boundaries and never drop content, Overlap detection between consecutive chunks (dedup judgement), Speaker label assignment by longest overlap, Speaker-labelled text output groups consecutive segments, SRT line wrapping for long segments, SRT refuses inverted timestamps and numbers only surviving lines, An srt task is refused when the engine cannot supply timestamps, SRT timestamp format and rounding, Bcut utterances become segments: milliseconds to seconds, empty ones dropped, t…

## Chunk
Source: `src/transcript/models.py:47`

| Field | Type | Note |
|---|---|---|
| index | int | 0-based; the retry/persist unit id |
| start | float |  |
| end | float |  |
| duration | property float |  |

Used by: Chunk plan budget and the chunk-length invariant, Cut points land on silence gaps in preference to hard cuts, Overlap detection between consecutive chunks (dedup judgement), Effective chunk length cap is the smaller of the configured max and the engine'…, Cost is summed across chunks, but audio seconds are never aggregated, Concurrency policy: serial offline, parallel online, Raw JSON provenance record

## TranscriptResult
Source: `src/transcript/models.py:60`

| Field | Type | Note |
|---|---|---|
| text | str |  |
| segments | list[Segment] |  |
| language | str / None |  |
| audio_seconds | float / None | explicitly NOT summed across chunks in merge_results (merge.py:138) |
| cost_usd | float / None | 0.0 for bcut/offline, upstream value for OpenRouter, None for DashScope |
| engine | str | e.g. 'dashscope:qwen-audio-3.1-asr-flash' |
| has_timestamps | bool |  |

Used by: Cost is summed across chunks, but audio seconds are never aggregated, Cost attribution differs per engine: local and anonymous are free, the paid srt…, An srt task is refused when the engine cannot supply timestamps, Resume reuses completed chunks and re-runs only two special cases, Chunk-level transcription state, OpenRouter returns sentence-level segments and the authoritative cost of the ca…, DashScope word-level timestamps are converted from milliseconds and the text is…, Bcut utterances become segments: milliseconds to seconds, empty ones dropped, t…, Offline transcription takes its text from the local ASR model and its timeline…

## AudioInfo
Source: `src/transcript/models.py:84`

| Field | Type | Note |
|---|---|---|
| path | Path |  |
| duration | float | max over format.duration and stream duration; 0 means ineligible |
| size_bytes | int |  |
| codec | str / None |  |
| sample_rate | int / None |  |
| channels | int / None |  |
| has_audio | bool |  |
| megabytes | property float |  |

Used by: Input file eligibility check, Working-copy audio contract and its verification, Cost pre-estimate per engine and artifact, DashScope blocks a chunk longer than its 300s ceiling locally instead of spendi…, Bcut rejects anything that is not a non-empty mp3 before opening the network ca…, Cost is summed across chunks, but audio seconds are never aggregated

## Config
Source: `src/transcript/config.py:77`

| Field | Type | Note |
|---|---|---|
| config_path | Path | ~/.config/transcript/config.env |
| dashscope_api_key | str | masked only; never read from shell env |
| openrouter_api_key | str |  |
| dashscope_base | str |  |
| openrouter_base | str |  |
| bcut_base | str |  |
| online_engine | str | auto / dashscope / openrouter / bcut |
| dashscope_model | str |  |
| openrouter_model | str |  |
| summary_model | str |  |
| summary_prompt | str | loaded from sibling summary-prompt.txt |
| offline_model | str |  |
| timing_model | str | whisper-large-v3-turbo; timeline only |
| vad_model | str |  |
| enable_diar | bool |  |
| diar_lib | str |  |
| diar_model | str |  |
| state_db | Path |  |
| output_dir | Path |  |
| glossary_path | Path |  |
| online_concurrency | int | default 4 |
| max_attempts | int | default 3 |
| backoff_base | float |  |
| chunk_min_s | float | 30.0 |
| chunk_max_s | float | 120.0 |
| chunk_overlap_s | float | 0.5 |

Used by: Configuration precedence and legacy settings compatibility, Configuration file permission hygiene, Credential value sanitization on save, Credentials are only ever shown masked and never persisted outside the config f…, Engine resolution: mode, artifact and per-task override decide which engine runs, A task only starts if the credentials the chosen engine actually needs are pres…, Online capability is 'ready' when at least one online engine needs no credentia…, Effective chunk length cap is the smaller of the configured max and the engine'…, Concurrency policy: serial offline, parallel online, Retry policy: exponential backoff for recoverable errors only, Product output directory fallback when the source directory is not writable, Speaker separation is gated and never blocks the transcript, Offline ASR models are cached process-wide and reloaded only when the configure…, Agent summary settings: accepted fields, key retention, prompt fallback, Chunk plan budget and the chunk-length invariant

## KeyField
Source: `src/transcript/web/app.py:85`

| Field | Type | Note |
|---|---|---|
| attr | str | Config attribute name, e.g. 'dashscope_api_key' |
| env | str | attr.upper() |
| label | str | Chinese display label |
| status | str | from Config.credential_status(); masked tail only |
| masked | str | 8 bullets + last 4 chars, or '' when unset |
| configured | bool |  |

Used by: API keys are paste-only and never rendered back in clear, Credentials are only ever shown masked and never persisted outside the config f…, Credential save/clear payload: empty input still saves an empty key, Saving secrets: a blank field keeps the stored secret and a masked preview is n…, Engine is selectable only when ready; missing credentials are named, Online mode alone exposes the engine picker and the credential panel, Online capability is 'ready' when at least one online engine needs no credentia…, Fallback console state when the boot payload is missing

## tasks table row / TaskRecord
Source: `src/transcript/store.py:79`

| Field | Type | Note |
|---|---|---|
| id | int | SQLite AUTOINCREMENT PK |
| name | str |  |
| source_path | str |  |
| mode | str | offline / online |
| artifact | str | txt / srt |
| engine | str / None | resolved engine id incl. model, e.g. 'openrouter:...' |
| status | str | running / done / failed / pending |
| progress | float | 0-100, derived from done chunks |
| duration_s | float / None |  |
| audio_seconds | float / None |  |
| cost_usd | float / None |  |
| chars | int / None |  |
| out_dir | str / None |  |
| txt_path/srt_path/raw_path | str / None |  |
| error | str / None |  |
| created_at / updated_at | str | UTC ISO, timespec=seconds |
| is_terminal | property bool | status in {done, failed} |

Used by: Task and chunk status lifecycle; no partial products, Task lifecycle flags drive cancel/resume/delete, A running task with no live process is reported as interrupted, not as running, History list is capped at the 50 newest tasks, History is bucketed by local calendar day: today / yesterday / last 7 days / ea…, A row offers Stop while it is running and Delete only when it is not, Saved output files are only read for a finished, non-running task, Export actions appear only for artifacts that actually exist, Stop is not applied optimistically; row state changes only on the next poll, Resume reuses completed chunks and re-runs only two special cases, Progress percentage: from SSE current/total, clamped at the card, Task progress percentage is derived from the count of completed chunks, Store stats (tasks / audio_seconds / cost_usd / chars sums) feed the console

## chunks table row / ChunkState
Source: `src/transcript/store.py:106`

| Field | Type | Note |
|---|---|---|
| task_id | int | FK tasks(id) ON DELETE CASCADE, half of the composite PK |
| idx | int | other half of the composite PK |
| start / end | float |  |
| status | str | pending / done / failed |
| text | str |  |
| words | list[Word] | persisted as words_json TEXT |
| segments | list[Segment] | persisted as segments_json TEXT; column added by _migrate (store.py:150) |
| attempts | int |  |
| error | str / None |  |
| done | property bool | status == 'done' |

Used by: Chunk-level transcription state, Task and chunk status lifecycle; no partial products, Resume reuses completed chunks and re-runs only two special cases, Cancellation semantics: stop at a chunk boundary and keep what is done, Deduplicate only at chunk boundaries and never drop content, Task progress percentage is derived from the count of completed chunks, Progress percentage: from SSE current/total, clamped at the card, Raw JSON provenance record, Retry policy: exponential backoff for recoverable errors only

## task_summaries table row / summary state dict
Source: `src/transcript/store.py:59`

| Field | Type | Note |
|---|---|---|
| task_id | int | PK, FK tasks(id) ON DELETE CASCADE |
| enabled | bool | stored as INTEGER |
| status | str | disabled / waiting / running / done / failed |
| content | dict / None | JSON: {title, overview, key_points[], action_items[], reasoning?} |
| error | str / None |  |
| model | str / None |  |

Used by: Agent summary state machine, Summary lifecycle and 700 ms polling, ending in a task-title refresh, Summary cannot be started until a working model connection exists, Enable / regenerate / retry summary all use the same enable action, Extracting a summary goes through the stored transcript, not the audio, Summary result normalization and length caps, Streaming summary shows title/overview/key points as soon as each field closes

## Progress
Source: `src/transcript/pipeline.py:41`

| Field | Type | Note |
|---|---|---|
| stage | str | probe/normalize/vad/plan/chunk/chunk_failed/retry/merge/diar/write/done/failed |
| message | str | display only |
| current | int |  |
| total | int |  |
| chunk_index | int / None | None for task-level stages |

Used by: SSE 进度流：先补历史，再实时推，空闲时心跳, Progress percentage: from SSE current/total, clamped at the card, Detail-page event stream connects only while work is live and closes on result, Chunk list merge keyed by chunk index, Only completed chunks feed the live subtitle/text view, Console submission lifecycle: queue, stream, and terminal outcome, Task progress percentage is derived from the count of completed chunks

## RunResult
Source: `src/transcript/pipeline.py:61`

| Field | Type | Note |
|---|---|---|
| task_id | int |  |
| status | str | done / failed |
| engine | str |  |
| out_dir | Path / None |  |
| txt_path / srt_path / raw_path | Path / None |  |
| audio_seconds | float / None |  |
| cost_usd | float / None |  |
| chars | int | count after normalize_for_compare stripping |
| changes | list[Change] |  |
| error | str / None |  |

Used by: Task and chunk status lifecycle; no partial products, Task lifecycle flags drive cancel/resume/delete, Cost is summed across chunks, but audio seconds are never aggregated, Glossary changes are disclosed in the products, Raw JSON provenance record, Console submission lifecycle: queue, stream, and terminal outcome, Detail-page event stream connects only while work is live and closes on result, One error contract for every API call, Cancellation semantics: stop at a chunk boundary and keep what is done

## Job
Source: `src/transcript/web/jobs.py:27`

| Field | Type | Note |
|---|---|---|
| task_id | int |  |
| source | str | stringified path |
| mode | str |  |
| artifact | str |  |
| language | str / None |  |
| online_engine | str / None | per-task override; None = use config default |

Used by: Concurrency policy: serial offline, parallel online, Engine resolution: mode, artifact and per-task override decide which engine runs, Resuming an interrupted task keeps the engine it originally ran on instead of r…, Retry policy: exponential backoff for recoverable errors only, Cancellation semantics: stop at a chunk boundary and keep what is done, 控制台默认值：离线优先、srt、中文、引擎自动

## Engine (protocol)
Source: `src/transcript/engines/base.py:24`

| Field | Type | Note |
|---|---|---|
| name | str | '<family>:<model>' |
| has_timestamps | bool | class attribute on all four adapters |
| max_chunk_s | float / None | None = no declared duration cap (offline, openrouter, bcut) |
| transcribe(audio_path, *, language, hotwords, want_timestamps) | (Path, ...) -> TranscriptResult | must raise a TranscriptError subclass on failure |

Used by: Effective chunk length cap is the smaller of the configured max and the engine'…, An srt task is refused when the engine cannot supply timestamps, Engine resolution: mode, artifact and per-task override decide which engine runs, Cost attribution differs per engine: local and anonymous are free, the paid srt…, Offline transcription takes its text from the local ASR model and its timeline…, Working-copy audio contract and its verification, DashScope blocks a chunk longer than its 300s ceiling locally instead of spendi…, Bcut rejects anything that is not a non-empty mp3 before opening the network ca…, Bcut upload splits the audio into server-sized pieces and chains their ETags, OpenRouter returns sentence-level segments and the authoritative cost of the ca…, HTTP failure classification: retryable or fatal

## EngineSpec / SPECS registry
Source: `src/transcript/engines/base.py:64`

| Field | Type | Note |
|---|---|---|
| id | str | offline / dashscope / openrouter / bcut |
| label | str |  |
| build | Callable[[Config, str / None], Engine] |  |
| required_keys | tuple[str, ...] | Config attribute names |
| max_chunk_s | float / None | DashScope 300.0 only |
| cost_note | str |  |
| online | bool | False for offline |

Used by: Engine chooser shows a fixed catalog with per-engine readiness, limits and cost…, Engine resolution: mode, artifact and per-task override decide which engine runs, A task only starts if the credentials the chosen engine actually needs are pres…, Online capability is 'ready' when at least one online engine needs no credentia…, Effective chunk length cap is the smaller of the configured max and the engine'…, Cost attribution differs per engine: local and anonymous are free, the paid srt…, Resuming an interrupted task keeps the engine it originally ran on instead of r…, Cost pre-estimate per engine and artifact

## EngineEntry (engine catalog entry)
Source: `src/transcript/engines/base.py:174`

| Field | Type | Note |
|---|---|---|
| id | str | includes synthetic 'auto' |
| label | str |  |
| needs_key | list[str] |  |
| max_chunk_s | float / None | None for auto |
| has_timestamps | bool | hardcoded True for every entry |
| cost | str |  |
| ready | bool |  |

Used by: Engine is selectable only when ready; missing credentials are named, Engine chooser shows a fixed catalog with per-engine readiness, limits and cost…, Online mode alone exposes the engine picker and the credential panel, Online capability is 'ready' when at least one online engine needs no credentia…, Fallback console state when the boot payload is missing, 控制台默认值：离线优先、srt、中文、引擎自动

## Rule (glossary rule)
Source: `src/transcript/glossary.py:25`

| Field | Type | Note |
|---|---|---|
| wrong | str |  |
| right | str |  |

Used by: Glossary file grammar and entry validation, Glossary replacement order and change counting, Hot-word list composition and caps, Glossary changes are disclosed in the products, OpenRouter sends at most 50 hotwords as a prompt prefix

## Change (glossary replacement record)
Source: `src/transcript/glossary.py:40`

| Field | Type | Note |
|---|---|---|
| wrong | str |  |
| right | str |  |
| count | int | occurrences actually replaced |
| describe() | () -> str | 'wrong→right ×count' |

Used by: Glossary replacement order and change counting, Glossary changes are disclosed in the products, Raw JSON provenance record, Task and chunk status lifecycle; no partial products

## GlossaryIssue
Source: `src/transcript/glossary.py:31`

| Field | Type | Note |
|---|---|---|
| line | int | 1-based line number |
| message | str |  |
| describe() | () -> str | '第 N 行：...' |

Used by: Glossary file grammar and entry validation

## SummaryContent (pydantic response contract)
Source: `src/transcript/summary.py:34`

| Field | Type | Note |
|---|---|---|
| title | str | min_length=1 max_length=80 |
| overview | str | min_length=1 max_length=2000 |
| key_points | list[str] | max_length=8 |
| action_items | list[str] | max_length=8 |

Used by: Summary output contract handed to the model, Summary result normalization and length caps, Prompt and hot-word limits

## SummaryPayload (summary state handed to the page)
Source: `src/transcript/summary.py:267`

| Field | Type | Note |
|---|---|---|
| enabled | bool |  |
| status | 'disabled' / 'waiting' / 'running' / 'done' / 'failed' |  |
| content | dict / None | {title?, overview, key_points[], action_items[], reasoning?} |
| error | str / None |  |
| model | str | state model or current config model |
| available | bool | openrouter_api_key present |
| partial.content | str | raw streaming JSON accumulator, throttled to 0.15 s |
| partial.reasoning | str | accumulated reasoning channel text |

Used by: Agent summary state machine, Summary lifecycle and 700 ms polling, ending in a task-title refresh, Enable / regenerate / retry summary all use the same enable action, Streaming summary shows title/overview/key points as soon as each field closes, Summary cannot be started until a working model connection exists, Enabling a summary discloses transcript text and key to the configured Base URL, Summary result normalization and length caps

## SummarySettingsPayload
Source: `src/transcript/web/app.py:378`

| Field | Type | Note |
|---|---|---|
| model | str |  |
| default_model | str |  |
| base_url | str |  |
| default_base_url | str |  |
| api_key_configured | bool |  |
| api_key_masked | str | masked preview only; never the value |
| prompt | str | falls back to DEFAULT_SUMMARY_PROMPT when empty |
| default_prompt | str |  |
| custom_prompt | bool |  |
| max_prompt_chars | int | 12000 |
| config_path | str |  |
| prompt_path | str | sibling summary-prompt.txt |
| hot_words | list[str] |  |
| max_hot_words | int | 80 |
| max_hot_word_chars | int | 40 |
| glossary_path | str |  |

Used by: Agent summary settings: accepted fields, key retention, prompt fallback, Prompt and hot-word limits, Hot words: separators, 40-character truncation, exact-match dedupe, 80-word cap, Summary settings can only be saved with a non-empty model and Base URL, Model list cannot be fetched while the connection settings have unsaved edits, Base URL 校验：只允许干净的本机/服务地址, API keys are paste-only and never rendered back in clear, Saving secrets: a blank field keeps the stored secret and a masked preview is n…, Restoring defaults does not touch the API key or the hot words, 模型清单按 Base URL 缓存 10 分钟

## SummaryModel / SummaryModelListPayload
Source: `src/transcript/web/app.py:527`

| Field | Type | Note |
|---|---|---|
| models[].id | str |  |
| models[].name | str |  |
| models[].context_length | int / None |  |
| models[].reasoning | bool | derived from supported_parameters containing 'reasoning' |
| models[].price_per_million_prompt | float / None | upstream price * 1e6; None when unparsable |
| error | str / None |  |
| cached | bool |  |

Used by: Model list filtering and display cap of 60, 模型清单里的每百万 token 单价, 模型清单按 Base URL 缓存 10 分钟, Model list cannot be fetched while the connection settings have unsaved edits, Summary cannot be started until a working model connection exists, Summary settings can only be saved with a non-empty model and Base URL

## PartialSummary (client-side streaming parse)
Source: `frontend/src/lib/summary-stream.ts:3`

| Field | Type | Note |
|---|---|---|
| title | str |  |
| overview | str |  |
| keyPoints | string[] |  |
| actionItems | string[] |  |
| titleComplete | boolean | closing quote of the title string seen |
| overviewComplete | boolean |  |

Used by: Streaming summary shows title/overview/key points as soon as each field closes, Summary lifecycle and 700 ms polling, ending in a task-title refresh, Agent summary state machine

## StatusPayload
Source: `src/transcript/web/app.py:133`

| Field | Type | Note |
|---|---|---|
| online_ready | bool |  |
| online_engines | EngineEntry[] |  |
| credentials | dict[str, str] | masked status strings only |
| key_fields | KeyField[] |  |
| defaults | ConsoleDefaults |  |
| stats | dict[str, float] | tasks / audio_seconds / cost_usd / chars sums |

Used by: Fallback console state when the boot payload is missing, Online capability is 'ready' when at least one online engine needs no credentia…, Engine is selectable only when ready; missing credentials are named, Online mode alone exposes the engine picker and the credential panel, Credentials are only ever shown masked and never persisted outside the config f…, Console defaults: offline by default, and the credentials deep link forces onli…, 内联到页面的 JSON 必须转义尖括号与行分隔符

## ConsoleDefaults
Source: `src/transcript/web/app.py:68`

| Field | Type | Note |
|---|---|---|
| mode | str | 'offline' |
| artifact | str | 'srt' |
| language | str | 'zh' |
| online_engine | str | 'auto' |

Used by: Console defaults: offline by default, and the credentials deep link forces onli…, 控制台默认值：离线优先、srt、中文、引擎自动, Subtitle vs transcript classification drives the default tab and the ready label, Engine resolution: mode, artifact and per-task override decide which engine runs, Online mode alone exposes the engine picker and the credential panel

## Task (API payload)
Source: `src/transcript/web/app.py:143`

| Field | Type | Note |
|---|---|---|
| id | int |  |
| name | str |  |
| title | str | summary title, fallback to source file name |
| source_name / source_path | str |  |
| mode | str |  |
| artifact | str |  |
| status | str |  |
| progress | float |  |
| engine | str / None |  |
| duration_s / audio_seconds / cost_usd / chars | float / int / None |  |
| out_dir / txt_path / srt_path / raw_path | str / None |  |
| error | str / None |  |
| created_at | str | UTC ISO with offset — clients must parse, not slice |
| is_terminal | bool |  |
| running | bool | from JobManager live process set, not the DB |
| cancelling | bool |  |
| resumable | bool | not running AND status in {pending, running, failed} |
| txt_exists / srt_exists / src_exists | bool | live filesystem checks |

Used by: Task lifecycle flags drive cancel/resume/delete, A running task with no live process is reported as interrupted, not as running, A row offers Stop while it is running and Delete only when it is not, Permanent delete requires a second click within a 4-second window, History list is capped at the 50 newest tasks, History is bucketed by local calendar day: today / yesterday / last 7 days / ea…, Sidebar refresh cadence: 2 s while work is in flight, 10 s otherwise, Stop is not applied optimistically; row state changes only on the next poll, Saved output files are only read for a finished, non-running task, Export actions appear only for artifacts that actually exist, Subtitle vs transcript classification drives the default tab and the ready label, Resuming an online task costs money and needs an explicit second confirmation

## ChunkItem (chunk as sent to the page)
Source: `src/transcript/store.py:122`

| Field | Type | Note |
|---|---|---|
| idx | int |  |
| start / end | float |  |
| status | str |  |
| chars | int | len(text), computed at serialisation time |
| text | str |  |
| segments | SubtitleLine[] | projected to {start,end,text}; words and speaker are dropped |
| attempts | int |  |
| error | str / None |  |

Used by: Only completed chunks feed the live subtitle/text view, Chunk list merge keyed by chunk index, Subtitle source precedence: saved SRT file beats live chunks, Transcript text source: saved TXT file beats chunk text, Task progress percentage is derived from the count of completed chunks, Progress percentage: from SSE current/total, clamped at the card, Chunk-level transcription state

## SubtitleLine
Source: `frontend/src/lib/types.ts:68`

| Field | Type | Note |
|---|---|---|
| start | number | seconds |
| end | number |  |
| text | string |  |

Used by: SRT parsing: block layout, timestamp format, and dropped entries, Subtitle source precedence: saved SRT file beats live chunks, Only completed chunks feed the live subtitle/text view, Sentence-splitting rules for subtitle lines, SRT line wrapping for long segments

## TaskDetail
Source: `src/transcript/web/app.py:177`

| Field | Type | Note |
|---|---|---|
| task | Task |  |
| chunks | ChunkItem[] |  |
| running | bool |  |
| cancelling | bool |  |
| resumable | bool |  |

Used by: Detail-page event stream connects only while work is live and closes on result, Chunk list merge keyed by chunk index, Only completed chunks feed the live subtitle/text view, Subtitle source precedence: saved SRT file beats live chunks, Transcript text source: saved TXT file beats chunk text, Task lifecycle flags drive cancel/resume/delete, A running task with no live process is reported as interrupted, not as running

## CreateTaskRequest (create form payload)
Source: `src/transcript/web/app.py:247`

| Field | Type | Note |
|---|---|---|
| file | UploadFile / undefined | multipart; when present it beats source_path |
| source_path | str | usually empty from the console, which always sends artifact='srt' |
| mode | str |  |
| artifact | str |  |
| language | str |  |
| online_engine | str |  |

Used by: 提交任务前的输入校验（模式 / 产物 / 在线引擎 / 源文件）, Audio source is required and an attached file beats a typed path, 上传文件 2GB 上限, A task only starts if the credentials the chosen engine actually needs are pres…, Console submission lifecycle: queue, stream, and terminal outcome, Input file eligibility check, Engine resolution: mode, artifact and per-task override decide which engine runs, 控制台默认值：离线优先、srt、中文、引擎自动

## Boot (inlined startup payload)
Source: `src/transcript/web/app.py:124`

| Field | Type | Note |
|---|---|---|
| status | StatusPayload |  |
| task | TaskDetail / null | null for / and for unknown or non-numeric task ids |
| tasks | Task[] / undefined | newest 50, optional — older bundles/test stubs omit it |

Used by: Fallback console state when the boot payload is missing, 内联到页面的 JSON 必须转义尖括号与行分隔符, History list is capped at the 50 newest tasks, Sidebar refresh cadence: 2 s while work is in flight, 10 s otherwise, Console defaults: offline by default, and the credentials deep link forces onli…, Saved output files are only read for a finished, non-running task

## SSE event (progress / result / close)
Source: `src/transcript/web/jobs.py:92`

| Field | Type | Note |
|---|---|---|
| type | 'progress' / 'result' / 'close' |  |
| stage | str | progress only; mirrors Progress.stage |
| message | str |  |
| current | int | overwritten with done-chunk count because online chunks finish out of order |
| total | int |  |
| chunk_index | int / null |  |
| chunk | ChunkItem? | attached only for chunk / chunk_failed stages |
| * | RunResult.as_dict() | flattened onto the result event |

Used by: SSE 进度流：先补历史，再实时推，空闲时心跳, Progress percentage: from SSE current/total, clamped at the card, Detail-page event stream connects only while work is live and closes on result, Console submission lifecycle: queue, stream, and terminal outcome, Chunk list merge keyed by chunk index, Only completed chunks feed the live subtitle/text view, Stop is not applied optimistically; row state changes only on the next poll, Progress bar fill is a left-shift of a full-width band, not a width change, Sidebar refresh cadence: 2 s while work is in flight, 10 s otherwise

## raw.json provenance record
Source: `src/transcript/pipeline.py:585`

| Field | Type | Note |
|---|---|---|
| task_id | int |  |
| source | str |  |
| mode / artifact | str |  |
| engine | str |  |
| chunk_count | int |  |
| config | dict | frozen snapshot of the model ids and chunking knobs used |
| chunks[] | list | idx/start/end/status/text/attempts/error/words[] read back from SQLite |
| merged_text_before_glossary | str | raw ASR text, kept untouched |
| final_text | str |  |
| segments[] | list | {start,end,text} |
| glossary_changes[] | list | {wrong,right,count} |

Used by: Raw JSON provenance record, Glossary changes are disclosed in the products, Glossary replacement order and change counting, Task and chunk status lifecycle; no partial products, Cost is summed across chunks, but audio seconds are never aggregated

## Estimate payload (/api/estimate)
Source: `src/transcript/web/app.py:222`

| Field | Type | Note |
|---|---|---|
| ok | bool |  |
| error | str | present only when ok is false |
| duration_s | float |  |
| estimated_cost_usd | float / None | None = price not fixed for that engine; the UI must not invent a number |
| chunk_max_s | float |  |

Used by: Cost pre-estimate per engine and artifact, Cost attribution differs per engine: local and anonymous are free, the paid srt…, Effective chunk length cap is the smaller of the configured max and the engine'…, Input file eligibility check

## Output preview payload (/api/tasks/{id}/output)
Source: `src/transcript/web/app.py:606`

| Field | Type | Note |
|---|---|---|
| content | str | truncated to OUTPUT_PREVIEW_CHARS (200 000) |
| path | str |  |
| truncated | bool |  |

Used by: 产物正文预览截断到 20 万字符, Saved output files are only read for a finished, non-running task, Export actions appear only for artifacts that actually exist, One error contract for every API call

## Theme preference record (localStorage 'transcript-theme')
Source: `frontend/public/theme.js:3`

| Field | Type | Note |
|---|---|---|
| transcript-theme | 'light' / 'dark' (string) | any other stored value is treated as absent |
| documentElement.classList | living state | exactly one of 'light' / 'dark' plus the derived colorScheme style |
| root.dataset.themeTransition | transient flag | present only while a wipe transition is running |

Used by: Theme preference resolution precedence, Saved preference is only accepted as an exact, known value, Storage unavailability degrades to session-only theming, Theme changes propagate across tabs, Live OS theme changes are honoured only without an explicit user preference, Toggle flips to the opposite of the currently applied theme, One theme wipe transition at a time; clicks during a transition are dropped, Transition lock is always released, with a hard timeout backstop, Animation is skipped when unsupported or when reduced motion is requested

## Design tokens (CSS custom properties)
Source: `frontend/src/index.css:15`

| Field | Type | Note |
|---|---|---|
| --canvas / --canvas-soft / --canvas-card / --canvas-mid | color |  |
| --hairline | color | the only inline elevation cue |
| --ink / --ink-hover / --body / --mute | color |  |
| --sunset / --sunset-soft / --dusk / --twilight / --breeze / --midnight | color |  |
| --surface-hover / --surface-selected / --surface-subtle | rgba color |  |
| --radius | length | 0.5rem; md/sm are derived as calc() offsets |
| --ease-out | cubic-bezier |  |
| :root vs html.light | theme scope | identical variable set in both blocks; light adds no new names |

Used by: UI colors resolve through CSS custom-property tokens, never literal values, Small corner radii are derived from a single radius token, Display/heading typography uses a fixed negative letter-spacing pair, Button style contract: pill shape, weight 400, no shadow, and only the primary…, Badge colour contract: no coloured background, destructive is red text on a hai…, Form-field chrome is identical across text input, textarea and select trigger, Elevation model: hairline borders inline, shadows only on floating overlays, Progress bar fill is a left-shift of a full-width band, not a width change, Tab underline is placed by pixel measurement, animated only on tab change, Single toast region: full-width top on phones, bottom-right capped at 420px on…

## Vite build manifest
Source: `src/transcript/web/frontend.py:31`

| Field | Type | Note |
|---|---|---|
| <entry>.isEntry | bool | must be true for index.html and task.html |
| <entry>.file | str | must exist next to the manifest |
| <entry>.css | list[str] | each must exist |
| theme.js | str | not in the manifest; validated only when the HTML references /static/dist/theme.js |

Used by: Frontend build output must land at a fixed path with a Vite manifest for backen…, 服务启动时的前端产物完整性硬门槛

## SSE keep-alive / job event log
Source: `src/transcript/web/jobs.py:164`

| Field | Type | Note |
|---|---|---|
| _events[task_id] | list[dict] | ring buffer capped at MAX_EVENTS_PER_TASK (500); rebuilt empty on every new run of the same task_id |
| _subscribers[task_id] | list[queue.Queue] | unbounded queues; enqueue never blocks or does I/O |
| : keep-alive | comment frame | emitted every 15 s of idleness |

Used by: SSE 进度流：先补历史，再实时推，空闲时心跳, Detail-page event stream connects only while work is live and closes on result, Console submission lifecycle: queue, stream, and terminal outcome, Cancellation semantics: stop at a chunk boundary and keep what is done
