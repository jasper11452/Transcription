// 任务详情页（/t/{id}）：字幕、文稿与总结共用一个标签内容面板。SSE 推送已完成分片。

import { type AnimationEvent as ReactAnimationEvent, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  AlertCircle,
  ArrowDown,
  Brain,
  Check,
  ChevronDown,
  Clipboard,
  Download,
  FileText,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  StopCircle,
  Subtitles,
  X,
} from 'lucide-react'
import '@/index.css'
import { Button } from '@/components/ui/button'
import { HistorySidebar } from '@/components/history-sidebar'
import { KeyFieldsPanel } from '@/components/key-fields'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger, TabUnderline } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { boot, type ChunkItem, type HotWordGroup, type KeyField, type SubtitleLine, type SummaryModel, type SummaryPayload, type SummarySettingsPayload, type TaskDetail } from '@/lib/types'
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
  saveArtifacts,
  saveSummarySettings,
  saveTranscript,
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
      // 服务端折行只插换行不插空格（render._wrap），这里必须原样拼回，否则每保存一次就多一个空格
      const text = lines.slice(timeLineIndex + 1).join('').trim()
      return text && Number.isFinite(start) && Number.isFinite(end) ? [{ start, end, text }] : []
    })
}

function parseSrtTime(value: string): number {
  const match = value.match(/^(\d+):(\d{2}):(\d{2})[,.](\d{3})$/)
  if (!match) return Number.NaN
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000
}

function fmtSrtTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds * 1000))
  const h = Math.floor(total / 3_600_000)
  const m = Math.floor((total % 3_600_000) / 60_000)
  const sec = Math.floor((total % 60_000) / 1000)
  const ms = total % 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')},${String(ms).padStart(3, '0')}`
}

/** 行内编辑：失焦或 ⌘/Ctrl+Enter 提交，Esc 放弃。 */
function LineEditor({
  value,
  onCommit,
  onCancel,
  className,
}: {
  value: string
  onCommit: (text: string) => void
  onCancel: () => void
  className?: string
}) {
  const [draft, setDraft] = useState(value)
  const cancelled = useRef(false)
  return (
    <textarea
      autoFocus
      value={draft}
      rows={Math.min(6, Math.max(1, Math.ceil(draft.length / 34)))}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => { if (!cancelled.current) onCommit(draft.trim()) }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          cancelled.current = true
          onCancel()
        } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
          event.preventDefault()
          event.currentTarget.blur()
        }
      }}
      className={cn(
        'w-full resize-none rounded-md border border-canvas-mid bg-canvas-soft px-2 py-1 text-[15px] leading-7 text-ink outline-none focus:border-ink',
        className,
      )}
    />
  )
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

function SubtitleLineRow({
  line,
  live,
  newest,
  editable,
  editing,
  onStartEdit,
  onCommit,
  onCancel,
}: {
  line: SubtitleLine
  live?: boolean
  newest?: boolean
  editable?: boolean
  editing?: boolean
  onStartEdit?: () => void
  onCommit?: (text: string) => void
  onCancel?: () => void
}) {
  return (
    <div className={cn('subtitle-line group', live && 'subtitle-line-live', newest && 'subtitle-line-current')}>
      <span className="subtitle-time font-mono">{fmtTime(line.start)}</span>
      {editing ? (
        <div className="min-w-0 flex-1">
          <LineEditor value={line.text} onCommit={(text) => onCommit?.(text)} onCancel={() => onCancel?.()} />
        </div>
      ) : editable ? (
        <button
          type="button"
          onClick={onStartEdit}
          title="点击修改这一行"
          className="min-w-0 flex-1 whitespace-pre-wrap rounded-md px-1 text-left text-[15px] leading-7 text-body -mx-1 hover:bg-surface-hover focus-visible:bg-surface-hover"
        >
          {line.text}
        </button>
      ) : (
        <p className="min-w-0 flex-1 whitespace-pre-wrap text-[15px] leading-7 text-body">{line.text}</p>
      )}
      {newest && <span className="subtitle-cursor" aria-hidden="true" />}
    </div>
  )
}

function SubtitlePanel({
  task,
  chunks,
  lastMessage,
  editedLines,
  editable,
  onEditLine,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
  editedLines: SubtitleLine[]
  editable: boolean
  onEditLine: (index: number, text: string) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  // 哪一行正在改：同一时刻只放一个 textarea，长字幕也不怕整页重排。
  const [editing, setEditing] = useState<number | null>(null)
  // 跟随最新是默认行为；用户上滑就暂停，底部的胶囊负责告诉他“后面又来了多少条”。
  const [follow, setFollow] = useState(task.running)
  // 暂停那一刻的行数游标：只数之后新到的行，不会把历史字幕也算成“新”。
  const pausedAt = useRef(0)

  const liveLines = useMemo(() => mergeChunkLines(chunks), [chunks])
  // 完成的字幕由详情页统一持有（两个标签共用一份，改了立刻同步）；
  // 转录中还没有文件，退回分片文本。
  const lines = editedLines.length ? editedLines : liveLines.length ? liveLines : fallbackLines(chunks)
  const latestKey = lines.length ? String(lines[lines.length - 1].start) + '-' + lines[lines.length - 1].text : ''

  useEffect(() => {
    if (!follow || !scrollRef.current) return
    const container = scrollRef.current
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    container.scrollTo({ top: container.scrollHeight, behavior })
  }, [follow, latestKey])

  useEffect(() => {
    if (follow) pausedAt.current = lines.length
  }, [follow, lines.length])

  const unseen = follow ? 0 : Math.max(0, lines.length - pausedAt.current)
  const atBottom = () => {
    const container = scrollRef.current
    if (!container) return true
    return container.scrollHeight - container.scrollTop - container.clientHeight < 8
  }
  const resumeFollow = () => {
    setFollow(true)
    const container = scrollRef.current
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
  }

  const isLive = task.running
  const hasLines = lines.length > 0
  // 只有产物真的存在时才标 SRT：转录中/失败的任务只有分片文本，没有文件。
  const timed = task.srt_exists
  const formatLabel = timed ? 'SRT · 时间轴' : '已完成片段'

  return (
    <>
      <div className="relative">
        <div
          ref={scrollRef}
          className="subtitle-scroll px-4 py-3 sm:px-6 sm:py-4"
          role="region"
          aria-label="字幕列表"
          tabIndex={0}
          onWheel={(event) => { if (event.deltaY < 0) setFollow(false) }}
          onTouchMove={() => setFollow(false)}
          onScroll={() => { if (!follow && atBottom()) setFollow(true) }}
        >
        {hasLines ? (
          <div className="space-y-0.5">
            {lines.map((line, index) => (
              <SubtitleLineRow
                key={String(line.start) + '-' + index}
                line={line}
                live={isLive && index === lines.length - 1}
                newest={isLive && index === lines.length - 1}
                editable={editable}
                editing={editing === index}
                onStartEdit={() => setEditing(index)}
                onCommit={(text) => {
                  if (text && text !== line.text) onEditLine(index, text)
                  setEditing(null)
                }}
                onCancel={() => setEditing(null)}
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
        {isLive && !follow && unseen > 0 && (
          <button type="button" className="subtitle-follow-pill" onClick={resumeFollow}>
            <ArrowDown size={13} /> {unseen} 条新字幕
          </button>
        )}
      </div>
      <div className="flex min-h-11 items-center justify-between gap-3 border-t border-hairline bg-canvas-soft/40 px-5 py-3 sm:px-6">
        <p className="truncate text-xs text-mute">
          {isLive
            ? lastMessage || '实时转录中 · 字幕会陆续出现'
            : timed
              ? `${formatLabel} · ${lines.length} 条字幕${editable ? ' · 点一行即可修改' : ''}`
              : lines.length
                ? `已完成 ${lines.length} 条 · 字幕尚未生成`
                : '字幕尚未生成'}
        </p>
        {isLive && <span className="live-label"><span /> 实时</span>}
      </div>
      {/* 每 5 条播报一次，不跟着每个分片刷屏 */}
      <span className="sr-only" role="status">
        {isLive && lines.length >= 5 ? `已完成 ${Math.floor(lines.length / 5) * 5} 段字幕` : ''}
      </span>
    </>
  )
}

function TranscriptPanel({
  task,
  chunks,
  lastMessage,
  editable,
  version,
  onSaved,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
  editable: boolean
  version: number
  onSaved: () => void
}) {
  const [fileText, setFileText] = useState('')
  const [draft, setDraft] = useState('')
  const [fileError, setFileError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const dirtyRef = useRef(false)
  // 全文编辑：txt 是这份稿子的真相，srt 在保存时按原时间轴重新切句。
  const dirty = editable && draft !== fileText
  dirtyRef.current = dirty

  useEffect(() => {
    let active = true
    setFileError('')
    if (task.running || task.status !== 'done' || !task.txt_exists) {
      setFileText('')
      setDraft('')
      return () => { active = false }
    }
    fetchOutput(task.id, 'txt').then((text) => {
      if (!active) return
      setFileText(text)
      // 有未保存的全文改动时，不用磁盘版本覆盖草稿
      if (!dirtyRef.current) setDraft(text)
    }).catch((error) => {
      if (active) setFileError(error instanceof Error ? error.message : String(error))
    })
    return () => { active = false }
  }, [task.id, task.running, task.status, task.txt_exists, version])

  useEffect(() => { setSaveError('') }, [task.id])

  const chunkText = chunks
    .filter((chunk) => chunk.status === 'done' && chunk.text.trim())
    .map((chunk) => chunk.text.trim())
    .join('\n')
  const readOnlyText = fileText || chunkText
  const isLive = task.running

  const save = async () => {
    if (!dirty || saving || !draft.trim()) return
    setSaving(true)
    setSaveError('')
    try {
      const saved = await saveTranscript(task.id, draft)
      setFileText(saved.txt)
      setDraft(saved.txt)
      onSaved()
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="subtitle-scroll px-5 py-4 sm:px-7 sm:py-5" role="region" aria-label="文稿内容" tabIndex={0}>
        {editable ? (
          <textarea
            value={draft}
            onChange={(event) => { setDraft(event.target.value); setSaveError('') }}
            spellCheck={false}
            aria-label="文稿全文"
            rows={Math.max(12, draft.split('\n').length + 2)}
            className="min-h-[260px] w-full resize-y bg-transparent font-sans text-[15px] leading-7 text-body outline-none"
          />
        ) : readOnlyText ? (
          <pre className="min-h-[260px] whitespace-pre-wrap break-words font-sans text-[15px] leading-7 text-body">{readOnlyText}</pre>
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
      <div className="flex min-h-11 flex-wrap items-center justify-between gap-3 border-t border-hairline bg-canvas-soft/40 px-5 py-3 sm:px-6">
        <p className="min-w-0 flex-1 truncate text-xs text-mute" role="status">
          {isLive
            ? (lastMessage || '正在转录…')
            : saveError
              ? <span className="text-destructive">{saveError}</span>
              : dirty
                ? '文稿已修改；保存会按原时间轴重新切句，并同步 .txt'
                : fileError || `${(task.chars ?? readOnlyText.length).toLocaleString('zh-CN')} 个字符`}
        </p>
        {isLive ? (
          <span className="live-label"><span /> 实时</span>
        ) : editable ? (
          dirty ? (
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" className="summary-retry" onClick={() => { setDraft(fileText); setSaveError('') }}>
                放弃
              </button>
              <Button type="button" size="sm" onClick={() => void save()} disabled={saving || !draft.trim()}>
                {saving ? '保存中…' : '保存文稿'}
              </Button>
            </div>
          ) : (
            <span className="shrink-0 font-mono text-xs text-mute">可直接编辑全文</span>
          )
        ) : null}
      </div>
    </>
  )
}

function normalizeHotWordGroups(groups: HotWordGroup[], fallback: string[] = []): EditorGroup[] {
  if (groups.length) return groups.map((group) => makeGroup(group.name, group.words))
  // 老词表只有 `错词 -> 正确词` 时没有分组；这些正确写法仍算热词，放进未分组免得看不见。
  return [makeGroup('', fallback)]
}

/** 编辑器内部的分组：`id` 只活在当前页面，用来做稳定 key（改名不会重挂输入框）。 */
type EditorGroup = HotWordGroup & { id: number }
let nextGroupId = 1
const makeGroup = (name: string, words: string[]): EditorGroup => ({
  id: nextGroupId++,
  name,
  words: [...words],
})

/** 加词：返回新分组与「被忽略的条数」，后者用来给用户一句实话，而不是静默丢弃。 */
function addWordsToGroup(
  groups: EditorGroup[],
  index: number,
  raw: string,
  maxChars: number,
  maxWords: number,
): { groups: EditorGroup[]; ignored: number } {
  const next = groups.map((group) => ({ ...group, words: [...group.words] }))
  const taken = new Set(next.flatMap((group) => group.words))
  let ignored = 0
  for (const part of raw.split(/[,，、\s]+/)) {
    const value = part.trim().slice(0, maxChars)
    if (!value) continue
    if (taken.has(value) || taken.size >= maxWords) {
      ignored += 1
      continue
    }
    taken.add(value)
    next[index].words.push(value)
  }
  return { groups: next, ignored }
}

/** 删整组会连词条一起丢：跟历史任务删除一样先点变确认，4 秒不点自动退回。 */
function DeleteGroupButton({
  name,
  count,
  onConfirm,
}: {
  name: string
  count: number
  onConfirm: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (!confirming) return
    const timer = setTimeout(() => setConfirming(false), 4000)
    return () => clearTimeout(timer)
  }, [confirming])
  return (
    <button
      type="button"
      onClick={() => (confirming ? onConfirm() : setConfirming(true))}
      aria-label={confirming ? `确认删除热词分组 ${name}` : `删除热词分组 ${name}`}
      title={confirming ? `再点一次删除，${count} 个词一起移除` : '删除分组（词条一起移除）'}
      className={cn(
        'ml-auto flex h-8 w-8 items-center justify-center rounded-md text-mute transition-colors hover:bg-surface-hover hover:text-destructive',
        confirming && 'text-destructive',
      )}
    >
      {confirming ? <Check size={13} /> : <X size={13} />}
    </button>
  )
}

/** 一个热词分组：组名可改，词条回车/逗号加入，Backspace 删除最后一个。 */
function HotWordGroupRow({
  group,
  index,
  maxChars,
  maxGroupChars,
  onRename,
  onAddWords,
  onRemoveWord,
  onRemove,
}: {
  group: HotWordGroup
  index: number
  maxChars: number
  maxGroupChars: number
  onRename: (index: number, name: string) => void
  onAddWords: (index: number, raw: string) => void
  onRemoveWord: (index: number, word: string) => void
  onRemove: (index: number) => void
}) {
  const [draft, setDraft] = useState('')

  const commit = () => {
    if (!draft.trim()) return
    onAddWords(index, draft)
    setDraft('')
  }

  return (
    <div className="rounded-lg border border-hairline bg-canvas-soft p-3">
      <div className="flex items-center gap-2">
        <Input
          value={group.name}
          onChange={(event) => onRename(index, event.target.value)}
          maxLength={maxGroupChars}
          aria-label={`热词分组 ${index + 1} 名称`}
          placeholder="分组名（留空 = 未分组）"
          className="h-8 max-w-56 bg-canvas"
        />
        <span className="font-mono text-[11px] text-mute">{group.words.length}</span>
        <DeleteGroupButton
          name={group.name || `未分组 ${index + 1}`}
          count={group.words.length}
          onConfirm={() => onRemove(index)}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-hairline bg-canvas p-2">
        {group.words.map((word) => (
          <span
            key={word}
            className="inline-flex items-center gap-1 rounded-md bg-surface-selected px-2 py-1 font-mono text-[11px] text-body"
          >
            {word}
            <button
              type="button"
              onClick={() => onRemoveWord(index, word)}
              aria-label={`从${group.name || '未分组'}移除热词 ${word}`}
              className="text-mute transition-colors hover:text-ink"
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',' || event.key === '，' || event.key === '、') {
              event.preventDefault()
              commit()
            } else if (event.key === 'Backspace' && !draft && group.words.length) {
              onRemoveWord(index, group.words[group.words.length - 1])
            }
          }}
          onBlur={commit}
          maxLength={maxChars + 2}
          placeholder={group.words.length ? '继续输入…' : '输入后回车，例如：小新'}
          autoComplete="off"
          className="h-7 min-w-[8rem] flex-1 bg-transparent px-1 text-sm text-foreground placeholder:text-mute focus:outline-none"
        />
      </div>
    </div>
  )
}

function SummarySettingsEditor() {
  const [settings, setSettings] = useState<SummarySettingsPayload | null>(null)
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [groups, setGroups] = useState<EditorGroup[]>([])
  const [ignoredWords, setIgnoredWords] = useState(0)
  const [newGroup, setNewGroup] = useState('')
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
      setGroups(normalizeHotWordGroups(next.hot_word_groups ?? [], next.hot_words))
      setIgnoredWords(0)
      setError('')
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : String(err))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  const connectionDirty = baseUrl.trim().replace(/\/+$/, '') !== settings?.base_url

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

  // 焦点始终留在输入框（aria-activedescendant 模式）：上下键移动高亮时把选项滚进可视区。
  useEffect(() => {
    if (!listOpen) return
    document.getElementById(`summaryModelOption-${highlight}`)?.scrollIntoView({ block: 'nearest' })
  }, [listOpen, highlight])

  const filteredModels = useMemo(() => {
    const all = models ?? []
    const needle = query.trim().toLowerCase()
    const matched = needle
      ? all.filter(
          (item) =>
            item.id.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
        )
      : all
    return matched.slice(0, 60)
  }, [models, query])

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
      else setHighlight((index) => Math.min(index + 1, Math.max(filteredModels.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && listOpen && filteredModels[highlight]) {
      event.preventDefault()
      pickModel(filteredModels[highlight].id)
    } else if (event.key === 'Escape') {
      setListOpen(false)
    }
  }

  const maxHotWordChars = settings?.max_hot_word_chars ?? 40
  const maxHotWords = settings?.max_hot_words ?? 80
  const maxGroupChars = settings?.max_hot_word_group_chars ?? 24
  const maxGroups = settings?.max_hot_word_groups ?? 12

  const renameGroup = (index: number, name: string) => {
    setGroups((current) => current.map((group, i) => (i === index ? { ...group, name } : group)))
  }

  const addGroup = () => {
    const name = newGroup.trim()
    if (!name) {
      setError('先给分组起个名字。')
      return
    }
    if (groups.some((group) => group.name.trim() === name)) {
      setError(`分组“${name}”已经存在。`)
      return
    }
    if (groups.filter((group) => group.name.trim() || group.words.length).length >= maxGroups) {
      setError(`最多 ${maxGroups} 个热词分组。`)
      return
    }
    setGroups((current) => [
      ...current.filter((group) => group.name.trim() || group.words.length),
      makeGroup(name, []),
    ])
    setNewGroup('')
    setIgnoredWords(0)
    setError('')
    setMessage('')
  }

  const removeGroup = (index: number) => {
    setIgnoredWords(0)
    setGroups((current) => {
      const next = current.filter((_, i) => i !== index)
      return next.length ? next : [makeGroup('', [])]
    })
  }

  // 每次加词都发生在独立的一次用户事件里，用的是上一次渲染后的 groups，不会读到旧列表；
  // 用 setGroups(fn) 反而拿不到「忽略了几条」的返回值。
  const addWords = (index: number, raw: string) => {
    const { groups: next, ignored: dropped } = addWordsToGroup(
      groups,
      index,
      raw,
      maxHotWordChars,
      maxHotWords,
    )
    setGroups(next)
    setIgnoredWords(dropped)
  }

  const removeWord = (index: number, word: string) => {
    setIgnoredWords(0) // 删掉一个词后「到上限了」的提示就不该继续挂着
    setGroups((current) =>
      current.map((group, i) =>
        i === index ? { ...group, words: group.words.filter((item) => item !== word) } : group,
      ),
    )
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
      const next = await saveSummarySettings({
        model,
        base_url: baseUrl,
        prompt,
        hot_word_groups: groups.map((group) => ({ name: group.name.trim(), words: group.words })),
      })
      setSettings(next)
      setModel(next.model)
      setBaseUrl(next.base_url)
      setPrompt(next.prompt)
      setGroups(normalizeHotWordGroups(next.hot_word_groups ?? [], next.hot_words))
      setIgnoredWords(0)
      setNewGroup('')
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
            <p className="text-xs leading-5 text-mute">
              OpenRouter 密钥在页面顶部「密钥」里维护；这里只改地址、模型与提示词。
            </p>
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
                  aria-autocomplete="list"
                  aria-activedescendant={listOpen && filteredModels[highlight] ? `summaryModelOption-${highlight}` : undefined}
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
                      <span className="font-mono text-[11px] text-mute">
                        {loadingModels ? '读取中…' : models === null ? '模型清单' : `${filteredModels.length} / ${models.length} 个模型`}
                      </span>
                      <button
                        type="button"
                        onClick={() => void loadModels(true)}
                        disabled={loadingModels}
                        className="font-mono text-[11px] text-mute transition-colors hover:text-ink disabled:opacity-50"
                      >
                        刷新
                      </button>
                    </div>
                    <div id="summaryModelList" role="listbox" className="max-h-64 overflow-y-auto">
                      {filteredModels.map((item, index) => (
                        <div
                          key={item.id}
                          id={`summaryModelOption-${index}`}
                          role="option"
                          tabIndex={-1}
                          aria-selected={item.id === model}
                          onMouseEnter={() => setHighlight(index)}
                          onClick={() => pickModel(item.id)}
                          className={cn(
                            'flex w-full cursor-pointer flex-col gap-0.5 px-3 py-2 text-left transition-colors',
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
                        </div>
                      ))}
                      {!loadingModels && models !== null && !filteredModels.length && (
                        <p className="px-3 py-3 text-[11px] text-mute">
                          {models.length ? '没有匹配的模型，仍可直接使用输入的内容。' : '暂无可选清单，直接输入模型 ID 即可。'}
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
              <p className="text-xs leading-5 text-mute">
                输出字段是固定的：标题、主旨、要点、待办。这里的提示词只决定内容取舍、语气和语言，
                不能改成别的结构或格式；改完需要点「重新生成」才会生效。
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span id="summaryHotWordsLabel" className="eyebrow-mono">热词库</span>
                <span className="text-xs text-mute">
                  共 {groups.reduce((sum, group) => sum + group.words.length, 0)} / {settings.max_hot_words} 个词
                </span>
              </div>
              <div className="space-y-2" role="group" aria-labelledby="summaryHotWordsLabel">
                {groups.map((group, index) => (
                  <HotWordGroupRow
                    key={group.id}
                    group={group}
                    index={index}
                    maxChars={maxHotWordChars}
                    maxGroupChars={maxGroupChars}
                    onRename={renameGroup}
                    onAddWords={addWords}
                    onRemoveWord={removeWord}
                    onRemove={removeGroup}
                  />
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Input
                  value={newGroup}
                  onChange={(event) => setNewGroup(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      addGroup()
                    }
                  }}
                  maxLength={maxGroupChars}
                  placeholder="新分组名称"
                  aria-label="新热词分组名称"
                  className="h-8 w-48"
                />
                <Button type="button" size="sm" variant="outline" onClick={addGroup}>
                  新建分组
                </Button>
                <span className="text-xs text-mute">
                  最多 {maxGroups} 组；组名留空即为未分组。
                </span>
              </div>
              <p className="text-xs leading-5 text-mute">
                词条用逗号或回车分隔，组名会写进词表的 <span className="font-mono">## 组名</span>。
                错词 → 正确词的替换规则不受影响。
              </p>
              {ignoredWords > 0 && (
                <p role="status" className="text-xs leading-5 text-mute">
                  已忽略 {ignoredWords} 个词：重复，或已到 {maxHotWords} 个上限。
                </p>
              )}
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
        <span className="font-mono text-[11px] text-mute">
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
          <p className="eyebrow-mono">主旨</p>
          <p className="mt-2 text-sm leading-6 text-body">
            {partial.overview}
            {partial.titleComplete && !partial.overviewComplete && <span className="summary-caret" />}
          </p>
        </div>
      )}
      {!!partial.keyPoints.length && (
        <div>
          <p className="eyebrow-mono">要点</p>
          <ul className="mt-2 space-y-2">
            {partial.keyPoints.map((point, index) => (
              <li key={`${index}-${point}`} className="summary-bullet">{point}</li>
            ))}
          </ul>
        </div>
      )}
      {!!partial.actionItems.length && (
        <div>
          <p className="eyebrow-mono">待办</p>
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

function SummaryPanel({ task }: { task: TaskDetail['task'] }) {
  const [summary, setSummary] = useState<SummaryPayload | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  // 增量抓取：只取上次之后新增的尾巴。长总结不再每轮整份重下（O(n²) → O(n)）。
  const partialRef = useRef({ content: '', reasoning: '' })

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSummary(task.id, {
        content: partialRef.current.content.length,
        reasoning: partialRef.current.reasoning.length,
      })
      // 后端长度比本地短 = 总结重新开了，整份重置，别把新旧拼在一起。
      const stale =
        (next.partial.content_length ?? 0) < partialRef.current.content.length ||
        (next.partial.reasoning_length ?? 0) < partialRef.current.reasoning.length
      partialRef.current = stale
        ? { content: next.partial.content, reasoning: next.partial.reasoning }
        : {
            content: partialRef.current.content + next.partial.content,
            reasoning: partialRef.current.reasoning + next.partial.reasoning,
          }
      setSummary({ ...next, partial: partialRef.current })
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

  // 每次拿到的是整份 partial，摘要越完整越贵：起步 700ms 逐次退到 1500ms，页面不可见时停手。
  useEffect(() => {
    if (!summary || !['waiting', 'running'].includes(summary.status)) return
    let delay = 700
    let timer = 0
    const poll = async () => {
      if (document.hidden) {
        timer = window.setTimeout(poll, 2000)
        return
      }
      await refresh()
      delay = Math.min(1500, Math.round(delay * 1.3))
      timer = window.setTimeout(poll, delay)
    }
    timer = window.setTimeout(poll, delay)
    return () => window.clearTimeout(timer)
  }, [refresh, summary?.status])

  const start = async () => {
    setWorking(true)
    setError('')
    try {
      const next = await enableSummary(task.id)
      // enable 返回整份，把增量游标对齐到它，接下来的轮询才能只取尾巴。
      partialRef.current = { content: next.partial.content, reasoning: next.partial.reasoning }
      setSummary(next)
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
            <span className="font-mono text-[11px] text-mute">{streaming ? '流式生成中' : thinking ? '思考中' : '等待首个片段'}</span>
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
            <p className="eyebrow-mono">主旨</p>
            <p className="mt-2 text-sm leading-6 text-body">{content.overview}</p>
          </div>
          {!!content.key_points.length && (
            <div>
              <p className="eyebrow-mono">要点</p>
              <ul className="mt-2 space-y-2">
                {content.key_points.map((point) => <li key={point} className="summary-bullet">{point}</li>)}
              </ul>
            </div>
          )}
          {!!content.action_items.length && (
            <div>
              <p className="eyebrow-mono">待办</p>
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
          <Button asChild size="sm" variant="outline"><a href="/settings">去设置</a></Button>
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
  editedLines,
  editable,
  onEditLine,
  outputVersion,
  onOutputSaved,
}: {
  task: TaskDetail['task']
  chunks: ChunkItem[]
  lastMessage: string
  editedLines: SubtitleLine[]
  editable: boolean
  onEditLine: (index: number, text: string) => void
  outputVersion: number
  onOutputSaved: () => void
}) {
  const defaultTab = task.artifact === 'txt' && !task.srt_exists ? 'transcript' : 'subtitle'
  const [activeTab, setActiveTab] = useState(defaultTab)
  const [shown, setShown] = useState<string[]>([defaultTab])
  // 首屏那次不播入场；用户真正切标签后才开始给内容一点位移反馈
  const [switched, setSwitched] = useState(false)
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
      onValueChange={(value) => {
        setSwitched(true)
        setActiveTab(value as 'subtitle' | 'transcript' | 'summary')
      }}
      data-switched={switched ? '' : undefined}
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
        </TabsList>
      </div>
      <TabsContent value="subtitle" className="result-tab-content mt-0 outline-none" {...arrived('subtitle')}>
        <SubtitlePanel
          task={task}
          chunks={chunks}
          lastMessage={lastMessage}
          editedLines={editedLines}
          editable={editable}
          onEditLine={onEditLine}
        />
      </TabsContent>
      <TabsContent value="transcript" className="result-tab-content mt-0 outline-none" {...arrived('transcript')}>
        <TranscriptPanel
          task={task}
          chunks={chunks}
          lastMessage={lastMessage}
          editable={editable}
          version={outputVersion}
          onSaved={onOutputSaved}
        />
      </TabsContent>
      <TabsContent value="summary" className="result-tab-content mt-0 outline-none" {...arrived('summary')}>
        <SummaryPanel task={task} />
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

/** 停止长任务要二次确认：第一次点击改成确认态，4 秒不点自动退回。 */
function StopButton({ onStop, compact = false }: { onStop: () => void; compact?: boolean }) {
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(false), 4000)
    return () => window.clearTimeout(timer)
  }, [confirming])
  return (
    <Button
      type="button"
      variant={confirming ? 'destructive' : 'outline'}
      className={compact ? 'h-8 shrink-0 px-3 text-xs' : 'mt-6 w-full'}
      onClick={() => (confirming ? onStop() : setConfirming(true))}
    >
      <StopCircle size={15} className="mr-2" />
      {confirming ? '再点一次，确认停止' : '停止转录'}
    </Button>
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
  // 「失败」和「被中断」不是一回事：前者引擎报错，后者是没跑完（进程不在了）。
  const interrupted = t.status === 'running' && !busy
  const failedState = t.status === 'failed'
  const failed = failedState || interrupted
  const done = t.status === 'done'
  const total = Math.max(totalOverride, detail.chunks.length)
  const doneCount = detail.chunks.filter((chunk) => chunk.status === 'done').length
  const pct = Math.min(100, Math.max(0, Math.round(t.progress)))
  const outcome = t.cancelling ? '停止中' : interrupted ? '已中断' : STATUS_LABEL[t.status] ?? t.status

  // 长录音的等待没有时间感：运行时给出已用时（每 30 秒刷新一次，不逐秒重渲染）。
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => setNow(Date.now()), 30000)
    return () => window.clearInterval(timer)
  }, [busy])
  const startedAt = t.started_at ?? t.created_at
  const elapsed = busy && startedAt ? Math.max(0, (now - new Date(startedAt).getTime()) / 1000) : null

  return (
    <section className="workbench-card p-5 sm:p-6" aria-labelledby="progressTitle">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <StatusMark busy={busy} failed={failed} done={done} />
          <h2 id="progressTitle" className="text-sm text-body">{outcome}</h2>
        </div>
        <span className="eyebrow-mono">{t.mode === 'online' ? '在线' : '离线'}</span>
      </div>
      <div className="mt-6 flex items-end gap-2">
        <span className="font-mono text-4xl leading-none tracking-tight text-ink">{pct}</span>
        <span className="pb-0.5 font-mono text-sm text-mute">%</span>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-canvas-soft" aria-label={`已完成 ${pct}%`} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        {/* 用 transform 推进，不用 width：width 每帧都要重新布局，而进度是随时间连续跳动的。
            500ms 也让进度条严重滞后于真实进度，改成 200ms。 */}
        <div
          className={cn('h-full w-full origin-left rounded-full transition-transform duration-200 ease-out', done ? 'bg-ink' : failed ? 'bg-destructive' : 'bg-sunset')}
          style={{ transform: `scaleX(${pct / 100})` }}
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-mute">
        <span>{total ? `${doneCount} / ${total} 个音频片段` : '正在分析音频…'}</span>
        {elapsed !== null ? (
          <span className="font-mono">已用 {fmtTime(elapsed)}</span>
        ) : t.duration_s ? (
          <span className="font-mono">{fmtTime(t.duration_s)}</span>
        ) : null}
      </div>
      {busy && <StopButton onStop={onCancel} />}
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
      {task.out_dir && (
        <button
          type="button"
          className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-lg px-3 text-xs text-body transition-colors hover:bg-surface-hover hover:text-ink"
          onClick={onReveal}
        >
          <FolderOpen size={13} /> 在访达中显示
        </button>
      )}
    </section>
  )
}

function Detail({ initial, animate }: { initial: TaskDetail; animate: boolean }) {
  const [detail, setDetail] = useState<TaskDetail>(initial)
  const [streamTotal, setStreamTotal] = useState(initial.chunks.length)
  const [lastMessage, setLastMessage] = useState('')
  const [showPaths, setShowPaths] = useState(false)
  // 校对以“字幕行”为唯一模型：字幕与文稿两个标签改的是同一份句子。
  const [lines, setLines] = useState<SubtitleLine[]>([])
  const [savedLines, setSavedLines] = useState<SubtitleLine[]>([])
  const [outputVersion, setOutputVersion] = useState(0)
  const [savingEdits, setSavingEdits] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied'>('idle')
  // 行内错误：原生 alert 不能选中、不能复制长错误，也和这套视觉不搭
  const [actionError, setActionError] = useState('')

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
      setLines([])
      setSavedLines([])
      return () => { active = false }
    }
    fetchOutput(detail.task.id, 'srt').then((raw) => {
      if (!active) return
      const parsed = parseSrt(raw)
      setLines(parsed)
      setSavedLines(parsed.map((line) => ({ ...line })))
    }).catch(() => {
      if (active) { setLines([]); setSavedLines([]) }
    })
    return () => { active = false }
  }, [detail.task.id, detail.running, detail.task.running, detail.task.srt_exists, detail.task.status, outputVersion])

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
    setActionError('')
    try {
      await fn()
      await refresh(detail.task.id)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    }
  }

  const t = detail.task
  const busy = t.running || t.cancelling
  // 与进度卡同一口径：失败（引擎报错）≠ 已中断（进程不在了）。
  const interrupted = t.status === 'running' && !busy
  const failedState = t.status === 'failed'
  const failed = failedState || interrupted
  const done = t.status === 'done'
  const editable = done && t.srt_exists && !busy
  const subtitleText = lines.length
    ? lines.map((line) => line.text).join('\n')
    : detail.chunks.map((chunk) => chunk.text).filter(Boolean).join('\n')
  const changedLines = lines.filter((line, index) => line.text !== savedLines[index]?.text).length
  const dirty = editable && changedLines > 0
  const totalChars = t.chars ?? detail.chunks.reduce((sum, chunk) => sum + chunk.chars, 0)
  // 阶段化标题区要用到的进度读数（与右栏卡片同一口径）
  const totalChunks = Math.max(streamTotal, detail.chunks.length)
  const doneChunks = detail.chunks.filter((chunk) => chunk.status === 'done').length
  const pct = Math.min(100, Math.max(0, Math.round(t.progress)))

  // 浏览器标题跟着记录走，历史里开好几个标签页时才分得清。
  useEffect(() => {
    document.title = t.title ? `${t.title} · 转录` : '任务 · 转录'
  }, [t.title])

  const editLine = (index: number, text: string) => {
    setLines((current) => current.map((line, at) => (at === index ? { ...line, text } : line)))
    setSaveError('')
  }

  const saveEdits = async () => {
    if (!editable || !dirty || savingEdits) return
    setSavingEdits(true)
    setSaveError('')
    // 时间轴原样带回：服务端只接受正文改动，行数变了会拒绝。
    const editedSrt = lines
      .map((line, index) => `${index + 1}\n${fmtSrtTime(line.start)} --> ${fmtSrtTime(line.end)}\n${line.text}`)
      .join('\n\n') + '\n'
    try {
      const saved = await saveArtifacts(t.id, editedSrt)
      const parsed = parseSrt(saved.srt)
      setLines(parsed)
      setSavedLines(parsed.map((line) => ({ ...line })))
      setOutputVersion((value) => value + 1)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error))
    } finally {
      setSavingEdits(false)
    }
  }

  const copySubtitle = async () => {
    if (!subtitleText || copyState === 'copying') return
    setActionError('')
    setCopyState('copying')
    try {
      await navigator.clipboard.writeText(subtitleText)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 2200)
    } catch {
      setCopyState('idle')
      setActionError('复制失败，请直接选中字幕复制。')
    }
  }

  return (
    <div className={cn('space-y-6 pb-10', animate && 'swap-in')}>
      {actionError && (
        <p role="alert" className="rounded-lg border border-destructive/40 px-4 py-3 text-sm leading-6 text-destructive [overflow-wrap:anywhere]">{actionError}</p>
      )}
      <div className="task-intro flex flex-wrap items-end justify-between gap-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <StatusMark busy={busy} failed={failed} done={done} />
            <span className="eyebrow-mono">{done ? (t.srt_exists ? '字幕已就绪' : '文稿已就绪') : busy ? '正在转录' : interrupted ? '已中断' : failedState ? '转录失败' : '任务'}</span>
          </div>
          <h1 title={t.title || t.source_name} className="mt-3 line-clamp-2 text-2xl leading-9 tracking-display text-ink sm:text-3xl">{t.title || t.source_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-mute">
            <span>{t.mode === 'online' ? '在线' : '离线'}转录</span><span className="h-1 w-1 rounded-full bg-canvas-mid" />
            <span>{t.artifact === 'srt' ? '字幕优先' : '文稿'}</span>{t.engine && <><span className="h-1 w-1 rounded-full bg-canvas-mid" /><span className="font-mono">{t.engine}</span></>}
          </div>
        </div>
        <div className="flex flex-col items-end">
          {/* 手机：把当前阶段最需要的动作放标题区（桌面右栏就在正文旁，不重复一份） */}
          <div className="w-full empty:hidden lg:hidden">
            {done ? (
              <div className="flex flex-wrap items-center gap-2">
                {t.srt_exists && (
                  <a className="header-action header-action-primary" href={`/api/tasks/${t.id}/output/file?kind=srt&download=true`}>
                    <Download size={14} /> 下载字幕
                  </a>
                )}
                {t.txt_exists && (
                  <a className="header-action" href={`/api/tasks/${t.id}/output/file?kind=txt&download=true`}>
                    <FileText size={14} /> 下载文稿
                  </a>
                )}
                {subtitleText && (
                  <button type="button" className="header-action" disabled={copyState === 'copying'} onClick={() => void copySubtitle()}>
                    {copyState === 'copied' ? <Check size={14} /> : <Clipboard size={14} />}
                    {copyState === 'copied' ? '已复制' : '复制全文'}
                  </button>
                )}
              </div>
            ) : busy ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-sm text-ink">{pct}%</span>
                  <span className="text-xs text-mute">{totalChunks ? `${doneChunks} / ${totalChunks} 片段` : '正在分析音频…'}</span>
                  <StopButton compact onStop={() => void act(() => cancelTask(t.id))} />
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-canvas-soft" role="progressbar" aria-label="转录进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                  <div className="h-full w-full origin-left rounded-full bg-sunset transition-transform duration-200 ease-out" style={{ transform: `scaleX(${pct / 100})` }} />
                </div>
              </div>
            ) : null}
          </div>
          <div className="mt-2 text-right text-xs text-mute lg:mt-0">
            {totalChars > 0 && <p className="font-mono">{totalChars.toLocaleString('zh-CN')} 字</p>}
            <p className="mt-1">{t.created_at ? new Date(t.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</p>
          </div>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          {failed && (
            <section className="workbench-card border-destructive/40 p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <AlertCircle size={18} className="mt-0.5 shrink-0 text-destructive" />
                <div>
                  <p className="text-sm text-body">这次转录没有完整结束，已完成的字幕仍然保留。</p>
                  <p className="mt-1 text-xs leading-5 text-mute">{detail.chunks.length ? `${detail.chunks.filter((chunk) => chunk.status === 'done').length} 个片段已完成，可从断点续跑。` : '可以稍后重新开始。'}</p>
                  {t.error && <p className="mt-2 text-xs leading-5 text-destructive [overflow-wrap:anywhere]">{t.error}</p>}
                  {t.resumable && <div className="mt-4"><ResumeButton task={t} onResume={() => act(() => resumeTask(t.id))} /></div>}
                </div>
              </div>
            </section>
          )}
          {editable && (dirty || saveError) && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-hairline bg-canvas-card px-4 py-3">
              <p
                role={saveError ? 'alert' : undefined}
                className={cn('text-xs leading-5', saveError ? 'text-destructive' : 'text-mute')}
              >
                {saveError || `已修改 ${changedLines} 行；保存会同时重写 .srt 与 .txt`}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setLines(savedLines.map((line) => ({ ...line })))
                    setSaveError('')
                  }}
                >
                  放弃
                </Button>
                <Button type="button" size="sm" onClick={() => void saveEdits()} disabled={savingEdits}>
                  {savingEdits ? '保存中…' : '保存修改'}
                </Button>
              </div>
            </div>
          )}
          <ResultTabs
            task={t}
            chunks={detail.chunks}
            lastMessage={lastMessage}
            editedLines={lines}
            editable={editable}
            onEditLine={editLine}
            outputVersion={outputVersion}
            onOutputSaved={() => setOutputVersion((value) => value + 1)}
          />
        </div>

        <aside aria-label="任务信息" className="flex flex-col gap-6 lg:sticky lg:top-5">
          {/* 完成后进度卡没有信息量：右栏从文件与元信息开始。
              手机上进度已经在标题区，右栏不再重复一份（display:none 会被 flex gap 跳过）。 */}
          {!done && (
            <div className="hidden lg:block">
              <ProgressCard detail={detail} totalOverride={streamTotal} onCancel={() => void act(() => cancelTask(t.id))} />
            </div>
          )}
          <FilesCard task={t} content={subtitleText} onCopy={() => void copySubtitle()} copyState={copyState} onReveal={() => void act(() => revealPath(t.out_dir as string))} />
          {(t.txt_path || t.srt_path) && (
            <div className="px-1">
              <button type="button" aria-expanded={showPaths} onClick={() => setShowPaths((value) => !value)} className="inline-flex min-h-8 items-center gap-1 py-1.5 text-xs text-mute hover:text-ink">
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

/** 全局设置：热词、总结模型与密钥对所有任务生效，不该只能从某条历史里进。 */
function SettingsPage() {
  const [keyFields, setKeyFields] = useState<KeyField[]>(() => boot().status.key_fields)
  useEffect(() => {
    document.title = '设置 · 转录'
    // 侧栏的当前页标记：设置页与任务页共用同一个外壳，只能在挂载后补
    const link = document.querySelector<HTMLAnchorElement>('aside a[href="/settings"]')
    link?.setAttribute('aria-current', 'page')
    return () => link?.removeAttribute('aria-current')
  }, [])
  return (
    <div className="space-y-6 pb-10">
      <div className="task-intro">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex h-2 w-2 shrink-0 rounded-full bg-ink" aria-hidden="true" />
          <span className="eyebrow-mono">全局设置</span>
        </div>
        <h1 className="mt-3 text-2xl leading-9 tracking-display text-ink sm:text-3xl">设置</h1>
        <p className="mt-2 text-xs text-mute">密钥、模型、提示词和热词对所有转录任务生效。</p>
      </div>
      <div className="workbench-card overflow-hidden">
        <section aria-label="密钥设置" className="p-5 sm:p-6">
          <h2 className="text-sm text-ink">密钥</h2>
          <p className="mt-2 text-xs leading-5 text-mute">
            在线转录与 Agent 总结用的密钥都保存在本机；页面只显示「已配置」和尾号。
            保存后在线引擎立即可用。
          </p>
          <div className="mt-4">
            <KeyFieldsPanel fields={keyFields} onRefresh={(next) => setKeyFields(next.key_fields)} />
          </div>
        </section>
      </div>
      <div className="workbench-card overflow-hidden">
        <SummarySettingsEditor />
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
      {window.location.pathname.replace(/\/+$/, '') === '/settings' ? <SettingsPage /> : task ? <Detail key={task.task.id} initial={task} animate={switched} /> : (
        <div className="workbench-card px-6 py-12 text-center">
          <p className="eyebrow-mono">未找到</p>
          <p className="mt-2 text-sm text-body">没有这个任务。<a href="/" className="text-ink underline-offset-4 hover:underline">返回控制台</a></p>
        </div>
      )}
    </>
  )
}

const rootEl = document.getElementById('root')
if (rootEl) createRoot(rootEl).render(<TaskPage />)
