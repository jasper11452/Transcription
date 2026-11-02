// 控制台：静态骨架（index.html）是唯一的表单真相，React 只负责引擎下拉、
// 热词库、共享的侧栏历史岛和表单行为。密钥配置在设置页。
// boot 状态已内联进 HTML，首屏无等待。

import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createPortal } from 'react-dom'
import '@/index.css'
import { HistorySidebar } from '@/components/history-sidebar'
import { boot, type EngineEntry, type HotWordGroup, type StatusPayload } from '@/lib/types'
import { createTask, fetchSummarySettings } from '@/lib/api'

const fmtDur = (seconds: number) => {
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

/** 引擎下拉的选项（portal 进静态 <select id="onlineEngine">） */
function EngineOptions({ engines }: { engines: EngineEntry[] }) {
  return createPortal(
    <>
      {engines.map((e) => (
        <option key={e.id} value={e.id} disabled={!e.ready}>
          {e.short_label ?? e.label}
          {e.ready ? '' : `（缺 ${e.needs_key.map((k) => k.toUpperCase()).join('、')}）`}
        </option>
      ))}
    </>,
    document.getElementById('onlineEngine') as HTMLElement,
  )
}

/** 初始页的热词库：按 `## 组名` 展示，只读；增删改统一去设置页。 */
function HotWordsPanel() {
  const [groups, setGroups] = useState<HotWordGroup[] | null>(null)
  const [allWords, setAllWords] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetchSummarySettings()
      .then((next) => {
        if (!active) return
        setGroups(next.hot_word_groups ?? [])
        setAllWords(next.hot_words ?? [])
      })
      .catch((err) => {
        if (!active) return
        setGroups([])
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (active) document.getElementById('hotWordsSection')?.removeAttribute('hidden')
      })
    return () => {
      active = false
    }
  }, [])

  const grouped = (groups ?? []).filter((group) => group.words.length)
  // 老词表只有 `错词 -> 正确词` 时没有基热词行：把这些正确写法当作未分组展示，不然库看起来是空的。
  const visible = grouped.length ? grouped : allWords.length ? [{ name: '', words: allWords }] : []
  const total = visible.reduce((sum, group) => sum + group.words.length, 0)

  useEffect(() => {
    const meta = document.getElementById('hotWordsMeta')
    if (!meta) return
    meta.textContent =
      groups === null ? '正在读取…' : `${total} 个词 · ${visible.length} 个分组`
  }, [groups, total, visible.length])

  if (!document.getElementById('hotWords')) return null
  return createPortal(
    error ? (
      <p className="text-xs leading-5 text-mute">热词库读取失败：{error}</p>
    ) : groups === null ? (
      <p className="text-xs text-mute">正在读取本机词表…</p>
    ) : visible.length ? (
      <div className="space-y-4">
        {visible.map((group) => (
          <div key={group.name || '__ungrouped'}>
            <p className="group-label flex items-baseline gap-2">
              {group.name || '未分组'}
              <span className="font-mono text-[11px] text-mute">{group.words.length}</span>
            </p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {group.words.map((word) => (
                <li
                  key={word}
                  className="rounded-md bg-surface-selected px-2 py-1 font-mono text-[11px] text-body"
                >
                  {word}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    ) : (
      <p className="text-xs leading-5 text-mute">
        还没有热词。到「设置」里按分组添加专名，转录时作为提示，Agent 总结也会统一写法。
      </p>
    ),
    document.getElementById('hotWords') as HTMLElement,
  )
}

export default function ConsoleApp() {
  const initial = useRef(boot().status)
  const status: StatusPayload = initial.current
  const submitting = useRef(false)

  useEffect(() => {
    // 静态骨架默认离线（产品默认）；boot 里带回来的默认值优先
    const d = initial.current.defaults
    const lever = document.getElementById('modeLever')
    const radios = lever?.querySelectorAll<HTMLInputElement>('input[name="mode"]')
    radios?.forEach((r) => {
      if (r.value === d.mode) r.checked = true
    })
    // 密钥统一在设置页维护：这里不再因 hash 自动切在线，也不再显示密钥面板。
    const artifact = document.querySelector<HTMLInputElement>(
      `input[name="artifact"][value="${d.artifact}"]`,
    )
    if (artifact) artifact.checked = true
    const lang = document.getElementById('language') as HTMLSelectElement | null
    if (lang) lang.value = d.language
    const engine = document.getElementById('onlineEngine') as HTMLSelectElement | null
    if (engine) engine.value = d.online_engine
    syncMode()
  }, [])

  const syncMode = () => {
    const checked = document.querySelector<HTMLInputElement>('input[name="mode"]:checked')
    const online = checked?.value === 'online'
    const engineField = document.getElementById('engineField')
    if (engineField) engineField.hidden = !online
    if (online) {
      const advanced = engineField?.closest('details')
      if (advanced) advanced.open = true
    }
    const hint = document.getElementById('modeHint')
    if (hint) {
      hint.textContent = online
        ? '上传音频到云端引擎，按量计费；密钥在「设置」里配置。'
        : '本机跑，不联网，不花钱。'
    }
    const submit = document.getElementById('submit') as HTMLButtonElement | null
    if (submit) submit.textContent = online ? '开始在线转录' : '开始离线转录'
  }

  useEffect(() => {
    const lever = document.getElementById('modeLever')
    const onChange = () => syncMode()
    lever?.addEventListener('change', onChange)
    return () => lever?.removeEventListener('change', onChange)
  }, [])

  // 引擎下拉里只有短名；限制和费用按所选引擎展开，长说明不再被 select 截断。
  useEffect(() => {
    const select = document.getElementById('onlineEngine') as HTMLSelectElement | null
    const hint = document.getElementById('engineHint')
    if (!select || !hint) return
    const render = () => {
      const entry = status.online_engines.find((item) => item.id === select.value)
      if (!entry) {
        hint.textContent = ''
        return
      }
      if (entry.id === 'auto') {
        hint.textContent = '按产物自动选择：txt → 百炼，srt → OpenRouter。'
        return
      }
      const limit = entry.max_chunk_s ? `单次上限 ${Math.round(entry.max_chunk_s)} 秒` : '无单次上限'
      hint.textContent = entry.cost ? `${limit} · ${entry.cost}` : limit
    }
    select.addEventListener('change', render)
    render()
    return () => select.removeEventListener('change', render)
  }, [status.online_engines])

  // 在线 + 本机路径时给时长/费用预估：界面承诺「按量计费」就该在提交前给出数字。
  useEffect(() => {
    const pathInput = document.getElementById('sourcePath') as HTMLInputElement | null
    const fileInput = document.getElementById('file') as HTMLInputElement | null
    const lever = document.getElementById('modeLever')
    const engineSelect = document.getElementById('onlineEngine') as HTMLSelectElement | null
    const hint = document.getElementById('estimateHint')
    if (!pathInput || !lever || !hint) return
    let timer: number | undefined
    let seq = 0

    const clear = () => {
      hint.hidden = true
      hint.textContent = ''
    }

    const run = async () => {
      const online =
        (document.querySelector<HTMLInputElement>('input[name="mode"]:checked')?.value ?? 'offline') === 'online'
      const path = pathInput.value.trim()
      // 选中的文件会在提交时才上传，本机预估只能基于已经存在的路径。
      if (!online || !path || fileInput?.files?.length) {
        clear()
        return
      }
      const gen = ++seq
      const body = new FormData()
      body.append('source_path', path)
      body.append('mode', 'online')
      body.append('artifact', 'srt')
      if (engineSelect) body.append('online_engine', engineSelect.value)
      try {
        const res = await fetch('/api/estimate', { method: 'POST', body })
        const data = (await res.json()) as {
          ok?: boolean
          error?: string
          duration_s?: number
          estimated_cost_usd?: number
        }
        if (gen !== seq) return
        if (!data.ok || typeof data.duration_s !== 'number') {
          hint.hidden = false
          hint.textContent = data.error ? `无法预估：${data.error}` : '无法预估这个路径。'
          return
        }
        const cost = typeof data.estimated_cost_usd === 'number' ? data.estimated_cost_usd : null
        const costText = cost === null ? '' : cost === 0 ? ' · 免费' : ` · 费用约 $${cost < 0.01 ? cost.toFixed(3) : cost.toFixed(2)}`
        hint.hidden = false
        hint.textContent = `预计 ${fmtDur(data.duration_s)}${costText}（按实际用量计费）`
      } catch {
        if (gen === seq) clear()
      }
    }

    const schedule = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = window.setTimeout(run, 500)
    }
    pathInput.addEventListener('input', schedule)
    fileInput?.addEventListener('change', schedule)
    lever.addEventListener('change', schedule)
    engineSelect?.addEventListener('change', schedule)
    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      pathInput.removeEventListener('input', schedule)
      fileInput?.removeEventListener('change', schedule)
      lever.removeEventListener('change', schedule)
      engineSelect?.removeEventListener('change', schedule)
    }
  }, [])

  // 拖入文件是 macOS 上最顺手的动作：把 drop 直接写回 file input
  useEffect(() => {
    const zone = document.getElementById('dropZone')
    const input = document.getElementById('file') as HTMLInputElement | null
    const hint = document.getElementById('fileHint')
    const formError = document.getElementById('formError')
    if (!zone || !input || !hint) return
    const idle = hint.textContent ?? ''
    // 预览用的 blob URL 必须在换文件时放掉，否则几百 MB 的视频会一直被钉在内存里
    let objectUrl = ''
    const clearFormError = () => {
      if (formError) {
        formError.hidden = true
        formError.textContent = ''
      }
    }
    const showName = () => {
      clearFormError()
      const f = input.files?.[0]
      hint.textContent = f ? f.name + ' · ' + (f.size / 1024 / 1024).toFixed(1) + ' MB' : idle
      const preview = document.getElementById('mediaPreview')
      if (!preview) return
      preview.innerHTML = ''
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = '' }
      if (!f) { preview.hidden = true; return }
      objectUrl = URL.createObjectURL(f)
      const media = document.createElement(f.type.startsWith('video/') ? 'video' : 'audio')
      media.src = objectUrl; media.controls = true; media.className = 'media-preview'
      preview.appendChild(media); preview.hidden = false
    }
    const onDragOver = (e: DragEvent) => {
      e.preventDefault()
      zone.dataset.drag = '1'
    }
    const onDragLeave = () => { delete zone.dataset.drag }
    const onDrop = (e: DragEvent) => {
      e.preventDefault()
      delete zone.dataset.drag
      const f = e.dataTransfer?.files?.[0]
      if (!f) return
      const dt = new DataTransfer()
      dt.items.add(f)
      input.files = dt.files
      showName()
    }
    zone.addEventListener('dragover', onDragOver)
    zone.addEventListener('dragleave', onDragLeave)
    zone.addEventListener('drop', onDrop)
    input.addEventListener('change', showName)
    const pathInput = document.getElementById('sourcePath')
    const onPathInput = () => clearFormError()
    pathInput?.addEventListener('input', onPathInput)
    return () => {
      zone.removeEventListener('dragover', onDragOver)
      zone.removeEventListener('dragleave', onDragLeave)
      zone.removeEventListener('drop', onDrop)
      input.removeEventListener('change', showName)
      pathInput?.removeEventListener('input', onPathInput)
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [])

  const onSubmit = async (ev: Event) => {
    ev.preventDefault()
    if (submitting.current) return
    const submit = document.getElementById('submit') as HTMLButtonElement
    const fileInput = document.getElementById('file') as HTMLInputElement
    const pathInput = document.getElementById('sourcePath') as HTMLInputElement
    const formError = document.getElementById('formError')
    const mode = document.querySelector<HTMLInputElement>('input[name="mode"]:checked')?.value ?? 'offline'
    const artifact = 'srt'
    const language = (document.getElementById('language') as HTMLSelectElement).value
    const engine = (document.getElementById('onlineEngine') as HTMLSelectElement).value

    const fail = (message: string) => {
      if (formError) {
        formError.textContent = message
        formError.hidden = false
      }
    }
    if (formError) {
      formError.hidden = true
      formError.textContent = ''
    }

    // 没有输入就提交，只会在服务端绕一圈再报 400；先在本地说清楚缺什么。
    if (!fileInput.files?.[0] && !pathInput.value.trim()) {
      fail('先选择一个音视频文件，或填写本机路径。')
      pathInput.focus()
      return
    }

    const fd = new FormData()
    fd.append('mode', mode)
    fd.append('artifact', artifact)
    fd.append('language', language)
    fd.append('online_engine', engine)
    if (fileInput.files?.[0]) {
      fd.append('file', fileInput.files[0])
    } else if (pathInput.value.trim()) {
      fd.append('source_path', pathInput.value.trim())
    }

    submitting.current = true
    submit.disabled = true
    const idleLabel = submit.textContent ?? '开始转录'
    // 上传/建任务至少要几百毫秒：按钮先给出“收到了”的反馈，再让换页动效接管。
    submit.textContent = '提交中…'
    submit.classList.add('is-busy')
    submit.setAttribute('aria-busy', 'true')
    try {
      const { task_id } = await createTask(fd)
      // 提交成功直接进详情页：进度、实时字幕和停止都在那里，不在控制台再摆一套。
      window.location.assign(`/t/${task_id}`)
    } catch (e) {
      submitting.current = false
      submit.disabled = false
      submit.textContent = idleLabel
      submit.classList.remove('is-busy')
      submit.removeAttribute('aria-busy')
      fail(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    const form = document.getElementById('taskForm')
    form?.addEventListener('submit', onSubmit)
    return () => {
      form?.removeEventListener('submit', onSubmit)
    }
  }, [])

  // 首次使用（没有历史）时给出离线模型、产物位置和密钥的三条说明。
  useEffect(() => {
    const tasks = boot().tasks
    if (tasks && tasks.length === 0) document.getElementById('firstRun')?.removeAttribute('hidden')
  }, [])

  return (
    <>
      <EngineOptions engines={status.online_engines} />
      <HotWordsPanel />
      <HistorySidebar />
    </>
  )
}

// 静态壳 + 动态岛：岛渲染进 #root，再由 portal 落到各容器
const rootEl = document.getElementById('root')
if (rootEl) createRoot(rootEl).render(<ConsoleApp />)
