// 统计层：纯函数。界面上的数字全部来自这里，避免同一件事在三个地方各算一遍。

import { countWords, wordsPerMinute, hms } from './util.js';

const LOW_CONFIDENCE = 0.72;

export function computeStats(doc) {
  const segments = doc.segments || [];
  const speechSec = segments.reduce((acc, s) => acc + Math.max(0, s.end - s.start), 0);
  const words = segments.reduce((acc, s) => acc + countWords(s.text), 0);
  const chars = segments.reduce((acc, s) => acc + Array.from(s.text || '').length, 0);
  const duration = doc.meta?.duration || (segments.length ? segments[segments.length - 1].end : 0);

  const bySpeaker = new Map();
  for (const seg of segments) {
    const key = seg.speaker || 'unknown';
    const row = bySpeaker.get(key) || { id: key, seconds: 0, segments: 0, words: 0 };
    row.seconds += Math.max(0, seg.end - seg.start);
    row.segments += 1;
    row.words += countWords(seg.text);
    bySpeaker.set(key, row);
  }

  const speakers = [...bySpeaker.values()]
    .map((row) => ({
      ...row,
      name: doc.speakers?.[row.id]?.name || row.id,
      color: doc.speakers?.[row.id]?.color || '#888',
      share: speechSec ? row.seconds / speechSec : 0,
      wpm: wordsPerMinute(row.words, row.seconds),
    }))
    .sort((a, b) => b.seconds - a.seconds);

  const longest = segments.reduce((acc, s) => (s.end - s.start > (acc?.end - acc?.start || 0) ? s : acc), null);
  const edited = segments.filter((s) => s.edited).length;
  const lowConf = segments.filter((s) => typeof s.confidence === 'number' && s.confidence < LOW_CONFIDENCE).length;
  const gaps = [];
  for (let i = 1; i < segments.length; i += 1) {
    const gap = segments[i].start - segments[i - 1].end;
    if (gap > 3) gaps.push({ after: segments[i - 1].id, seconds: gap, at: segments[i - 1].end });
  }

  return {
    duration,
    speechSec,
    silenceSec: Math.max(0, duration - speechSec),
    coverage: duration ? speechSec / duration : 0,
    segments: segments.length,
    words,
    chars,
    wpm: wordsPerMinute(words, speechSec),
    avgSegment: segments.length ? speechSec / segments.length : 0,
    longestSec: longest ? longest.end - longest.start : 0,
    speakers,
    edited,
    lowConf,
    gaps,
    readingTime: hms((words / 300) * 60),
    speakingTime: hms(speechSec),
  };
}

export { LOW_CONFIDENCE };
