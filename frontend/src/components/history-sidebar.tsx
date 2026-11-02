// 左侧栏的历史岛：控制台和详情页共用同一份实现，portal 进静态骨架的 #taskList。
// 滚动交给栏本身（aside 是 lg:h-dvh + min-h-0），这里只负责行内容。

import { type PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, LoaderCircle, StopCircle, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { boot, type Task } from '@/lib/types'
import { cancelTask, deleteTask, fetchTasks } from '@/lib/api'
import { groupTasks } from '@/lib/task-groups'

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '转录中',
  done: '已完成',
  failed: '失败',
}

const fmtDur = (s?: number | null) => {
  if (!s) return '—'
  const total = Math.round(s)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

function statusOf(t: Task) {
  // 库里是 running 但没有活动进程 → 这是一次没跑完的中断，别装作还在转录
  const interrupted = t.status === 'running' && !t.running && !t.cancelling
  return {
    label: t.cancelling ? '停止中' : interrupted ? '已中断' : (STATUS_LABEL[t.status] ?? t.status),
    dot:
      t.status === 'done'
        ? 'bg-ink'
        : t.status === 'failed'
          ? 'bg-destructive'
          : t.running || t.cancelling
            ? 'status-breathe bg-sunset'
            : 'bg-mute',
  }
}

// 删除是永久动作（只删记录、不动文件）：先点变确认，4 秒不点自动退回
function DeleteButton({ id, name, onRemove }: { id: number; name: string; onRemove: (id: number) => void }) {
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (!confirming) return
    const timer = setTimeout(() => setConfirming(false), 4000)
    return () => clearTimeout(timer)
  }, [confirming])
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      aria-label={confirming ? `确认删除 ${name}` : `删除 ${name}`}
      title={confirming ? '确认删除' : '删除'}
      className={cn('h-11 w-11 text-mute hover:text-ink', confirming && 'text-destructive hover:text-destructive')}
      onClick={() => (confirming ? onRemove(id) : setConfirming(true))}
    >
      {confirming ? <Check size={15} /> : <Trash2 size={15} />}
    </Button>
  )
}

/** 行内操作：触屏滑动露出与桌面 hover 覆盖共用这一份实现。 */
function RowAction({
  task,
  onCancel,
  onRemove,
}: {
  task: Task
  onCancel: (id: number) => void
  onRemove: (id: number) => void
}) {
  return task.running ? (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      aria-label="停止"
      title="停止"
      className="h-11 w-11 text-mute hover:text-ink"
      onClick={() => onCancel(task.id)}
    >
      <StopCircle size={15} />
    </Button>
  ) : (
    <DeleteButton id={task.id} name={task.title || task.source_name} onRemove={onRemove} />
  )
}

/** 显式操作区的宽度：一个 44px 按钮 + 行右内边距。 */
const REVEAL = 76

/** 历史任务岛：宽屏常驻左侧栏，窄屏在栏落回顶部后限高内滚 */
export function HistorySidebar({ currentId }: { currentId?: number }) {
  // 首帧就用内联的任务表：省掉「加载中…」那一屏，也免了列表到达时整栏换掉。
  // 没内联（旧产物/测试桩）就回落到自己拉。
  const [tasks, setTasks] = useState<Task[] | null>(() => boot().tasks ?? null)
  const [query, setQuery] = useState('')
  // 删/停失败用行内提示，不用阻塞式 alert
  const [actionError, setActionError] = useState('')
  // 滑动露出操作：一次只开一行；鼠标走 hover，不动位移。
  const [revealed, setRevealed] = useState<number | null>(null)
  const [drag, setDrag] = useState<{ id: number; dx: number } | null>(null)
  const gesture = useRef<{ id: number; x: number; y: number; base: number; active: boolean } | null>(null)
  const offset = useRef(0)
  const justSwiped = useRef(0)
  const searchRef = useRef<HTMLInputElement>(null)

  // `/` 直接聚焦历史搜索：切任务是这一页最高频的动作，不该先去点输入框。
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      event.preventDefault()
      searchRef.current?.focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const list = await fetchTasks(50)
        if (!alive) return
        setTasks(list)
        const busy = list.some((t) => t.running || t.cancelling || !t.is_terminal)
        timer = setTimeout(tick, busy ? 2000 : 10000)
      } catch {
        if (alive) timer = setTimeout(tick, 10000)
      }
    }
    tick()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])

  // 手机上历史默认收起：第一次进来先看到任务正文。展开态不持久化，切页重来一次。
  useEffect(() => {
    const toggle = document.getElementById('historyToggle')
    const panel = document.getElementById('historyPanel')
    if (!toggle || !panel) return
    const onClick = () => {
      const open = panel.dataset.open === '1'
      if (open) delete panel.dataset.open
      else panel.dataset.open = '1'
      toggle.setAttribute('aria-expanded', String(!open))
    }
    toggle.addEventListener('click', onClick)
    return () => toggle.removeEventListener('click', onClick)
  }, [])

  useEffect(() => {
    const label = tasks ? `${tasks.length}${tasks.length >= 50 ? '+' : ''}` : ''
    document.querySelectorAll('.history-count').forEach((el) => { el.textContent = label })
  }, [tasks])

  const remove = async (id: number) => {
    setActionError('')
    try {
      await deleteTask(id)
      setTasks((list) => list?.filter((t) => t.id !== id) ?? null)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  // 停止失败要说出来：静默吞掉的话，行会继续显示「转录中」，看着像按钮没反应
  const cancel = async (id: number) => {
    setActionError('')
    try {
      await cancelTask(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const el = document.getElementById('taskList')

  const startSwipe = (event: ReactPointerEvent<HTMLDivElement>, id: number) => {
    if (event.pointerType === 'mouse') return
    const base = revealed === id ? -REVEAL : 0
    gesture.current = { id, x: event.clientX, y: event.clientY, base, active: false }
    offset.current = base
  }

  const moveSwipe = (event: ReactPointerEvent<HTMLDivElement>) => {
    const current = gesture.current
    if (!current) return
    const dx = event.clientX - current.x
    const dy = event.clientY - current.y
    if (!current.active) {
      // Telegram 的 2:1 仲裁：纵向意图更强就还给滚动，不抢手势
      if (Math.abs(dx) > Math.abs(dy) * 2 && Math.abs(dx) > 2) {
        current.active = true
        event.currentTarget.setPointerCapture?.(event.pointerId)
      } else if (Math.abs(dy) > 2) {
        gesture.current = null
        return
      } else {
        return
      }
    }
    offset.current = Math.min(0, Math.max(-REVEAL, current.base + dx))
    setDrag({ id: current.id, dx: offset.current })
  }

  const endSwipe = () => {
    const current = gesture.current
    gesture.current = null
    if (!current?.active) { setDrag(null); return }
    justSwiped.current = Date.now()
    // 越过 30% 才打开，10% 以内回弹；中间地带保持原状（同 Telegram 的 trigger/reset progress）
    if (offset.current <= -REVEAL * 0.3) setRevealed(current.id)
    else if (offset.current >= -REVEAL * 0.1) setRevealed(null)
    setDrag(null)
  }

  // 点行内以外的地方、或按 Esc，收起露出的操作
  useEffect(() => {
    if (revealed === null) return
    const close = (event: Event) => {
      const target = event.target as Element | null
      if (target?.closest?.('[data-swipe-row]')) return
      setRevealed(null)
    }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setRevealed(null) }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', onKey)
    }
  }, [revealed])

  if (!el) return null

  const needle = query.trim().toLowerCase()
  const filtered = needle && tasks
    ? tasks.filter((t) =>
        [t.title, t.source_name].some((value) => (value ?? '').toLowerCase().includes(needle)),
      )
    : tasks
  const groups = filtered ? groupTasks(filtered) : []
  const showSearch = (tasks?.length ?? 0) >= 6

  return createPortal(
    <>
      {actionError && (
        <p role="alert" className="mb-2 rounded-lg border border-destructive/40 px-3 py-2 text-xs leading-5 text-destructive [overflow-wrap:anywhere]">{actionError}</p>
      )}
      {showSearch && (
        <div className="sticky top-0 z-10 hidden bg-canvas pb-2 lg:block">
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Escape') return
              setQuery('')
              event.currentTarget.blur()
            }}
            placeholder="搜索任务…（/）"
            aria-label="搜索历史任务"
            className="h-9 w-full rounded-lg border border-hairline bg-canvas-soft px-3 text-sm text-foreground placeholder:text-mute focus:border-canvas-mid focus:outline-none"
          />
        </div>
      )}
      {tasks === null ? (
        <p className="flex items-center gap-2 px-3 py-2 text-sm text-mute">
          <LoaderCircle size={14} className="animate-spin" />
          加载中…
        </p>
      ) : tasks.length === 0 ? (
        <p className="px-3 py-2 text-sm text-mute">还没有任务。拖入一个文件开始第一次转录。</p>
      ) : groups.length === 0 ? (
        <p className="px-3 py-2 text-sm text-mute">没有匹配的任务。</p>
      ) : (
        groups.map((group) => (
        <div key={group.key} className="mt-5 first:mt-0">
          <p className="group-label px-2 pb-2">{group.label}</p>
          <ul className="space-y-0.5">
            {group.items.map((t) => {
              const status = statusOf(t)
              const active = t.id === currentId
              const opened = revealed === t.id
              const dx = drag?.id === t.id ? drag.dx : opened ? -REVEAL : 0
              return (
                <li key={t.id} data-swipe-row className="group relative overflow-hidden rounded-lg">
                  {/* 底层：滑动露出的操作。内容层不透明，盖住它就是“收起”。 */}
                  <div className="absolute inset-y-0 right-0 z-0 flex items-center pr-1" onFocus={() => setRevealed(t.id)}>
                    <RowAction task={t} onCancel={cancel} onRemove={remove} />
                  </div>
                  <div
                    className={cn(
                      'relative flex items-center gap-0.5 rounded-lg bg-canvas pr-1',
                      !drag && 'transition-transform duration-[260ms]',
                      active && 'bg-surface-selected',
                      !active && 'hover:bg-surface-hover',
                    )}
                    style={{
                      transform: `translateX(${dx}px)`,
                      transitionTimingFunction: 'cubic-bezier(0.38, 0.7, 0.125, 1)',
                      touchAction: 'pan-y',
                    }}
                    onPointerDown={(event) => startSwipe(event, t.id)}
                    onPointerMove={moveSwipe}
                    onPointerUp={endSwipe}
                    onPointerCancel={endSwipe}
                  >
                  <a
                    className="min-w-0 flex-1 rounded-lg px-2 py-2"
                    href={`/t/${t.id}`}
                    title={t.title || t.source_name}
                    aria-current={active ? 'page' : undefined}
                    onClick={(event) => {
                      // 刚滑完的那一下不算点击；点在已露出的行上先收起，不跳转
                      if (Date.now() - justSwiped.current < 400 || revealed === t.id) {
                        event.preventDefault()
                        setRevealed(null)
                      }
                    }}
                  >
                    <span className="block truncate text-sm text-ink">{t.title || t.source_name}</span>
                    <span className="mt-1 flex items-center gap-1.5 font-mono text-xs text-mute">
                      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', status.dot)} />
                      {status.label}
                      <span className="truncate">
                        · {t.mode === 'online' ? '在线' : '离线'}
                        {t.running ? ` ${Math.round(t.progress)}%` : ''}
                        {t.duration_s ? ` · ${fmtDur(t.duration_s)}` : ''}
                      </span>
                    </span>
                  </a>
                  {/* 桌面：hover / 键盘聚焦时覆盖在右缘，不需要滑动 */}
                  <div
                    className="hidden shrink-0 items-center bg-canvas opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 lg:flex"
                    onFocus={() => setRevealed(t.id)}
                  >
                    <RowAction task={t} onCancel={cancel} onRemove={remove} />
                  </div>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
        ))
      )}
    </>,
    el,
  )
}
