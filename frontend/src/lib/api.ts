// 轻量 API 客户端：所有后端契约（{"error": ...}、"tasks" 包裹）在这里适配。

import type {
  StatusPayload,
  SummaryModelListPayload,
  SummaryPayload,
  SummarySettingsPayload,
  Task,
  TaskDetail,
} from './types'

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = (body as { error?: string }).error || `请求失败（${res.status}）`
    throw new Error(msg)
  }
  return body as T
}

export async function fetchTasks(limit = 20): Promise<Task[]> {
  const body = await parse<{ tasks: Task[] }>(
    await fetch(`/api/tasks?limit=${limit}`),
  )
  return body.tasks
}

export async function fetchTaskDetail(id: number): Promise<TaskDetail> {
  return parse<TaskDetail>(await fetch(`/api/tasks/${id}`))
}

export async function createTask(form: FormData): Promise<{ task_id: number }> {
  return parse<{ task_id: number }>(
    await fetch('/api/tasks', { method: 'POST', body: form }),
  )
}

export async function cancelTask(id: number): Promise<void> {
  await parse(await fetch(`/api/tasks/${id}/cancel`, { method: 'POST' }))
}

export async function resumeTask(id: number): Promise<void> {
  await parse(await fetch(`/api/tasks/${id}/resume`, { method: 'POST' }))
}

export async function deleteTask(id: number): Promise<void> {
  await parse(await fetch(`/api/tasks/${id}`, { method: 'DELETE' }))
}

export async function revealPath(path: string): Promise<void> {
  const form = new FormData()
  form.append('path', path)
  await parse(await fetch('/api/reveal', { method: 'POST', body: form }))
}

export async function fetchOutput(id: number, kind: 'txt' | 'srt'): Promise<string> {
  const res = await fetch(`/api/tasks/${id}/output/file?kind=${kind}`)
  if (!res.ok) await parse(res)
  return res.text()
}

export async function fetchSummarySettings(): Promise<SummarySettingsPayload> {
  return parse(await fetch('/api/summary-settings'))
}

export async function saveSummarySettings(payload: {
  model: string
  base_url: string
  api_key?: string
  prompt: string
  hot_words: string[]
}): Promise<SummarySettingsPayload> {
  return parse(
    await fetch('/api/summary-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}

export async function fetchSummaryModels(refresh = false): Promise<SummaryModelListPayload> {
  return parse(await fetch(`/api/summary-models${refresh ? '?refresh=1' : ''}`))
}

export async function fetchSummary(id: number): Promise<SummaryPayload> {
  return parse(await fetch(`/api/tasks/${id}/summary`))
}

export async function enableSummary(id: number): Promise<SummaryPayload> {
  return parse(await fetch(`/api/tasks/${id}/summary`, { method: 'POST' }))
}

export async function saveCredentials(payload: {
  keys?: Record<string, string>
  clear?: string[]
}): Promise<Pick<StatusPayload, 'credentials' | 'key_fields' | 'online_engines'>> {
  return parse(
    await fetch('/api/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}
