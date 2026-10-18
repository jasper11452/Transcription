// 控制台：静态骨架（index.html）是唯一的表单真相，React 只负责两块动态岛
// （引擎下拉、密钥面板）、共享的侧栏历史岛和表单行为。boot 状态已内联进 HTML，首屏无等待。

import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createPortal } from 'react-dom'
import '@/index.css'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { HistorySidebar } from '@/components/history-sidebar'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { boot, type EngineEntry, type KeyField, type StatusPayload } from '@/lib/types'
import { createTask, saveCredentials, saveDiarSetting } from '@/lib/api'

/** 引擎下拉的选项（portal 进静态 <select id="onlineEngine">） */
function EngineOptions({ engines }: { engines: EngineEntry[] }) {
  return createPortal(
    <>
      {engines.map((e) => (
        <option key={e.id} value={e.id} disabled={!e.ready}>
          {e.label}
          {e.ready ? '' : `（缺 ${e.needs_key.map((k) => k.toUpperCase()).join('、')}）`}
        </option>
      ))}
    </>,
    document.getElementById('onlineEngine') as HTMLElement,
  )
}

/** 在线密钥面板：显示掩码状态，支持填写/清除 */
function KeyFieldsPanel({
  fields,
  onRefresh,
}: {
  fields: KeyField[]
  onRefresh: (s: Pick<StatusPayload, 'credentials' | 'key_fields' | 'online_engines'>) => void
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)

  const save = async (attr: string, clear = false) => {
    setMsg(null)
    const value = (values[attr] ?? '').trim()
    if (!clear && !value) {
      // Q1：空输入是无操作，不是写入空值（空值会摧毁正在用的凭据）。
      setMsg('请先输入密钥')
      return
    }
    try {
      const payload = clear
        ? { clear: [attr] }
        : { keys: { [attr]: value } }
      const res = await saveCredentials(payload)
      onRefresh(res)
      setValues((v) => ({ ...v, [attr]: '' }))
      setMsg(clear ? '已清除' : '已保存')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  if (!fields.length) {
    return createPortal(<p className="text-sm text-mute">在线模式暂不需要密钥。</p>, document.getElementById('keyFields') as HTMLElement)
  }
  return createPortal(
    <div>
      <div className="divide-y divide-hairline">
        {fields.map((f) => (
          <div key={f.attr} className="flex flex-wrap items-center gap-x-5 gap-y-3 py-4 first:pt-0 last:pb-0">
            <div className="w-44 shrink-0">
              <p className="text-sm text-ink">{f.label}</p>
              <p className="mt-1 font-mono text-[11px] tracking-[0.08em] text-mute">{f.env}</p>
            </div>
            <Badge variant="outline" className={f.configured ? 'text-ink' : 'text-mute'}>
              <span className={cn('mr-1.5 h-1.5 w-1.5 rounded-full', f.configured ? 'bg-ink' : 'bg-mute')} />
              {f.configured ? `已配置 ${f.masked}` : '未配置'}
            </Badge>
            <Input
              type="password"
              autoComplete="off"
              className="w-64"
              placeholder="粘贴密钥"
              value={values[f.attr] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.attr]: e.target.value }))}
            />
            <Button type="button" size="sm" variant="outline" onClick={() => save(f.attr)}>
              保存
            </Button>
            {f.configured && (
              <Button type="button" size="sm" variant="ghost" onClick={() => save(f.attr, true)}>
                清除
              </Button>
            )}
          </div>
        ))}
      </div>
      {msg && <p className="pt-3 font-mono text-xs text-mute">{msg}</p>}
    </div>,
    document.getElementById('keyFields') as HTMLElement,
  )
}

export default function ConsoleApp() {
  const initial = useRef(boot().status)
  const [status, setStatus] = useState<StatusPayload>(initial.current)
  const submitting = useRef(false)
  const events = useRef<EventSource | null>(null)

  useEffect(() => {
    // 静态骨架默认离线（产品默认）；boot 里带回来的默认值优先
    const d = initial.current.defaults
    const lever = document.getElementById('modeLever')
    const radios = lever?.querySelectorAll<HTMLInputElement>('input[name="mode"]')
    radios?.forEach((r) => {
      if (r.value === d.mode) r.checked = true
    })
    if (window.location.hash === '#credentials') {
      const online = lever?.querySelector<HTMLInputElement>('input[value="online"]')
      if (online) online.checked = true
    }
    const artifact = document.querySelector<HTMLInputElement>(
      `input[name="artifact"][value="${d.artifact}"]`,
    )
    if (artifact) artifact.checked = true
    const lang = document.getElementById('language') as HTMLSelectElement | null
    if (lang) lang.value = d.language
    const engine = document.getElementById('onlineEngine') as HTMLSelectElement | null
    if (engine) engine.value = d.online_engine
    const diar = document.getElementById('diarEnabled') as HTMLInputElement | null
    if (diar) diar.checked = initial.current.diar_enabled
    syncMode()
  }, [])

  const syncMode = () => {
    const checked = document.querySelector<HTMLInputElement>('input[name="mode"]:checked')
    const online = checked?.value === 'online'
    const engineField = document.getElementById('engineField')
    if (engineField) engineField.hidden = !online
    // 密钥只在在线时报到：离线用户不需要看到它
    const keyPanel = document.getElementById('credentials')
    if (keyPanel) keyPanel.hidden = !online
    if (online) {
      const advanced = engineField?.closest('details')
      if (advanced) advanced.open = true
    }
    const hint = document.getElementById('modeHint')
    if (hint) hint.textContent = online ? '上传音频到云端引擎，按量计费。' : '本机跑，不联网，不花钱。'
    const submit = document.getElementById('submit') as HTMLButtonElement | null
    if (submit) submit.textContent = online ? '开始在线转录' : '开始离线转录'
  }

  useEffect(() => {
    const lever = document.getElementById('modeLever')
    const onChange = () => syncMode()
    lever?.addEventListener('change', onChange)
    return () => lever?.removeEventListener('change', onChange)
  }, [])

  // C8：说话人分离开关。只对离线路径生效，UI 必须明确标注。
  useEffect(() => {
    const diar = document.getElementById('diarEnabled') as HTMLInputElement | null
    const msg = document.getElementById('diarMsg')
    if (!diar) return
    const onChange = async () => {
      if (msg) msg.textContent = '保存中…'
      try {
        const res = await saveDiarSetting(diar.checked)
        if (msg) msg.textContent = res.enabled ? '已开启（仅离线）' : '已关闭'
      } catch (e) {
        diar.checked = !diar.checked
        if (msg) msg.textContent = e instanceof Error ? e.message : String(e)
      }
    }
    diar.addEventListener('change', onChange)
    return () => diar.removeEventListener('change', onChange)
  }, [])

  // 拖入文件是 macOS 上最顺手的动作：把 drop 直接写回 file input
  useEffect(() => {
    const zone = document.getElementById('dropZone')
    const input = document.getElementById('file') as HTMLInputElement | null
    const hint = document.getElementById('fileHint')
    if (!zone || !input || !hint) return
    const idle = hint.textContent ?? ''
    const showName = () => {
      const f = input.files?.[0]
      hint.textContent = f ? f.name + ' · ' + (f.size / 1024 / 1024).toFixed(1) + ' MB' : idle
      const preview = document.getElementById('mediaPreview')
      if (!preview) return
      preview.innerHTML = ''
      if (!f) { preview.hidden = true; return }
      const url = URL.createObjectURL(f)
      const media = document.createElement(f.type.startsWith('video/') ? 'video' : 'audio')
      media.src = url; media.controls = true; media.className = 'media-preview'
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
    return () => {
      zone.removeEventListener('dragover', onDragOver)
      zone.removeEventListener('dragleave', onDragLeave)
      zone.removeEventListener('drop', onDrop)
      input.removeEventListener('change', showName)
    }
  }, [])

  const onSubmit = async (ev: Event) => {
    ev.preventDefault()
    if (submitting.current) return
    const deck = document.getElementById('progressDeck')
    const submit = document.getElementById('submit') as HTMLButtonElement
    const fileInput = document.getElementById('file') as HTMLInputElement
    const pathInput = document.getElementById('sourcePath') as HTMLInputElement
    const mode = document.querySelector<HTMLInputElement>('input[name="mode"]:checked')?.value ?? 'offline'
    const artifact = 'srt'
    const language = (document.getElementById('language') as HTMLSelectElement).value
    const engine = (document.getElementById('onlineEngine') as HTMLSelectElement).value

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

    const bar = document.getElementById('progressBar')
    const text = document.getElementById('progressText')
    const link = document.getElementById('progressLink') as HTMLAnchorElement
    const setMsg = (m: string) => {
      if (text) text.textContent = m
    }

    // Q5：没有音频来源就不提交 —— 服务端也会拒，但没必要多跑一趟。
    // 消息写在 progressDeck 里；该区域默认 hidden，必须先展开，否则提示不可见
    //（UAT 实测：点击后页面毫无反应，字符串只在 JS 源码里）。
    if (!fileInput.files?.[0] && !pathInput.value.trim()) {
      deck?.removeAttribute('hidden')
      if (link) link.hidden = true
      setMsg('请选择音频文件或填写路径')
      return
    }

    submitting.current = true
    submit.disabled = true
    events.current?.close()
    if (bar) bar.style.width = '0%'
    if (link) link.hidden = true

    try {
      deck?.removeAttribute('hidden')
      setMsg('提交中…')
      const { task_id } = await createTask(fd)
      if (link) {
        link.href = `/t/${task_id}`
        link.hidden = false
      }
      setMsg('已排队，等待启动…')
      const es = new EventSource(`/api/tasks/${task_id}/events`)
      events.current = es
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as { type?: string; stage?: string; message?: string; current?: number; total?: number; status?: string; error?: string }
          if (data.type === 'progress') {
            const pct = data.total ? Math.round(((data.current ?? 0) / data.total) * 100) : null
            if (bar && pct !== null) bar.style.width = `${pct}%`
            setMsg(data.message || data.stage || '处理中…')
          } else if (data.type === 'result') {
            es.close()
            if (data.status === 'done') {
              if (bar) bar.style.width = '100%'
              setMsg('完成')
            } else {
              setMsg(`失败：${data.error ?? '未知错误'}`)
            }
          } else if (data.type === 'close') {
            es.close()
          }
        } catch {
          /* 忽略无法解析的心跳 */
        }
      }
      es.onerror = () => setMsg('进度连接中断，正在重连…')
    } catch (e) {
      deck?.removeAttribute('hidden')
      setMsg(e instanceof Error ? e.message : String(e))
    } finally {
      submitting.current = false
      submit.disabled = false
    }
  }

  useEffect(() => {
    const form = document.getElementById('taskForm')
    form?.addEventListener('submit', onSubmit)
    return () => {
      form?.removeEventListener('submit', onSubmit)
      events.current?.close()
    }
  }, [])

  const refreshStatus = (s: Pick<StatusPayload, 'credentials' | 'key_fields' | 'online_engines'>) =>
    setStatus((prev) => ({ ...prev, ...s }))

  return (
    <>
      <EngineOptions engines={status.online_engines} />
      <KeyFieldsPanel fields={status.key_fields} onRefresh={refreshStatus} />
      <HistorySidebar />
    </>
  )
}

// 静态壳 + 动态岛：岛渲染进 #root，再由 portal 落到各容器
const rootEl = document.getElementById('root')
if (rootEl) createRoot(rootEl).render(<ConsoleApp />)
