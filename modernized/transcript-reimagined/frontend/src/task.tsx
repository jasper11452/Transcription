// 任务详情页（/t/{id}）：字幕、文稿与总结共用一个标签内容面板。SSE 推送已完成分片。

import { type AnimationEvent as ReactAnimationEvent, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  AlertCircle,
  Brain,
  Check,
  ChevronDown,
  Clipboard,
  Download,
  FileText,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Settings2,
  Sparkles,
  StopCircle,
  Subtitles,
  X,
} from 'lucide-react'
import '@/index.css'
import { Button } from '@/components/ui/button'
import { HistorySidebar } from '@/components/history-sidebar'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger, TabUnderline } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { boot, type ChunkItem, type SubtitleLine, type SummaryModel, type SummaryPayload, type SummarySettingsPayload, type TaskDetail } from '@/lib/types'
import { hasPartialContent, parsePartialSummary, type PartialSummary } from '@/lib/summary-stream'
import {
  cancelTask,
  enableSummary,
  fetchOutput,
  fetchSummary,
  fetchSummaryModels,
  fetchSummarySettings,
  fetchTaskDetail,
  resumeTask,
  revealPath,
  saveSummarySettings,
} from '@/lib/api'

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '转录中',
  done: '已完成',
  failed: '失败',
}

function fmtTime(seconds: number): string {
  const safe = Math.max(0, Number(seconds) || 0)
  const hours = Math.floor(safe / 3600)
  const minutes = Math.floor((safe % 3600) / 60)
  const secs = Math.floor(safe % 60)
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

function parseSrt(raw: string): SubtitleLine[] {
  const normalized = raw.replace(/^\uFEFF/, '').replace(/\r/g, '')
  return normalized
    .split(/\n\s*\n/)
    .flatMap((block) => {
      const lines = block.trim().split('\n')
      const timeLineIndex = lines.findIndex((line) => line.includes('-->'))
      if (timeLineIndex < 0) return []
      const [start, end] = lines[timeLineIndex].split('-->').map((part) => parseSrtTime(part.trim()))
      const text = lines.slice(timeLineIndex + 1).filter((line) => !line.startsWith('#')).join(' ').trim()
      return text && Number.isFinite(start) && Number.isFinite(end) ? [{ start, end, text }] : []
    })
}

function parseSrtTime(value: string): number {
  const match = value.match(/^(\d+):(\d{2}):(\d{2})[,.](\d{3})$/)
  if (!match) return Number.NaN
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000
}

function srtToPlainText(raw: string): string {
  return parseSrt(raw).map((line) => line.text).join('\n')
}

function fallbackLines(chunks: ChunkItem[]): SubtitleLine[] {
  return chunks
    .filter((chunk) => chunk.status === 'done' && chunk.text.trim())
    .flatMap((chunk) => {
      if (chunk.segments.length) return chunk.segments
      return [{ start: chunk.start, end: chunk.end, text: chunk.text.trim() }]
    })
    .sort((a, b) => a.start - b.start)
}

function mergeChunkLines(chunks: ChunkItem[]): SubtitleLine[] {
  return chunks
    .filter((chunk) => chunk.status === 'done')
    .flatMap((chunk) => chunk.segments.length
      ? chunk.segments
      : chunk.text.trim() ? [{ start: chunk.start, end: chunk.end, text: chunk.text.trim() }] : [])
    .sort((a, b) => a.start - b.start)
}

// Q4：同一片同时带 segments 与 text 时，以 segments 为准；text 只在没有
// 结构化时间轴时使用。不要两处各取一份，否则同一段正文会出现/消失取决于走哪条路径。
function chunkTexts(chunks: ChunkItem[]): string[] {
  return chunks
    .filter((chunk) => chunk.status === 'done')
    .flatMap((chunk) =>
      chunk.segments.length
        ? chunk.segments.map((line) => line.text.trim()).filter(Boolean)
        : chunk.text.trim()
          ? [chunk.text.trim()]
          : [],
    )
}

interface SseEvent {
  type?: string
  stage?: string
  message?: string
  current?: number
  total?: number
  chunk?: ChunkItem
}

function StatusMark({ busy, failed, done }: { busy: boolean; failed: boolean; done: boolean }) {
  return (
    <span
      className={cn(
        'relative inline-flex h-2 w-2 shrink-0 rounded-full',
        done && 'bg-ink',
        failed && 'bg-destructive',
        busy && 'bg-sunset',
        !busy && !failed && !done && 'bg-mute',
      )}
      aria-hidden="true"
    >
      {busy && <span className="status-ping absolute inset-0 rounded-full bg-sunset" />}
    </span>
  )
}

function SubtitleLineRow({ line, live, newest }: { line: SubtitleLine; live?: boolean; newest?: boolean }) {
  return (
    <div className={cn('subtitle-line group', live && 'subtitle-line-live', newest && 'subtitle-line-current')}>
      <span className="subtitle-time font-mono">{fmtTime(line.start)}</span>
      <p className="min-w-0 flex-1 whitespace-pre-wrap text-[15px] leading-7 text-body">{line.text}</p>
      {newest && <span className="subtitle-cursor" aria-hidden="true" />}
    </div>
  )
}

function SubtitlePanel({
  task,
  chunks,
  lastMessage,
  follow,
  setFollow,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
  follow: boolean
  setFollow: (value: boolean) => void
}) {
  const [fileLines, setFileLines] = useState<SubtitleLine[]>([])
  const [fileError, setFileError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    setFileError('')
    if (task.running || task.status !== 'done' || !task.srt_exists) {
      setFileLines([])
      return () => { active = false }
    }
    fetchOutput(task.id, 'srt').then((raw) => {
      if (active) setFileLines(parseSrt(raw))
    }).catch((error) => {
      if (active) setFileError(error instanceof Error ? error.message : String(error))
    })
    return () => { active = false }
  }, [task.id, task.running, task.srt_exists, task.status])

  const liveLines = useMemo(() => mergeChunkLines(chunks), [chunks])
  const lines = fileLines.length ? fileLines : liveLines.length ? liveLines : fallbackLines(chunks)
  const latestKey = lines.length ? String(lines[lines.length - 1].start) + '-' + lines[lines.length - 1].text : ''

  useEffect(() => {
    if (!follow || !scrollRef.current) return
    const container = scrollRef.current
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    container.scrollTo({ top: container.scrollHeight, behavior })
  }, [follow, latestKey])

  const isLive = task.running
  const hasLines = lines.length > 0
  const timed = task.srt_exists || task.artifact === 'srt'
  const formatLabel = timed ? 'SRT · TIMED' : 'TEXT · CHUNK'

  return (
    <>
      <div
        ref={scrollRef}
        className="subtitle-scroll px-4 py-3 sm:px-6 sm:py-4"
        aria-live="polite"
        onWheel={(event) => { if (event.deltaY < 0) setFollow(false) }}
        onTouchMove={() => setFollow(false)}
      >
        {hasLines ? (
          <div className="space-y-0.5">
            {lines.map((line, index) => (
              <SubtitleLineRow
                key={String(line.start) + '-' + index + '-' + line.text}
                line={line}
                live={isLive && index === lines.length - 1}
                newest={isLive && index === lines.length - 1}
              />
            ))}
            {isLive && (
              <div className="subtitle-pending-row">
                <span className="subtitle-time font-mono">{fmtTime(lines[lines.length - 1].end)}</span>
                <span className="inline-flex items-center gap-2 text-sm text-mute">
                  <LoaderCircle size={14} className="animate-spin" /> 正在识别下一段…
                </span>
              </div>
            )}
          </div>
        ) : isLive ? (
          <div className="flex min-h-[290px] flex-col items-center justify-center gap-4 text-center">
            <div className="live-orbit"><span /><span /><span /></div>
            <div>
              <p className="text-sm text-body">正在准备第一段字幕</p>
              <p className="mt-1 text-xs text-mute">音频切片完成后，字幕会在这里实时出现</p>
            </div>
          </div>
        ) : (
          <div className="flex min-h-[220px] flex-col items-center justify-center text-center">
            <Subtitles size={24} className="text-mute" strokeWidth={1.4} />
            <p className="mt-3 text-sm text-body">暂时没有可显示的字幕</p>
            <p className="mt-1 text-xs text-mute">完成转录后，带时间码的字幕会出现在这里</p>
          </div>
        )}
      </div>
      <div className="flex min-h-11 items-center justify-between gap-3 border-t border-hairline bg-canvas-soft/40 px-5 py-3 sm:px-6">
        <p className="truncate text-xs text-mute" role="status">
          {isLive ? (lastMessage || formatLabel) : fileError || formatLabel + ' · ' + lines.length + (timed ? ' 条字幕' : ' 个片段')}
        </p>
        {isLive && <span className="live-label"><span /> LIVE</span>}
      </div>
    </>
  )
}

function TranscriptPanel({
  task,
  chunks,
  lastMessage,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
}) {
  const [fileText, setFileText] = useState('')
  const [fileError, setFileError] = useState('')

  useEffect(() => {
    let active = true
    setFileText('')
    setFileError('')
    if (task.running || task.status !== 'done' || !task.txt_exists) {
      return () => { active = false }
    }
    fetchOutput(task.id, 'txt').then((text) => {
      if (active) setFileText(text)
    }).catch((error) => {
      if (active) setFileError(error instanceof Error ? error.message : String(error))
    })
    return () => { active = false }
  }, [task.id, task.running, task.status, task.txt_exists])

  const chunkText = chunkTexts(chunks).join('\n')
  const text = fileText || chunkText
  const isLive = task.running

  return (
    <>
      <div className="subtitle-scroll px-5 py-4 sm:px-7 sm:py-5" aria-live="polite">
        {text ? (
          <pre className="min-h-[260px] whitespace-pre-wrap break-words font-sans text-[15px] leading-7 text-body">{text}</pre>
        ) : isLive ? (
          <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-center">
            <LoaderCircle size={18} className="animate-spin text-mute" />
            <p className="text-sm text-body">正在整理文稿</p>
            <p className="text-xs text-mute">已完成分片会先显示在这里</p>
          </div>
        ) : (
          <div className="flex min-h-[220px] flex-col items-center justify-center text-center">
            <FileText size={24} className="text-mute" strokeWidth={1.4} />
            <p className="mt-3 text-sm text-body">暂时没有可显示的文稿</p>
            <p className="mt-1 text-xs text-mute">{fileError || '转录完成后，TXT 文稿会出现在这里'}</p>
          </div>
        )}
      </div>
      <div className="flex min-h-11 items-center justify-between gap-3 border-t border-hairline bg-canvas-soft/40 px-5 py-3 sm:px-6">
        <p className="truncate text-xs text-mute" role="status">
          {isLive ? (lastMessage || '正在转录…') : fileError || String(text.length.toLocaleString('zh-CN')) + ' 个字符'}
        </p>
        {isLive && <span className="live-label"><span /> LIVE</span>}
      </div>
    </>
  )
}

function SummarySettingsEditor() {
  const [settings, setSettings] = useState<SummarySettingsPayload | null>(null)
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [hotWords, setHotWords] = useState<string[]>([])
  const [hotWordDraft, setHotWordDraft] = useState('')
  const [models, setModels] = useState<SummaryModel[] | null>(null)
  const [modelListError, setModelListError] = useState('')
  const [loadingModels, setLoadingModels] = useState(false)
  const [listOpen, setListOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const comboRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    fetchSummarySettings().then((next) => {
      if (!active) return
      setSettings(next)
      setModel(next.model)
      setBaseUrl(next.base_url)
      setPrompt(next.prompt)
      setHotWords(next.hot_words)
      setError('')
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : String(err))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  const connectionDirty = baseUrl.trim().replace(/\/+$/, '') !== settings?.base_url || !!apiKey.trim()

  const loadModels = useCallback(async (refresh = false) => {
    if (connectionDirty) {
      setModelListError('连接设置有未保存的修改。请先保存，再获取该服务的模型列表；也可直接手填模型 ID。')
      return
    }
    setLoadingModels(true)
    try {
      const payload = await fetchSummaryModels(refresh)
      setModels(payload.models)
      setModelListError(payload.error ?? '')
    } catch (err) {
      setModels([])
      setModelListError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingModels(false)
    }
  }, [connectionDirty])

  const toggleList = useCallback(() => {
    setListOpen((open) => {
      // 箭头打开时展示全量清单；过滤词只在打字时生效。
      if (!open) {
        setQuery('')
        if (models === null) void loadModels()
      }
      return !open
    })
    setHighlight(0)
  }, [loadModels, models])

  useEffect(() => {
    if (!listOpen) return
    const onDown = (event: MouseEvent) => {
      if (comboRef.current && !comboRef.current.contains(event.target as Node)) setListOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [listOpen])

  const filteredModels = useMemo(() => {
    const all = models ?? []
    const needle = query.trim().toLowerCase()
    return needle
      ? all.filter(
          (item) =>
            item.id.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
        )
      : all
  }, [models, query])

  // Q2：先计数再截断 —— 60 条只是渲染上限，匹配总数必须可见，否则用户以为
  // 搜索没结果。继续输入会缩小范围，被截掉的位置是可发现的。
  const visibleModels = useMemo(() => filteredModels.slice(0, 60), [filteredModels])

  const pickModel = (id: string) => {
    setModel(id)
    setQuery('')
    setListOpen(false)
    setMessage('')
    setError('')
  }

  const onModelKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!listOpen) toggleList()
      else setHighlight((index) => Math.min(index + 1, Math.max(visibleModels.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && listOpen && visibleModels[highlight]) {
      event.preventDefault()
      pickModel(visibleModels[highlight].id)
    } else if (event.key === 'Escape') {
      setListOpen(false)
    }
  }

  const commitHotWords = (raw: string, limit = settings?.max_hot_words ?? 80) => {
    const parts = raw.split(/[,，、\s]+/).map((part) => part.trim()).filter(Boolean)
    if (!parts.length) return
    const maxChars = settings?.max_hot_word_chars ?? 40
    setHotWords((current) => {
      const next = [...current]
      for (const part of parts) {
        const value = part.slice(0, maxChars)
        if (value && !next.includes(value) && next.length < limit) next.push(value)
      }
      return next
    })
    setHotWordDraft('')
  }

  const removeHotWord = (word: string) => {
    setHotWords((current) => current.filter((item) => item !== word))
  }

  const restoreDefaults = () => {
    if (!settings) return
    setModel(settings.default_model)
    setBaseUrl(settings.default_base_url)
    setPrompt(settings.default_prompt)
    setMessage('已载入默认值，点击保存后生效。')
    setError('')
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const next = await saveSummarySettings({ model, base_url: baseUrl, api_key: apiKey, prompt, hot_words: hotWords })
      setSettings(next)
      setModel(next.model)
      setBaseUrl(next.base_url)
      setPrompt(next.prompt)
      setHotWords(next.hot_words)
      setApiKey('')
      setModels(null)
      setModelListError('')
      setListOpen(false)
      setMessage('已保存。')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="模型设置" className="p-5 sm:p-6">
      <div className="space-y-4">
        {loading && <p className="text-xs text-mute">正在读取本机设置…</p>}
        {settings && (
          <form className="space-y-4" onSubmit={save}>
            <div className="space-y-2">
              <label htmlFor="summaryBaseUrl" className="eyebrow-mono">Base URL</label>
              <Input
                id="summaryBaseUrl"
                type="url"
                value={baseUrl}
                onChange={(event) => { setBaseUrl(event.target.value); setModels(null); setListOpen(false) }}
                maxLength={500}
                placeholder="https://api.example.com/v1"
                autoComplete="off"
                spellCheck={false}
                required
              />
              <p className="text-xs leading-5 text-mute">OpenAI 兼容地址，与在线转录共用。请求会携带密钥，请使用可信服务。</p>
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="summaryApiKey" className="eyebrow-mono">API Key</label>
                <span className="text-xs text-mute">{settings.api_key_configured ? `已配置 ${settings.api_key_masked}` : '未配置'}</span>
              </div>
              <Input
                id="summaryApiKey"
                type="password"
                value={apiKey}
                onChange={(event) => { setApiKey(event.target.value); setModels(null); setListOpen(false) }}
                maxLength={512}
                autoComplete="new-password"
                spellCheck={false}
                placeholder={settings.api_key_configured ? '粘贴新密钥以替换；留空保留原密钥' : '粘贴此服务的 API Key'}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="summaryModel" className="eyebrow-mono">模型 ID</label>
              <div className="relative" ref={comboRef}>
                <Input
                  id="summaryModel"
                  value={model}
                  onChange={(event) => { setModel(event.target.value); setQuery(event.target.value); setHighlight(0); if (!listOpen) setListOpen(true) }}
                  onKeyDown={onModelKeyDown}
                  maxLength={200}
                  placeholder={settings.default_model}
                  autoComplete="off"
                  required
                  role="combobox"
                  aria-expanded={listOpen}
                  aria-controls="summaryModelList"
                  className="pr-11"
                />
                <button
                  type="button"
                  onClick={toggleList}
                  aria-label={listOpen ? '收起模型列表' : '展开模型列表'}
                  className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-md text-mute transition-colors hover:bg-surface-hover hover:text-ink"
                >
                  <ChevronDown size={15} className={cn('transition-transform', listOpen && 'rotate-180')} />
                </button>
                {listOpen && (
                  <div className="model-menu absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-lg border border-hairline bg-popover">
                    <div className="flex items-center justify-between gap-3 border-b border-hairline px-3 py-2">
                      <span className="font-mono text-[10px] text-mute">
                        {loadingModels ? '读取中…' : models === null ? '模型清单' : query.trim() ? `${filteredModels.length} 个匹配（显示 ${visibleModels.length}）` : `${models.length} 个模型`}
                      </span>
                      <button
                        type="button"
                        onClick={() => void loadModels(true)}
                        disabled={loadingModels}
                        className="font-mono text-[10px] text-mute transition-colors hover:text-ink disabled:opacity-50"
                      >
                        刷新
                      </button>
                    </div>
                    <div id="summaryModelList" role="listbox" className="max-h-64 overflow-y-auto">
                      {visibleModels.map((item, index) => (
                        <button
                          type="button"
                          key={item.id}
                          role="option"
                          aria-selected={item.id === model}
                          onMouseEnter={() => setHighlight(index)}
                          onClick={() => pickModel(item.id)}
                          className={cn(
                            'flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors',
                            index === highlight && 'bg-surface-selected',
                          )}
                        >
                          <span className="truncate font-mono text-[11px] text-body">{item.id}</span>
                          <span className="truncate text-[11px] text-mute">
                            {item.name}
                            {item.reasoning ? ' · 支持思考' : ''}
                            {item.context_length ? ` · ${Math.round(item.context_length / 1000)}k 上下文` : ''}
                            {item.price_per_million_prompt ? ` · $${item.price_per_million_prompt.toFixed(3)}/M` : ''}
                          </span>
                        </button>
                      ))}
                      {!loadingModels && models !== null && !filteredModels.length && (
                        <p className="px-3 py-3 text-[11px] text-mute">
                          {models.length ? '没有匹配的模型，仍可直接使用输入的内容。' : '暂无可选清单，直接输入模型 ID 即可。'}
                        </p>
                      )}
                      {filteredModels.length > visibleModels.length && (
                        <p className="border-t border-hairline px-3 py-2 text-[11px] text-mute">
                          仅显示前 {visibleModels.length} 个匹配（共 {filteredModels.length} 个），继续输入以缩小范围。
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <p className="text-xs leading-5 text-mute">
                可手填，或保存连接后从下拉列表选择。
              </p>
              {modelListError && <p className="text-xs leading-5 text-mute">{modelListError}</p>}
            </div>
            <div className="space-y-2">
              <label htmlFor="summaryPrompt" className="eyebrow-mono">总结提示词</label>
              <Textarea
                id="summaryPrompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                maxLength={settings.max_prompt_chars}
                rows={4}
                className="resize-y font-mono text-xs leading-5"
                placeholder="说明你希望总结重点、语气或格式…"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="summaryHotWords" className="eyebrow-mono">热词</label>
              <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-hairline bg-canvas-soft p-2">
                {hotWords.map((word) => (
                  <span
                    key={word}
                    className="inline-flex items-center gap-1 rounded-md bg-surface-selected px-2 py-1 font-mono text-[11px] text-body"
                  >
                    {word}
                    <button
                      type="button"
                      onClick={() => removeHotWord(word)}
                      aria-label={`移除热词 ${word}`}
                      className="text-mute transition-colors hover:text-ink"
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
                <input
                  id="summaryHotWords"
                  value={hotWordDraft}
                  onChange={(event) => setHotWordDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ',' || event.key === '，' || event.key === '、') {
                      event.preventDefault()
                      commitHotWords(hotWordDraft)
                    } else if (event.key === 'Backspace' && !hotWordDraft && hotWords.length) {
                      removeHotWord(hotWords[hotWords.length - 1])
                    }
                  }}
                  onBlur={() => commitHotWords(hotWordDraft)}
                  maxLength={(settings.max_hot_word_chars ?? 40) + 2}
                  placeholder={hotWords.length ? '' : '输入后回车，例如：小新'}
                  autoComplete="off"
                  className="h-7 min-w-[8rem] flex-1 bg-transparent px-1 text-sm text-foreground placeholder:text-mute focus:outline-none"
                />
              </div>
              <p className="text-xs leading-5 text-mute">
                逗号或回车分隔，最多 {settings.max_hot_words} 个。
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" size="sm" disabled={saving || loading || !model.trim() || !baseUrl.trim()}>
                {saving && <LoaderCircle size={14} className="mr-2 animate-spin" />}
                {saving ? '保存中…' : '保存设置'}
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={restoreDefaults} disabled={saving}>
                恢复默认值
              </Button>
            </div>
            <p className="text-xs text-mute">仅保存到本机，不会发起总结。</p>
          </form>
        )}
        {message && <p role="status" className="text-xs text-mute">{message}</p>}
        {error && <p role="alert" className="text-xs leading-5 text-destructive">{error}</p>}
      </div>
    </section>
  )
}

function ThinkingDetails({ text, live = false }: { text: string; live?: boolean }) {
  if (!text.trim()) return null
  return (
    <details className="summary-thinking">
      <summary className="summary-thinking-head">
        <span className="inline-flex items-center gap-2">
          <Brain size={13} className={live ? 'animate-pulse' : ''} />
          思考过程
        </span>
        <span className="font-mono text-[10px] text-mute">
          {live ? '进行中' : `${text.length.toLocaleString('zh-CN')} 字`}
        </span>
      </summary>
      <pre className="summary-thinking-body">{text}</pre>
    </details>
  )
}

function LiveSummary({ partial }: { partial: PartialSummary }) {
  return (
    <div className="space-y-5 summary-content">
      {partial.overview && (
        <div>
          <p className="eyebrow-mono">OVERVIEW</p>
          <p className="mt-2 text-sm leading-6 text-body">
            {partial.overview}
            {partial.titleComplete && !partial.overviewComplete && <span className="summary-caret" />}
          </p>
        </div>
      )}
      {!!partial.keyPoints.length && (
        <div>
          <p className="eyebrow-mono">KEY POINTS</p>
          <ul className="mt-2 space-y-2">
            {partial.keyPoints.map((point, index) => (
              <li key={`${index}-${point}`} className="summary-bullet">{point}</li>
            ))}
          </ul>
        </div>
      )}
      {!!partial.actionItems.length && (
        <div>
          <p className="eyebrow-mono">ACTION ITEMS</p>
          <ul className="mt-2 space-y-2">
            {partial.actionItems.map((item, index) => (
              <li key={`${index}-${item}`} className="summary-bullet summary-action">{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function SummaryPanel({ task, onSettings }: { task: TaskDetail['task']; onSettings: () => void }) {
  const [summary, setSummary] = useState<SummaryPayload | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSummary(task.id)
      setSummary(next)
      if (next.status === 'done') window.dispatchEvent(new Event('task-title-updated'))
      setError('')
      return next
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return null
    }
  }, [task.id])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!summary || !['waiting', 'running'].includes(summary.status)) return
    const timer = window.setInterval(() => { void refresh() }, 700)
    return () => window.clearInterval(timer)
  }, [refresh, summary?.status])

  const start = async () => {
    setWorking(true)
    setError('')
    try {
      setSummary(await enableSummary(task.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setWorking(false)
    }
  }

  const status = summary?.status ?? 'disabled'
  const content = summary?.content
  const unavailable = summary && !summary.available
  const partialRaw = summary?.partial?.content ?? ''
  const live = useMemo(() => parsePartialSummary(partialRaw), [partialRaw])
  const streaming = hasPartialContent(live)
  const thinking = (summary?.partial?.reasoning ?? '').trim().length > 0

  return (
    <div className="min-h-[340px] px-5 py-5 sm:px-6">
      {status === 'running' ? (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <p className="text-sm text-body">Agent 正在整理字幕…</p>
            <span className="font-mono text-[10px] text-mute">{streaming ? '流式生成中' : thinking ? '思考中' : '等待首个片段'}</span>
          </div>
          {!streaming && (
            <div className="summary-waiting">
              <div className="summary-shimmer" />
              <p className="text-xs text-mute">正在读取转录…</p>
            </div>
          )}
          {streaming && <LiveSummary partial={live} />}
          <ThinkingDetails text={summary?.partial?.reasoning ?? ''} live />
          <p className="text-xs text-mute">这不会影响转录任务</p>
        </div>
      ) : status === 'waiting' ? (
        <div className="space-y-3">
          <p className="text-sm leading-6 text-body">已开启。转录完成后会自动生成项目标题、主旨、要点和待办。</p>
          <p className="text-xs text-mute">{task.status === 'done' ? 'Agent 会在后台完成整理。' : '当前转录完成后，Agent 会自动开始整理。'}</p>
        </div>
      ) : status === 'done' && content ? (
        <div className="space-y-6 summary-content">
          <div>
            <p className="eyebrow-mono">OVERVIEW</p>
            <p className="mt-2 text-sm leading-6 text-body">{content.overview}</p>
          </div>
          {!!content.key_points.length && (
            <div>
              <p className="eyebrow-mono">KEY POINTS</p>
              <ul className="mt-2 space-y-2">
                {content.key_points.map((point) => <li key={point} className="summary-bullet">{point}</li>)}
              </ul>
            </div>
          )}
          {!!content.action_items.length && (
            <div>
              <p className="eyebrow-mono">ACTION ITEMS</p>
              <ul className="mt-2 space-y-2">
                {content.action_items.map((item) => <li key={item} className="summary-bullet summary-action">{item}</li>)}
              </ul>
            </div>
          )}
          <ThinkingDetails text={content.reasoning ?? ''} />
          <button type="button" className="summary-retry" onClick={start} disabled={working}>
            <RefreshCw size={13} className={working ? 'animate-spin' : ''} /> 重新生成
          </button>
        </div>
      ) : unavailable ? (
        <div className="space-y-3">
          <p className="text-sm leading-6 text-body">先配置模型连接，再开启总结。</p>
          <Button type="button" size="sm" variant="outline" onClick={onSettings}>去设置</Button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-6 text-body">让 Agent 根据转录内容生成项目标题、主旨、要点和待办。</p>
          <p className="text-xs leading-5 text-mute">启用后会把转录文字、当前提示词和 API 密钥发送到配置的 Base URL，不上传音频。</p>
          <Button type="button" size="sm" onClick={start} disabled={working}>
            {working ? <LoaderCircle size={14} className="mr-2 animate-spin" /> : <Sparkles size={14} className="mr-2" />}
            开启自动总结
          </Button>
        </div>
      )}
      {status === 'failed' && (
        <div className="mt-4 space-y-2">
          <p role="alert" className="text-xs leading-5 text-destructive">{summary?.error || '总结未完成。'}</p>
          <Button type="button" variant="outline" size="sm" onClick={start} disabled={working}>重试总结</Button>
        </div>
      )}
      {error && !summary?.error && <p role="alert" className="mt-4 text-xs leading-5 text-destructive">{error}</p>}
    </div>
  )
}

function ResultTabs({
  task,
  chunks,
  lastMessage,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
}) {
  const defaultTab = task.artifact === 'txt' && !task.srt_exists ? 'transcript' : 'subtitle'
  const [activeTab, setActiveTab] = useState(defaultTab)
  const [follow, setFollow] = useState(task.running)
  const [shown, setShown] = useState<string[]>([defaultTab])
  const listRef = useRef<HTMLDivElement>(null)

  // 露过一次就不再播入场：切回来是同一份内容，重播等于每次切标签都暗一下；
  // 首屏那个标签从一上就在，也不能播——骨架刚换掉就再入场一次，等于多闪一下。
  const arrived = (value: string) => ({
    'data-shown': shown.includes(value) ? '' : undefined,
    onAnimationEnd: (e: ReactAnimationEvent<HTMLDivElement>) => {
      if (e.animationName !== 'swap-arrive' || e.target !== e.currentTarget) return
      setShown((prev) => (prev.includes(value) ? prev : [...prev, value]))
    },
  })

  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => setActiveTab(value as 'subtitle' | 'transcript' | 'summary' | 'settings')}
      className="workbench-card overflow-hidden"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-3 sm:px-5">
        {/* 四个标签的选中下划线由一条共享的线滑动承担，各标签自己只留 2px 透明边框占高度 */}
        <TabsList ref={listRef} aria-label="转录内容视图" className="h-auto justify-start rounded-none bg-transparent p-0">
          <TabUnderline listRef={listRef} value={activeTab} />
          <TabsTrigger value="subtitle" className="min-h-12 gap-2 rounded-none border-b-2 border-transparent px-3 text-xs text-mute data-[state=active]:bg-transparent data-[state=active]:text-ink sm:px-4">
            <Subtitles size={15} /> 字幕
          </TabsTrigger>
          <TabsTrigger value="transcript" className="min-h-12 gap-2 rounded-none border-b-2 border-transparent px-3 text-xs text-mute data-[state=active]:bg-transparent data-[state=active]:text-ink sm:px-4">
            <FileText size={15} /> 文稿
          </TabsTrigger>
          <TabsTrigger value="summary" className="min-h-12 gap-2 rounded-none border-b-2 border-transparent px-3 text-xs text-mute data-[state=active]:bg-transparent data-[state=active]:text-ink sm:px-4">
            <Sparkles size={15} /> 总结
          </TabsTrigger>
          <TabsTrigger value="settings" className="min-h-12 gap-2 rounded-none border-b-2 border-transparent px-3 text-xs text-mute data-[state=active]:bg-transparent data-[state=active]:text-ink sm:px-4">
            <Settings2 size={15} /> 设置
          </TabsTrigger>
        </TabsList>
        {activeTab === 'subtitle' && (
          <button
            type="button"
            className="follow-toggle"
            aria-pressed={follow}
            onClick={() => setFollow((value) => !value)}
          >
            <span className={cn('follow-dot', follow && 'follow-dot-on')} />
            {follow ? '跟随最新' : '已暂停跟随'}
          </button>
        )}
      </div>
      <TabsContent value="subtitle" className="result-tab-content mt-0 outline-none" {...arrived('subtitle')}>
        <SubtitlePanel task={task} chunks={chunks} lastMessage={lastMessage} follow={follow} setFollow={setFollow} />
      </TabsContent>
      <TabsContent value="transcript" className="result-tab-content mt-0 outline-none" {...arrived('transcript')}>
        <TranscriptPanel task={task} chunks={chunks} lastMessage={lastMessage} />
      </TabsContent>
      <TabsContent value="summary" className="result-tab-content mt-0 outline-none" {...arrived('summary')}>
        <SummaryPanel task={task} onSettings={() => setActiveTab('settings')} />
      </TabsContent>
      <TabsContent value="settings" className="result-tab-content mt-0 outline-none" {...arrived('settings')}>
        <SummarySettingsEditor />
      </TabsContent>
    </Tabs>
  )
}

function ResumeButton({ task, onResume }: { task: TaskDetail['task']; onResume: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const costs = task.mode === 'online'
  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(false), 4000)
    return () => window.clearTimeout(timer)
  }, [confirming])
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant={confirming ? 'destructive' : 'default'}
        onClick={() => (costs && !confirming ? setConfirming(true) : onResume())}
      >
        {confirming ? '确认续跑' : '继续未完成的分段'}
      </Button>
      {confirming && <p role="status" className="text-xs text-mute">在线续跑会重新上传音频并按量计费。</p>}
    </div>
  )
}

function ProgressCard({
  detail,
  totalOverride,
  onCancel,
}: {
  detail: TaskDetail
  totalOverride: number
  onCancel: () => void
}) {
  const t = detail.task
  const busy = t.running || t.cancelling
  const failed = t.status === 'failed' || t.interrupted
  const done = t.status === 'done'
  const total = Math.max(totalOverride, detail.chunks.length)
  const doneCount = detail.chunks.filter((chunk) => chunk.status === 'done').length
  const pct = Math.min(100, Math.max(0, Math.round(t.progress)))
  const outcome = t.cancelling ? '停止中' : failed ? '已中断' : STATUS_LABEL[t.status] ?? t.status

  return (
    <section className="workbench-card p-5 sm:p-6" aria-labelledby="progressTitle">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <StatusMark busy={busy} failed={failed} done={done} />
          <h2 id="progressTitle" className="text-sm text-body">{outcome}</h2>
        </div>
        <span className="eyebrow-mono">{t.mode === 'online' ? 'ONLINE' : 'OFFLINE'}</span>
      </div>
      <div className="mt-6 flex items-end gap-2">
        <span className="font-mono text-4xl leading-none tracking-tight text-ink">{pct}</span>
        <span className="pb-0.5 font-mono text-sm text-mute">%</span>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-canvas-soft" aria-label={`已完成 ${pct}%`} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        {/* 用 transform 推进，不用 width：width 每帧都要重新布局，而进度是随时间连续跳动的。
            500ms 也让进度条严重滞后于真实进度，改成 200ms。 */}
        <div
          className={cn('h-full w-full origin-left rounded-full transition-transform duration-200 ease-out', failed ? 'bg-destructive' : 'bg-sunset')}
          style={{ transform: `scaleX(${pct / 100})` }}
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-mute">
        <span>{total ? `${doneCount} / ${total} 个音频片段` : '正在分析音频…'}</span>
        {t.duration_s ? <span className="font-mono">{fmtTime(t.duration_s)}</span> : null}
      </div>
      {busy && (
        <Button type="button" variant="outline" className="mt-6 w-full" onClick={onCancel}>
          <StopCircle size={15} className="mr-2" /> 停止转录
        </Button>
      )}
      {t.error && failed && <p className="mt-4 text-xs leading-5 text-destructive [overflow-wrap:anywhere]">{t.error}</p>}
    </section>
  )
}

function FilesCard({ task, content, onCopy, copyState, onReveal }: {
  task: TaskDetail['task']
  content: string
  onCopy: () => void
  copyState: 'idle' | 'copying' | 'copied'
  onReveal: () => void
}) {
  return (
    <section className="workbench-card p-5 sm:p-6" aria-labelledby="filesTitle">
      <div className="flex items-center justify-between gap-3">
        <h2 id="filesTitle" className="text-sm text-body">导出</h2>
        <FileText size={16} className="text-mute" />
      </div>
      <div className="mt-4 space-y-2">
        {task.srt_exists ? (
          <a className="file-action file-action-primary" href={`/api/tasks/${task.id}/output/file?kind=srt&download=true`}>
            <Subtitles size={15} /> 下载字幕 <Download size={13} className="ml-auto opacity-60" />
          </a>
        ) : (
          <div className="file-action file-action-disabled"><Subtitles size={15} /> 字幕尚未生成</div>
        )}
        {task.txt_exists && (
          <a className="file-action" href={`/api/tasks/${task.id}/output/file?kind=txt&download=true`}>
            <FileText size={15} /> 下载文稿 <Download size={13} className="ml-auto opacity-60" />
          </a>
        )}
        {content && (
          <button type="button" className="file-action" disabled={copyState === 'copying'} onClick={onCopy}>
            {copyState === 'copied' ? <Check size={15} /> : <Clipboard size={15} />}
            {copyState === 'copying' ? '复制中…' : copyState === 'copied' ? '已复制转录文本' : '复制转录文本'}
          </button>
        )}
      </div>
      {task.out_dir && <button type="button" className="mt-4 inline-flex items-center gap-2 text-xs text-mute underline-offset-4 hover:text-ink hover:underline" onClick={onReveal}><FolderOpen size={13} /> 在访达中显示</button>}
    </section>
  )
}

function Detail({ initial, animate }: { initial: TaskDetail; animate: boolean }) {
  const [detail, setDetail] = useState<TaskDetail>(initial)
  const [streamTotal, setStreamTotal] = useState(initial.chunks.length)
  const [lastMessage, setLastMessage] = useState('')
  const [showPaths, setShowPaths] = useState(false)
  const [subtitleContent, setSubtitleContent] = useState('')
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied'>('idle')

  useEffect(() => {
    const update = () => {
      if (detail) void fetchTaskDetail(detail.task.id).then(setDetail).catch(console.error)
    }
    window.addEventListener('task-title-updated', update)
    return () => window.removeEventListener('task-title-updated', update)
  }, [detail?.task.id])

  const refresh = useCallback(async (id: number) => {
    try {
      setDetail(await fetchTaskDetail(id))
    } catch {
      // 任务已删：保持页面当前状态。
    }
  }, [])

  useEffect(() => {
    let active = true
    if (detail.running || detail.task.running || detail.task.status !== 'done' || !detail.task.srt_exists) {
      setSubtitleContent('')
      return () => { active = false }
    }
    fetchOutput(detail.task.id, 'srt').then((text) => {
      if (active) setSubtitleContent(srtToPlainText(text))
    }).catch(() => {
      if (active) setSubtitleContent('')
    })
    return () => { active = false }
  }, [detail.task.id, detail.running, detail.task.running, detail.task.srt_exists, detail.task.status])

  useEffect(() => {
    const id = detail.task.id
    if (!detail.running && !detail.cancelling) return
    const es = new EventSource(`/api/tasks/${id}/events`)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as SseEvent
        if (data.type === 'result' || data.type === 'close') {
          es.close()
          void refresh(id)
          return
        }
        if (data.type !== 'progress') return
        setLastMessage(data.message || '')
        if (data.total) setStreamTotal((current) => Math.max(current, data.total ?? 0))
        if (data.stage === 'plan') void refresh(id)
        setDetail((current) => {
          const next = { ...current, running: true, task: { ...current.task, status: 'running', running: true } }
          if (data.total) {
            next.task.progress = Math.round(((data.current ?? 0) / data.total) * 100)
          }
          if (data.chunk) {
            const existing = next.chunks.findIndex((chunk) => chunk.idx === data.chunk?.idx)
            next.chunks = existing >= 0
              ? next.chunks.map((chunk, index) => index === existing ? data.chunk as ChunkItem : chunk)
              : [...next.chunks, data.chunk as ChunkItem].sort((a, b) => a.idx - b.idx)
          }
          return next
        })
      } catch {
        // 坏事件不断开已收到的字幕。
      }
    }
    es.onerror = () => { void refresh(id) }
    return () => es.close()
  }, [detail.cancelling, detail.running, detail.task.id, refresh])

  const act = async (fn: () => Promise<void>) => {
    try {
      await fn()
      await refresh(detail.task.id)
    } catch (error) {
      alert(error instanceof Error ? error.message : String(error))
    }
  }

  const t = detail.task
  const busy = t.running || t.cancelling
  const failed = t.status === 'failed' || t.interrupted
  const done = t.status === 'done'
  const subtitleText = subtitleContent || chunkTexts(detail.chunks).join('\n')
  const totalChars = detail.chunks.reduce((sum, chunk) => sum + chunk.chars, 0)

  const copySubtitle = async () => {
    if (!subtitleText || copyState === 'copying') return
    setCopyState('copying')
    try {
      await navigator.clipboard.writeText(subtitleText)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 2200)
    } catch {
      setCopyState('idle')
      alert('复制失败，请直接选中字幕复制。')
    }
  }

  return (
    <div className={cn('space-y-6 pb-10', animate && 'swap-in')}>
      <div className="task-intro flex flex-wrap items-end justify-between gap-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <StatusMark busy={busy} failed={failed} done={done} />
            <span className="eyebrow-mono">{done ? (t.srt_exists || t.artifact === 'srt' ? 'SUBTITLE READY' : 'TRANSCRIPT READY') : busy ? 'TRANSCRIBING NOW' : failed ? 'NEEDS ATTENTION' : 'TASK'}</span>
          </div>
          <h1 className="mt-3 truncate text-2xl leading-9 tracking-display text-ink sm:text-3xl">{t.title || t.source_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-mute">
            <span>{t.mode === 'online' ? '在线' : '离线'}转录</span><span className="h-1 w-1 rounded-full bg-canvas-mid" />
            <span>{t.artifact === 'srt' ? '字幕优先' : '文稿'}</span>{t.engine && <><span className="h-1 w-1 rounded-full bg-canvas-mid" /><span className="font-mono">{t.engine}</span></>}
          </div>
        </div>
        <div className="text-right text-xs text-mute">
          {totalChars > 0 && <p className="font-mono">{totalChars.toLocaleString('zh-CN')} CHARACTERS</p>}
          <p className="mt-1">{t.created_at ? new Date(t.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</p>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          <ResultTabs task={t} chunks={detail.chunks} lastMessage={lastMessage} />
          {failed && (
            <section className="workbench-card border-destructive/40 p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <AlertCircle size={18} className="mt-0.5 shrink-0 text-destructive" />
                <div>
                  <p className="text-sm text-body">这次转录没有完整结束，已完成的字幕仍然保留。</p>
                  <p className="mt-1 text-xs leading-5 text-mute">{detail.chunks.length ? `${detail.chunks.filter((chunk) => chunk.status === 'done').length} 个片段已完成，可从断点续跑。` : '可以稍后重新开始。'}</p>
                  {t.resumable && <div className="mt-4"><ResumeButton task={t} onResume={() => act(() => resumeTask(t.id))} /></div>}
                </div>
              </div>
            </section>
          )}
        </div>

        <aside className="space-y-6 lg:sticky lg:top-5">
          <ProgressCard detail={detail} totalOverride={streamTotal} onCancel={() => void act(() => cancelTask(t.id))} />
          <FilesCard task={t} content={subtitleText} onCopy={() => void copySubtitle()} copyState={copyState} onReveal={() => void act(() => revealPath(t.out_dir as string))} />
          {(t.txt_path || t.srt_path) && (
            <div className="px-1">
              <button type="button" aria-expanded={showPaths} onClick={() => setShowPaths((value) => !value)} className="inline-flex items-center gap-1 text-xs text-mute hover:text-ink">
                文件位置 <ChevronDown size={13} className={cn('transition-transform duration-150', showPaths && 'rotate-180')} />
              </button>
              {showPaths && <div className="mt-3 space-y-2 font-mono text-[11px] leading-5 text-mute [overflow-wrap:anywhere]">
                {t.srt_path && <p><span className="text-body">字幕</span> {t.srt_path}</p>}
                {t.txt_path && <p><span className="text-body">文稿</span> {t.txt_path}</p>}
              </div>}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

/** /t/{id} → 任务号；其他路径返回 null */
function routeTaskId(): number | null {
  const matched = /^\/t\/(\d+)\/?$/.exec(window.location.pathname)
  return matched ? Number(matched[1]) : null
}

export default function TaskPage() {
  const [task, setTask] = useState<TaskDetail | null>(() => boot().task)
  // 首次进页面不播入场动效：那时骨架刚被替换掉，再淡入一次就是多闪一下
  const [switched, setSwitched] = useState(false)
  // 事件监听只注册一次，用 ref 取当前任务号，免得闭包里读到旧的
  const showing = useRef<number | null>(task?.task.id ?? null)
  showing.current = task?.task.id ?? null
  // 连点两行时两次请求同时在飞，快的不一定是你最后点的那次：只认序号，不认到达顺序。
  const pending = useRef(0)

  // 切任务不整页跳转：整页重载实测要闪两帧「内容不在」（主区全空、侧栏还挂着
  // 「加载中…」），而切任务是这一页最高频的动作。同文档换数据，侧栏不重挂也不重拉。
  useEffect(() => {
    let alive = true

    const go = async (id: number, push: boolean) => {
      if (id === showing.current) return
      const gen = ++pending.current
      let next: TaskDetail
      try {
        next = await fetchTaskDetail(id)
      } catch {
        return // 任务可能刚被删掉：留在原地，别把页面换成 404 壳
      }
      if (!alive || gen !== pending.current || id === showing.current) return
      showing.current = id
      if (push) window.history.pushState({ task: id }, '', `/t/${id}`)
      window.scrollTo(0, 0)
      setSwitched(true)
      setTask(next)
    }

    // 侧栏那排 <a href="/t/N"> 是历史岛和控制台共用的一棵 DOM，统一在这里拦下，改成压一条
    // history 再换数据；⌘ 点、中键这类「不是就地换」的意图留给浏览器。
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const link = (event.target as Element | null)?.closest?.('a[href^="/t/"]')
      if (!link) return
      const id = Number(new URL((link as HTMLAnchorElement).href).pathname.replace('/t/', ''))
      if (!Number.isInteger(id)) return
      event.preventDefault()
      void go(id, true)
    }

    const onPop = () => {
      const id = routeTaskId()
      if (id === null) {
        window.location.reload()
        return
      }
      void go(id, false)
    }

    document.addEventListener('click', onClick)
    window.addEventListener('popstate', onPop)
    return () => {
      alive = false
      document.removeEventListener('click', onClick)
      window.removeEventListener('popstate', onPop)
    }
  }, [])

  return (
    <>
      {/* 侧栏历史与控制台共用；当前这条任务在栏里标成 active */}
      <HistorySidebar currentId={task?.task.id} />
      {task ? <Detail key={task.task.id} initial={task} animate={switched} /> : (
        <div className="workbench-card px-6 py-12 text-center">
          <p className="eyebrow-mono">NOT FOUND</p>
          <p className="mt-2 text-sm text-body">没有这个任务。<a href="/" className="text-ink underline-offset-4 hover:underline">返回控制台</a></p>
        </div>
      )}
    </>
  )
}

const rootEl = document.getElementById('root')
if (rootEl) createRoot(rootEl).render(<TaskPage />)
