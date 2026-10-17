// 纯工具层：不碰 DOM，不碰 store。可以在 node 里直接 import 做单测。

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

let _idSeq = 0;
export function uid(prefix = 'id') {
  _idSeq += 1;
  return `${prefix}_${Date.now().toString(36)}_${_idSeq.toString(36)}`;
}

/** 秒 -> 00:12.345（用于导出，毫秒 3 位）
 *  先在整数毫秒上四舍五入，再拆分时分秒。
 *  分别取整秒和毫秒小数会造出 00:59.1000、00:60.000 这类非法时间码。
 */
export function timecode(sec, { ms = true } = {}) {
  const total = Math.max(0, Math.round((Number(sec) || 0) * 1000));
  const h = Math.floor(total / 3600000);
  const m = Math.floor((total % 3600000) / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const milli = total % 1000;
  const head = h > 0 ? `${String(h).padStart(2, '0')}:` : '';
  return `${head}${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}${ms ? '.' + String(milli).padStart(3, '0') : ''}`;
}

/** 秒 -> 12:03（用于界面标签，省掉毫秒）；不足一分钟只给 05 这样的秒数 */
export function clock(sec) {
  const t = Math.max(0, Number(sec) || 0);
  if (t < 60) return timecode(t, { ms: false }).slice(3);
  return timecode(t, { ms: false }).replace(/^00:/, '');
}

/** 秒 -> 05 / 1:20 / 00:03.500，用于状态栏这种空间紧的地方 */
export function shortTime(sec) {
  const t = Math.max(0, Number(sec) || 0);
  if (t < 60) return timecode(t, { ms: false }).slice(3);
  return timecode(t, { ms: false }).replace(/^00:/, '');
}

/** 00:12.345 / 00:00:12,345 -> 秒；容错，坏值返回 null */
export function parseTimecode(str) {
  if (typeof str === 'number') return isFinite(str) ? str : null;
  if (typeof str !== 'string') return null;
  const m = str.trim().match(/^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?$/);
  if (!m) return null;
  const [, h, mm, ss, frac] = m;
  const msPart = frac ? Number(frac.padEnd(3, '0')) / 1000 : 0;
  return Number(h || 0) * 3600 + Number(mm) * 60 + Number(ss) + msPart;
}

const CJK_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/;

/** 中日韩字符按"字"计，拉丁按词计 —— 两种都不低估。非字符串输入按空串处理。 */
export function countWords(text) {
  if (typeof text !== 'string' || !text) return 0;
  let cjk = 0;
  const latin = text.replace(/[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/g, (ch) => {
    cjk += 1;
    return ' ';
  });
  const words = latin.replace(/[^\p{L}\p{N}'’-]+/gu, ' ').trim();
  return cjk + (words ? words.split(/\s+/).length : 0);
}

/**
 * 每分钟字数。第一个参数收文本或者已经数好的字数——
 * 之前只收文本，但调用方传的是数字，countWords(数字) 返回 0，导致界面上语速恒显示 0。
 * 收两种类型比让每个调用方记得先转换更不易错。
 */
export function wordsPerMinute(textOrCount, seconds) {
  const secs = Number(seconds);
  if (!Number.isFinite(secs) || secs <= 0) return 0;
  const words = typeof textOrCount === 'number' ? textOrCount : countWords(textOrCount);
  return (words / secs) * 60;
}

/** 旧名保留：语义相同，避免已导入的地方失效 */
export const readSeconds = wordsPerMinute;

export function debounce(fn, wait = 200) {
  let t = 0;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

export function throttle(fn, wait = 100) {
  let last = 0;
  let pending = null;
  return (...args) => {
    const now = Date.now();
    if (now - last >= wait) {
      last = now;
      fn(...args);
    } else {
      clearTimeout(pending);
      pending = setTimeout(() => {
        last = Date.now();
        fn(...args);
      }, wait - (now - last));
    }
  };
}

export function deepCopy(v) {
  if (typeof structuredClone === 'function') return structuredClone(v);
  return JSON.parse(JSON.stringify(v));
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 把逐字/逐词时间戳折成逐字数组，用于把播放位置映射到字符。
 *  输入宽松：{text,start,end} 或 {word,start,end} 都收。
 */
export function foldIntoTokens(tokens) {
  const out = [];
  for (const t of tokens || []) {
    const text = t.text ?? t.word ?? t.value ?? '';
    const start = Number(t.start ?? t.start_time ?? 0);
    const end = Number(t.end ?? t.end_time ?? start);
    if (!text) continue;
    const chars = Array.from(text);
    const span = Math.max(0.001, end - start) / chars.length;
    chars.forEach((ch, i) => out.push({ ch, start: start + i * span, end: start + (i + 1) * span }));
  }
  return out;
}

/** 播放位置 -> 该段内已读字符数 */
export function charsAtTime(tokens, t) {
  let n = 0;
  for (const tok of tokens) {
    if (tok.start <= t) n += 1;
    else break;
  }
  return n;
}

/** 简单行级 diff：返回 [{type:'same'|'add'|'del', a, b}]，供编辑前后对照 */
export function lineDiff(before, after) {
  const a = String(before ?? '').split('\n');
  const b = String(after ?? '').split('\n');
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ type: 'same', text: a[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ type: 'del', text: a[i] });
      i += 1;
    } else {
      rows.push({ type: 'add', text: b[j] });
      j += 1;
    }
  }
  while (i < n) rows.push({ type: 'del', text: a[i++] });
  while (j < m) rows.push({ type: 'add', text: b[j++] });
  return rows;
}

/** 字符级 diff：给两个近似字符串标出改动（前后缀裁剪，足够用且快） */
export function charDiff(before, after) {
  const a = Array.from(String(before ?? ''));
  const b = Array.from(String(after ?? ''));
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head += 1;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail += 1;
  return {
    same_head: a.slice(0, head).join(''),
    removed: a.slice(head, a.length - tail).join(''),
    added: b.slice(head, b.length - tail).join(''),
    same_tail: tail > 0 ? a.slice(a.length - tail).join('') : '',
  };
}

/** 中文标点后补空格没有意义，这里只在拉丁文之间做规范化 */
export function tidyText(text) {
  const t = String(text ?? '');
  const hasCJK = CJK_RE.test(t);
  return hasCJK
    ? t.replace(/\s+/g, ' ').trim()
    : t.replace(/\s+/g, ' ').replace(/\s+([,.!?;:])/g, '$1').trim();
}

/** CSV/文件名安全化 */
export function safeName(name) {
  return String(name || 'audio').replace(/\.[^.]+$/, '').replace(/[^\p{L}\p{N}._-]+/gu, '_').slice(0, 80) || 'audio';
}

export function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function bytes(n) {
  if (!n && n !== 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function hms(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h > 0 ? `${h} 小时 ${m} 分` : m > 0 ? `${m} 分 ${r} 秒` : `${r} 秒`;
}
