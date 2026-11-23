// 导出层：只吃 {segments, speakers, meta}，不认识 DOM 也不认识 UI。
// 一条硬约束：所有产物都从同一份 segments 派生，不各自维护副本。

import { timecode, safeName, tidyText } from './util.js';

/** SRT 规范要求 HH:MM:SS,mmm 四段齐全，所以不能用 timecode 的"零小时省略"版本 */
function srtStamp(sec) {
  const total = Math.max(0, Math.round((Number(sec) || 0) * 1000));
  const h = Math.floor(total / 3600000);
  const m = Math.floor((total % 3600000) / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const ms = total % 1000;
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(h)}:${p(m)}:${p(s)},${p(ms, 3)}`;
}

function speakerName(seg, speakers) {
  const sp = speakers?.[seg.speaker];
  return (sp && sp.name) || '说话人';
}

/** 纯文本：可选的说话人与时间戳前缀 */
export function toTxt(doc, { timestamps = false, speakers = false } = {}) {
  const lines = [];
  let lastSpeaker = null;
  for (const seg of doc.segments) {
    const parts = [];
    if (timestamps) parts.push(`[${timecode(seg.start)}]`);
    if (speakers && seg.speaker !== lastSpeaker) parts.push(`${speakerName(seg, doc.speakers)}：`);
    if (!speakers) lastSpeaker = null;
    else lastSpeaker = seg.speaker;
    parts.push(tidyText(seg.text));
    lines.push(parts.filter(Boolean).join(speakers && !timestamps ? '' : ' '));
  }
  return lines.join('\n');
}

export function toSrt(doc) {
  const out = [];
  let n = 0;
  for (const seg of doc.segments) {
    const text = tidyText(seg.text);
    if (!text) continue; // 空段不进字幕，否则出现只有序号的黑屏
    n += 1;
    out.push(String(n));
    out.push(`${srtStamp(seg.start)} --> ${srtStamp(seg.end)}`);
    out.push(text);
    out.push('');
  }
  return out.join('\n');
}

export function toVtt(doc) {
  const out = ['WEBVTT', ''];
  let n = 0;
  for (const seg of doc.segments) {
    const text = tidyText(seg.text);
    if (!text) continue;
    n += 1;
    out.push(String(n));
    out.push(`${timecode(seg.start)} --> ${timecode(seg.end)}`);
    out.push(`<v ${speakerName(seg, doc.speakers)}>${text}`);
    out.push('');
  }
  return out.join('\n');
}

export function toMarkdown(doc) {
  const rows = doc.segments.map((seg) => {
    const text = tidyText(seg.text).replace(/\|/g, '\\|');
    return `| ${timecode(seg.start)} | ${timecode(seg.end)} | ${speakerName(seg, doc.speakers)} | ${text} |`;
  });
  return [
    `# ${doc.meta?.title || '转录'}`,
    '',
    `- 时长：${timecode(doc.meta?.duration || 0)}`,
    `- 分段：${doc.segments.length}`,
    `- 来源：${doc.meta?.source || '未知'}`,
    '',
    '| 开始 | 结束 | 说话人 | 文本 |',
    '| --- | --- | --- | --- |',
    ...rows,
    '',
  ].join('\n');
}

/** raw.json：把分片级证据原样留下，供别的工具消费（与 PRODUCT.md 的 raw.json 同精神） */
export function toJson(doc) {
  return JSON.stringify(
    {
      version: 1,
      generated_at: new Date().toISOString(),
      meta: { ...doc.meta },
      speakers: doc.speakers,
      segments: doc.segments.map((s) => ({
        id: s.id,
        start: Number(s.start.toFixed(3)),
        end: Number(s.end.toFixed(3)),
        speaker: s.speaker,
        text: s.text,
        confidence: s.confidence ?? null,
        edited: !!s.edited,
      })),
      stats: doc.stats || null,
    },
    null,
    2,
  );
}

export const EXPORTERS = {
  txt: { label: '纯文本 .txt', ext: 'txt', mime: 'text/plain;charset=utf-8', build: (d) => toTxt(d) },
  txt_time: {
    label: '带时间戳 .txt',
    ext: 'txt',
    mime: 'text/plain;charset=utf-8',
    build: (d) => toTxt(d, { timestamps: true }),
  },
  txt_speaker: {
    label: '带说话人 .txt',
    ext: 'txt',
    mime: 'text/plain;charset=utf-8',
    build: (d) => toTxt(d, { timestamps: true, speakers: true }),
  },
  srt: { label: '字幕 .srt', ext: 'srt', mime: 'application/x-subrip;charset=utf-8', build: toSrt },
  vtt: { label: '字幕 .vtt', ext: 'vtt', mime: 'text/vtt;charset=utf-8', build: toVtt },
  md: { label: '表格 .md', ext: 'md', mime: 'text/markdown;charset=utf-8', build: toMarkdown },
  json: { label: '原始数据 .json', ext: 'json', mime: 'application/json;charset=utf-8', build: toJson },
};

export function buildExport(doc, kind) {
  const ex = EXPORTERS[kind];
  if (!ex) throw new Error(`未知导出格式: ${kind}`);
  return { text: ex.build(doc), filename: `${safeName(doc.meta?.title)}.${ex.ext}`, mime: ex.mime };
}

/** SRT 反向解析：容错单测用，也用于"导入已有字幕继续改" */
export function parseSrt(input) {
  const segs = [];
  const blocks = String(input || '').replace(/\r\n/g, '\n').trim().split(/\n{2,}/);
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim() !== '');
    if (lines.length < 2) continue;
    let idx = 0;
    if (/^\d+$/.test(lines[0].trim())) idx = 1;
    const tm = lines[idx]?.match(/(\S+)\s*-->\s*(\S+)/);
    if (!tm) continue;
    const parse = (s) => {
      const m = s.match(/(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})/);
      if (!m) return null;
      return Number(m[1] || 0) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4].padEnd(3, '0')) / 1000;
    };
    const start = parse(tm[1]);
    const end = parse(tm[2]);
    if (start == null || end == null) continue;
    segs.push({ start, end, text: lines.slice(idx + 1).join('\n') });
  }
  return segs;
}
