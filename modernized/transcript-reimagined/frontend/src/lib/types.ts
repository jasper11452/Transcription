// 后端契约类型（字段名与 tests/web/test_api.py 对齐，别随意改名）

export interface KeyField {
  attr: string
  env: string
  label: string
  status: string
  masked: string
  configured: boolean
}

export interface EngineEntry {
  id: string
  label: string
  needs_key: string[]
  max_chunk_s: number | null
  has_timestamps: boolean
  cost: string
  ready: boolean
}

export interface ConsoleDefaults {
  mode: string
  artifact: string
  language: string
  online_engine: string
}

export interface StatusPayload {
  online_ready: boolean
  online_engines: EngineEntry[]
  credentials: Record<string, string>
  key_fields: KeyField[]
  defaults: ConsoleDefaults
  stats: Record<string, number>
  diar_enabled: boolean
  diar_available: boolean
}

export interface Task {
  id: number
  name: string
  title: string
  source_name: string
  source_path: string
  mode: string
  artifact: string
  status: string
  progress: number
  engine: string | null
  duration_s: number | null
  audio_seconds: number | null
  cost_usd: number | null
  chars: number | null
  out_dir: string | null
  txt_path: string | null
  srt_path: string | null
  raw_path: string | null
  error: string | null
  created_at: string
  is_terminal: boolean
  running: boolean
  interrupted: boolean
  cancelling: boolean
  resumable: boolean
  txt_exists: boolean
  srt_exists: boolean
  src_exists: boolean
}

export interface SubtitleLine {
  start: number
  end: number
  text: string
}

export interface ChunkItem {
  idx: number
  start: number
  end: number
  status: string
  chars: number
  text: string
  segments: SubtitleLine[]
  attempts: number
  error: string | null
}

export interface TaskDetail {
  task: Task
  chunks: ChunkItem[]
  running: boolean
  cancelling: boolean
  resumable: boolean
}

export interface CreateTaskRequest {
  file?: File
  path?: string
  mode: string
  artifact: string
  language: string
  online_engine?: string
}

export interface GlossaryRule {
  wrong: string
  right: string
}

export interface SummarySettingsPayload {
  model: string
  default_model: string
  base_url: string
  default_base_url: string
  api_key_configured: boolean
  api_key_masked: string
  prompt: string
  default_prompt: string
  custom_prompt: boolean
  max_prompt_chars: number
  config_path: string
  prompt_path: string
  hot_words: string[]
  max_hot_words: number
  max_hot_word_chars: number
  glossary_path: string
}

export interface SummaryModel {
  id: string
  name: string
  context_length: number | null
  reasoning: boolean
  price_per_million_prompt: number | null
}

export interface SummaryModelListPayload {
  models: SummaryModel[]
  error: string | null
  cached: boolean
}

export interface SummaryPayload {
  enabled: boolean
  available: boolean
  status: 'disabled' | 'waiting' | 'running' | 'done' | 'failed'
  content: {
    title?: string
    overview: string
    key_points: string[]
    action_items: string[]
    reasoning?: string
  } | null
  error: string | null
  model: string
  partial: { content: string; reasoning: string }
}

export interface Boot {
  status: StatusPayload
  task: TaskDetail | null
  /** 侧栏任务表。跟着 HTML 一起到，省掉进页后那次往返——否则侧栏先画「加载中…」，
      列表一到就整栏换掉；切任务时那两帧坏画面里有一帧就是它。
      可能缺失（旧产物/测试桩），所以可选，缺了就自己拉。 */
  tasks?: Task[]
}

declare global {
  interface Window {
    __BOOT__?: Boot
  }
}

export function boot(): Boot {
  return (
    window.__BOOT__ ?? {
      status: {
        online_ready: false,
        online_engines: [],
        credentials: {},
        key_fields: [],
        defaults: { mode: 'offline', artifact: 'srt', language: 'zh', online_engine: 'auto' },
        stats: {},
        diar_enabled: false,
        diar_available: true,
      },
      task: null,
    }
  )
}
