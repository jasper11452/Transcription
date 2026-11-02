// 密钥面板：控制台与设置页共用。控制台只在在线模式出现；设置页常驻。
// 只显示「已配置/未配置 + 尾号」，明文不落进任何响应。

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { saveCredentials } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { KeyField, StatusPayload } from '@/lib/types'

type SavedStatus = Pick<StatusPayload, 'credentials' | 'key_fields' | 'online_engines'>

export function KeyFieldsPanel({
  fields,
  onRefresh,
}: {
  fields: KeyField[]
  onRefresh: (s: SavedStatus) => void
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)

  const save = async (attr: string, clear = false) => {
    setMsg(null)
    try {
      const payload = clear
        ? { clear: [attr] }
        : { keys: { [attr]: values[attr] ?? '' } }
      const res = await saveCredentials(payload)
      onRefresh(res)
      setValues((v) => ({ ...v, [attr]: '' }))
      setMsg(clear ? '已清除' : '已保存')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  if (!fields.length) {
    return <p className="text-sm text-mute">在线模式暂不需要密钥。</p>
  }
  return (
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
              aria-label={`${f.label} 密钥`}
              placeholder="粘贴密钥"
              value={values[f.attr] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.attr]: e.target.value }))}
            />
            <Button type="button" size="sm" variant="outline" aria-label={`保存 ${f.label} 密钥`} onClick={() => void save(f.attr)}>
              保存
            </Button>
            {f.configured && (
              <Button type="button" size="sm" variant="ghost" aria-label={`清除 ${f.label} 密钥`} onClick={() => void save(f.attr, true)}>
                清除
              </Button>
            )}
          </div>
        ))}
      </div>
      {msg && <p className="pt-3 font-mono text-xs text-mute">{msg}</p>}
    </div>
  )
}
