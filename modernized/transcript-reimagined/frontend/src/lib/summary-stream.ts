// 流式总结的增量解析：模型边输出 JSON，页面边显示已经到达的部分。

export interface PartialSummary {
  title: string
  overview: string
  keyPoints: string[]
  actionItems: string[]
  titleComplete: boolean
  overviewComplete: boolean
}

interface Scanned {
  value: string
  complete: boolean
  end: number
}

/** 从 index 处的开引号开始扫描一个 JSON 字符串，未闭合时返回已到达的内容。 */
function scanStringAt(raw: string, index: number): Scanned | null {
  if (raw[index] !== '"') return null
  let out = ''
  let i = index + 1
  while (i < raw.length) {
    const ch = raw[i]
    if (ch === '\\') {
      const next = raw[i + 1]
      if (next === undefined) return { value: out, complete: false, end: i }
      if (next === 'u') {
        const hex = raw.slice(i + 2, i + 6)
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) return { value: out, complete: false, end: i }
        out += String.fromCharCode(parseInt(hex, 16))
        i += 6
        continue
      }
      out += next === 'n' ? '\n' : next === 't' ? '\t' : next === 'r' ? '' : next
      i += 2
      continue
    }
    if (ch === '"') return { value: out, complete: true, end: i + 1 }
    out += ch
    i += 1
  }
  return { value: out, complete: false, end: raw.length }
}

function findStringField(raw: string, key: string): Scanned | null {
  const keyToken = `"${key}"`
  const at = raw.indexOf(keyToken)
  if (at < 0) return null
  const colon = raw.indexOf(':', at + keyToken.length)
  if (colon < 0) return null
  let i = colon + 1
  while (i < raw.length && /\s/.test(raw[i])) i += 1
  return scanStringAt(raw, i)
}

function findArrayField(raw: string, key: string): string[] {
  const keyToken = `"${key}"`
  const at = raw.indexOf(keyToken)
  if (at < 0) return []
  const open = raw.indexOf('[', at + keyToken.length)
  if (open < 0) return []
  const items: string[] = []
  let i = open + 1
  while (i < raw.length) {
    const ch = raw[i]
    if (/\s/.test(ch) || ch === ',') {
      i += 1
      continue
    }
    if (ch !== '"') break
    const scanned = scanStringAt(raw, i)
    if (!scanned) break
    if (scanned.value.trim()) items.push(scanned.value)
    i = scanned.end
  }
  return items
}

export function parsePartialSummary(raw: string): PartialSummary {
  const title = findStringField(raw, 'title')
  const overview = findStringField(raw, 'overview')
  return {
    title: (title?.value ?? '').trim(),
    overview: (overview?.value ?? '').trim(),
    keyPoints: findArrayField(raw, 'key_points'),
    actionItems: findArrayField(raw, 'action_items'),
    titleComplete: title?.complete ?? false,
    overviewComplete: overview?.complete ?? false,
  }
}

export function hasPartialContent(partial: PartialSummary): boolean {
  return Boolean(
    partial.title || partial.overview || partial.keyPoints.length || partial.actionItems.length,
  )
}
