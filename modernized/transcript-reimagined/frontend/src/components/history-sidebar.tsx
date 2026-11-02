// 左侧栏的历史岛：控制台和详情页共用同一份实现，portal 进静态骨架的 #taskList。
// 滚动交给栏本身（aside 是 lg:h-dvh + min-h-0），这里只负责行内容。

import { useEffect, useState } from 'react'
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
  // Q10：中断状态由服务端给出（running + 无活进程），前端不再自己推断。
  return {
    label: t.cancelling ? '停止中' : t.interrupted ? '已中断' : (STATUS_LABEL[t.status] ?? t.status),
    dot:
      t.status === 'done'
        ? 'bg-ink'
        : t.status === 'failed'
          ? 'bg-destructive'
          : t.running || t.cancelling
            ? 'animate-pulse bg-sunset'
            : 'bg-mute',
  }
}

// 删除是永久动作（只删记录、不动文件）：先点变确认，4 秒不点自动退回
function DeleteButton({ id, onRemove }: { id: number; onRemove: (id: number) => void }) {
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
      aria-label={confirming ? '确认删除' : '删除'}
      title={confirming ? '确认删除' : '删除'}
      className={cn('h-8 w-8 text-mute hover:text-ink', confirming && 'text-destructive hover:text-destructive')}
      onClick={() => (confirming ? onRemove(id) : setConfirming(true))}
    >
      {confirming ? <Check size={15} /> : <Trash2 size={15} />}
    </Button>
  )
}

/** 历史任务岛：宽屏常驻左侧栏，窄屏在栏落回顶部后限高内滚 */
export function HistorySidebar({ currentId }: { currentId?: number }) {
  // 首帧就用内联的任务表：省掉「加载中…」那一屏，也免了列表到达时整栏换掉。
  // 没内联（旧产物/测试桩）就回落到自己拉。
  const [tasks, setTasks] = useState<Task[] | null>(() => boot().tasks ?? null)

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

  const remove = async (id: number) => {
    try {
      await deleteTask(id)
      setTasks((list) => list?.filter((t) => t.id !== id) ?? null)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    }
  }

  // Q6：点停止先乐观进入「停止中」，不要等下一轮轮询才有反馈。
  // 失败时用服务端的列表恢复，错误照旧说出来。
  const cancel = async (id: number) => {
    setTasks((list) => list?.map((t) => (t.id === id ? { ...t, cancelling: true } : t)) ?? null)
    try {
      await cancelTask(id)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
      try {
        setTasks(await fetchTasks(50))
      } catch {
        /* 恢复失败就保持原样，下一轮轮询会纠正 */
      }
    }
  }

  const el = document.getElementById('taskList')
  if (!el) return null

  return createPortal(
    tasks === null ? (
      <p className="flex items-center gap-2 px-3 py-2 text-sm text-mute">
        <LoaderCircle size={14} className="animate-spin" />
        加载中…
      </p>
    ) : tasks.length === 0 ? (
      <p className="px-3 py-2 text-sm text-mute">还没有任务。</p>
    ) : (
      groupTasks(tasks).map((group) => (
        <div key={group.key} className="mt-5 first:mt-0">
          <p className="eyebrow-mono px-3 pb-2">{group.label}</p>
          <ul className="space-y-0.5">
            {group.items.map((t) => {
              const status = statusOf(t)
              const active = t.id === currentId
              return (
                <li
                  key={t.id}
                  className={cn('group flex items-center gap-0.5 rounded-lg pr-1', active ? 'bg-surface-selected' : 'hover:bg-surface-hover')}
                >
                  <a
                    className="min-w-0 flex-1 rounded-lg px-3 py-2"
                    href={`/t/${t.id}`}
                    aria-current={active ? 'page' : undefined}
                  >
                    <span className="block truncate text-sm text-ink">{t.title || t.source_name}</span>
                    <span className="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-mute">
                      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', status.dot)} />
                      {status.label}
                      <span className="truncate">
                        · {t.mode === 'online' ? '在线' : '离线'}
                        {t.running ? ` ${Math.round(t.progress)}%` : ''}
                        {t.duration_s ? ` · ${fmtDur(t.duration_s)}` : ''}
                      </span>
                    </span>
                  </a>
                  <div className="flex shrink-0 items-center opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100">
                    {t.running ? (
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label="停止"
                        title="停止"
                        className="h-8 w-8 text-mute hover:text-ink"
                        onClick={() => cancel(t.id)}
                      >
                        <StopCircle size={15} />
                      </Button>
                    ) : (
                      <DeleteButton id={t.id} onRemove={remove} />
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      ))
    ),
    el,
  )
}
