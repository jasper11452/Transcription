// 历史任务按本地日历日分组：今天 / 昨天 / 本周 / 更早。
// created_at 是带时区偏移的 ISO 串（store.py 用 datetime.now(UTC).isoformat），
// 所以这里只做本地日零点相减，不碰字符串切片。

import type { Task } from './types'

export interface TaskGroup {
  key: string
  label: string
  items: Task[]
}

const DAY_MS = 86_400_000

/** 本地日零点的时间戳：用它相减，跨夏令时也能按「天」落桶 */
function dayStart(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
}

const LABELS = ['今天', '昨天', '本周', '更早'] as const

export function groupTasks(tasks: Task[], now: Date = new Date()): TaskGroup[] {
  const today = dayStart(now)
  const buckets: Task[][] = [[], [], [], []]
  for (const task of tasks) {
    const at = new Date(task.created_at).getTime()
    // 解析不出来（脏数据）就归「更早」，不让一条坏记录把整栏打空
    const days = Number.isNaN(at) ? Number.POSITIVE_INFINITY : Math.round((today - dayStart(new Date(at))) / DAY_MS)
    buckets[days <= 0 ? 0 : days === 1 ? 1 : days <= 6 ? 2 : 3].push(task)
  }
  return buckets
    .map((items, index) => ({ key: ['today', 'yesterday', 'week', 'earlier'][index], label: LABELS[index], items }))
    .filter((group) => group.items.length > 0)
}
