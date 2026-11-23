// 状态层：单一数据源 + 撤销栈 + 本地持久化 + 订阅。
// 取舍：所有编辑都走 commit()，撤销栈只存 segments 的整份快照。
// 30-90 分钟的转录几十万字符，整份快照 × 60 步在内存里是可接受的（<50MB），
// 换来的是"撤销永远和数据一致"，不值得为省内存做补丁式撤销。

import { deepCopy, uid, tidyText } from './util.js';
import { computeStats } from './stats.js';

const STORAGE_KEY = 'workbench.transcript.v1';
const SETTINGS_KEY = 'workbench.settings.v1';
const HISTORY_LIMIT = 60;

/**
 * commit 的"什么都没改"哨兵：拿 false/0/null 当哨兵会同时踩两个坑——
 * 合并 0 处、替换 0 处的正常返回值就是 0（改了却不进撤销栈），
 * 而 splitSegment 被拒绝时自然返回 null（没改却进了撤销栈）。
 * 专用符号把两者分开。
 */
export const NO_CHANGE = Symbol('no-change');

/** 只留界面上真的会读的键。剩下的设置项都随功能一起删掉了，
 *  留着它们会让下一个人以为某项还能配。 */
const DEFAULT_SETTINGS = {
  theme: 'auto',
  waveColorMode: 'speaker',
  autoScroll: true,
  fontScale: 1,
  playbackRate: 1,
  reduceMotion: false,
};

function defaultSpeakers() {
  return {
    spk_a: { id: 'spk_a', name: '主持人', color: '#5b8def' },
    spk_b: { id: 'spk_b', name: '发言人 2', color: '#e08a3c' },
    spk_c: { id: 'spk_c', name: '发言人 3', color: '#41b883' },
    spk_d: { id: 'spk_d', name: '发言人 4', color: '#c85fd1' },
  };
}

function emptyDoc() {
  return {
    meta: { title: '未命名转录', duration: 0, source: '—', engine: '—', createdAt: new Date().toISOString() },
    speakers: defaultSpeakers(),
    segments: [],
  };
}

/**
 * 造一个 store。
 * storage 可注入：测试要的是一个可预测的存储环境，
 * 直接把 localStorage 写死在模块里就只能靠污染全局来做测试。
 */
export function createStore({ storage = globalThis.localStorage } = {}) {
  const LS = storage;
  let doc = emptyDoc();
  let settings = { ...DEFAULT_SETTINGS };
  let history = [];
  let future = [];
  let dirty = false;
  const listeners = new Set();
  const eventListeners = new Map();

  function emit(reason = 'change') {
    invalidate();
    for (const fn of listeners) fn(doc, settings, { reason, canUndo: history.length > 0, canRedo: future.length > 0, dirty });
  }

  function fire(type, payload) {
    for (const fn of eventListeners.get(type) || []) fn(payload);
  }

  let statsCache = null;
  let statsFor = null;
  function invalidate() {
    statsCache = null;
    statsFor = null;
  }

  /**
   * 内容指纹：只取"会被持久化的转录内容"，不含设置、播放位置、当前选区。
   * 用它判断"硬盘上的存档是不是已经跟屏幕上的东西一致"。
   * 之前只用 dirty 标志：而所有 commit 都会把它置 true，
   * 连切主题、点筛选这类已自动落盘的动作也算"未保存"，
   * 于是每次刷新都被浏览器拦一下——那是个没有意义的拦截，还会吓到用户。
   */
  function contentSignature() {
    return JSON.stringify({
      title: doc.meta?.title ?? '',
      segments: doc.segments.map((s) => [s.id, s.start, s.end, s.speaker, s.text, !!s.flag, !!s.edited]),
      speakers: Object.entries(doc.speakers || {}).map(([id, sp]) => [id, sp.name, sp.color]),
    });
  }

  /** 上次落盘时的内容指纹；null 表示还没有基准（尚未 load） */
  let savedSignature = null;

  function snapshot() {
    return {
      segments: deepCopy(doc.segments),
      speakers: deepCopy(doc.speakers),
      meta: deepCopy(doc.meta),
    };
  }

  function restore(snap) {
    doc.segments = snap.segments;
    doc.speakers = snap.speakers;
    doc.meta = snap.meta;
  }

  function load() {
    try {
      const raw = LS?.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && Array.isArray(parsed.segments) && parsed.segments.length) {
          doc = parsed;
          dirty = parsed.dirty === true;
        }
      }
    } catch {
      /* 坏数据直接忽略，不要因为 localStorage 让页面起不来 */
    }
    try {
      const raw = LS?.getItem(SETTINGS_KEY);
      if (raw) settings = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    } catch {
      /* 同上 */
    }
    invalidate();
    return { doc, settings };
  }

  function persist() {
    try {
      LS.setItem(STORAGE_KEY, JSON.stringify({ ...doc, dirty }));
      savedSignature = contentSignature();
    } catch (err) {
      // 写不进去的时候必须让"有未保存改动"一直停在那里，
      // 否则下次启动会读到一个旧存档并告诉用户"已同步"——那是在骗人。
      dirty = true;
      savedSignature = null; // 没有可信的落盘基准
      fire('error', { message: '本地保存失败（可能超出配额）', detail: String(err) });
    }
  }

  /** 是否真的有未落盘的转录改动（不是"动过"） */
  function hasUnsavedWork() {
    if (!savedSignature) return dirty;
    return contentSignature() !== savedSignature;
  }

  function persistSettings() {
    try {
      LS.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      /* 设置存不下不影响使用 */
    }
  }

  const store = {
    get doc() {
      return doc;
    },
    get settings() {
      return settings;
    },
    get dirty() {
      return dirty;
    },
    /** 给卸载拦截用：只对"磁盘上没有的转录改动"返回 true */
    get unsavedWork() {
      return hasUnsavedWork();
    },
    get canUndo() {
      return history.length > 0;
    },
    get canRedo() {
      return future.length > 0;
    },
    get stats() {
      if (statsFor !== doc.segments || !statsCache) {
        statsCache = computeStats(doc);
        statsFor = doc.segments;
      }
      return statsCache;
    },
    load,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    on(type, fn) {
      if (!eventListeners.has(type)) eventListeners.set(type, new Set());
      eventListeners.get(type).add(fn);
      return () => eventListeners.get(type).delete(fn);
    },
    /**
     * 一次可撤销的修改。label 出现在撤销菜单里，也是日志里的动作名。
     * mutate 直接改 doc（拿到的是可变引用），commit 负责前后快照。
     *
     * 返回 NO_CHANGE 视为"这次什么都没改"：不留撤销点、不标脏、并把 doc 还原。
     * 返回其他任何值（包括 0、null、false）都算真改过了。
     */
    commit(label, mutate, { silent = false } = {}) {
      const before = snapshot();
      const result = mutate(doc);
      if (result === NO_CHANGE) {
        restore(before);
        return result;
      }
      history.push({ label, before });
      if (history.length > HISTORY_LIMIT) history.shift();
      future = [];
      dirty = true;
      persist();
      if (!silent) emit(label);
      return result;
    },

    /** 不产生撤销点的修改：重命名说话人这种"顺手的"，仍标记 dirty */    touch(mutate) {
      const result = mutate(doc);
      dirty = true;
      persist();
      emit('touch');
      return result;
    },

    undo() {
      if (!history.length) return false;
      const entry = history.pop();
      future.push({ label: entry.label, after: snapshot() });
      restore(entry.before);
      persist();
      emit('undo');
      fire('undo', entry.label);
      return true;
    },

    redo() {
      if (!future.length) return false;
      const entry = future.pop();
      history.push({ label: entry.label, before: snapshot() });
      restore(entry.after);
      persist();
      emit('redo');
      fire('redo', entry.label);
      return true;
    },

    historyLabels() {
      return { undo: history.length ? history[history.length - 1].label : null, redo: future.length ? future[future.length - 1].label : null };
    },

    setSetting(key, value, { silent = false } = {}) {
      settings = { ...settings, [key]: value };
      persistSettings();
      if (!silent) {
        emit(`setting:${key}`);
        fire('setting', { key, value });
      }
    },

    /** 导入/新建文档：默认标脏，因为这份内容还从没被显式保存过 */
    replaceDoc(next, { markDirty = true } = {}) {
      history = [];
      future = [];
      doc = {
        meta: { ...emptyDoc().meta, ...next.meta },
        speakers: next.speakers || defaultSpeakers(),
        // 导入的 JSON 不可信：null 条目、缺字段、字符串数字都见过。
        // 这一层必须把它们规整成可用形态，而不是让后面的渲染去崩。
        segments: (next.segments || [])
          .filter((s) => s && typeof s === 'object')
          .map((s) => {
            const start = Number(s.start);
            const end = Number(s.end);
            const safeStart = Number.isFinite(start) && start >= 0 ? start : 0;
            const safeEnd = Number.isFinite(end) && end > safeStart ? end : safeStart + 0.2;
            return {
              id: s.id || uid('seg'),
              start: safeStart,
              end: safeEnd,
              speaker: typeof s.speaker === 'string' && s.speaker ? s.speaker : 'spk_a',
              text: typeof s.text === 'string' ? s.text : '',
              confidence: typeof s.confidence === 'number' && Number.isFinite(s.confidence) ? s.confidence : undefined,
              edited: !!s.edited,
              note: typeof s.note === 'string' ? s.note : '',
              flag: !!s.flag,
            };
          }),
      };
      dirty = markDirty;
      persist();
      emit('replace');
    },
    clearAll() {
      history = [];
      future = [];
      doc = emptyDoc();
      dirty = false;
      persist();
      emit('clear');
    },

    markSaved() {
      // 显式保存：把当前内容定为落盘基准（存档本来就已经写了）
      dirty = false;
      persist();
      emit('saved');
    },

    /* ---------- 面向分段的具体操作：都在这里，避免散落到 UI ---------- */

    insertAfter(index, patch = {}) {      return store.commit('新增分段', (d) => {
        const prev = d.segments[index];
        const next = d.segments[index + 1];
        const start = prev ? prev.end : 0;
        const end = next ? Math.min(next.start, start + 5) : start + 5;
        const seg = {
          id: uid('seg'),
          start,
          end: Math.max(end, start + 0.2),
          speaker: prev?.speaker || 'spk_a',
          text: '',
          edited: true,
          ...patch,
        };
        d.segments.splice(index + 1, 0, seg);
        return seg;
      });
    },

    splitSegment(id, atTime, { headText, tailText, speaker } = {}) {
      return store.commit('拆分分段', (d) => {
        const i = d.segments.findIndex((s) => s.id === id);
        if (i < 0) return NO_CHANGE; // 切点写错时不该静默改数据
        const seg = d.segments[i];
        // 切点必须在段内部，且两半都不能短于 0.2 秒
        if (!(seg.end - seg.start > 0.4)) return NO_CHANGE;
        const t = Math.min(Math.max(atTime, seg.start + 0.2), seg.end - 0.2);

        // 时间比例 -> 字符切点；文字上给了显式切分就以它为准
        const chars = Array.from(seg.text || '');
        const ratio = seg.end > seg.start ? (t - seg.start) / (seg.end - seg.start) : 0.5;
        const cut = headText != null || tailText != null ? -1 : Math.round(chars.length * ratio);
        const head = headText != null ? headText : cut >= 0 ? chars.slice(0, cut).join('') : '';
        const tail = tailText != null ? tailText : cut >= 0 ? chars.slice(cut).join('') : seg.text;

        const originalEnd = seg.end;
        seg.text = tidyText(head);
        seg.end = t;
        seg.edited = true;

        const created = {
          id: uid('seg'),
          start: t,
          end: originalEnd,
          speaker: speaker || seg.speaker,
          text: tidyText(tail),
          confidence: seg.confidence,
          edited: true,
        };
        d.segments.splice(i + 1, 0, created);
        return { head: seg, tail: created };
      });
    },

    /** 把若干段并进第一段。mergeWithNext 与框选合并都走这里 */
    mergeRange(ids) {
      return store.commit(ids.length > 1 ? `合并 ${ids.length} 段` : '合并分段', (d) => {
        const idx = ids
          .map((id) => d.segments.findIndex((s) => s.id === id))
          .filter((i) => i >= 0)
          .sort((x, y) => x - y);
        if (idx.length < 2) return NO_CHANGE;
        const picked = idx.map((i) => d.segments[i]);
        const first = picked[0];
        first.end = picked.at(-1).end;
        first.text = tidyText(picked.map((s) => s.text).filter(Boolean).join(' '));
        first.edited = true;
        // 置信度取最低的那一个：合并后只要有一半可疑，整段就还可疑
        const confs = picked.map((s) => s.confidence).filter((c) => typeof c === 'number');
        if (confs.length) first.confidence = Math.min(...confs);
        for (let k = idx.length - 1; k >= 1; k -= 1) d.segments.splice(idx[k], 1);
        return first;
      });
    },

    mergeWithNext(id) {
      const i = doc.segments.findIndex((s) => s.id === id);
      if (i < 0 || i >= doc.segments.length - 1) return NO_CHANGE;
      return store.mergeRange([doc.segments[i].id, doc.segments[i + 1].id]);
    },

    deleteSegments(ids) {
      const set = new Set(ids);
      return store.commit(`删除 ${ids.length} 段`, (d) => {
        const before = d.segments.length;
        d.segments = d.segments.filter((s) => !set.has(s.id));
        return before - d.segments.length || NO_CHANGE;
      });
    },

    updateText(id, text) {
      return store.commit('修改文本', (d) => {
        const seg = d.segments.find((s) => s.id === id);
        if (!seg || seg.text === text) return NO_CHANGE;
        seg.text = text;
        seg.edited = true;
        return true;
      });
    },

    retime(id, start, end) {
      return store.commit('调整时间', (d) => {
        const seg = d.segments.find((s) => s.id === id);
        if (!seg) return NO_CHANGE;
        const s = Math.max(0, Math.min(start, end - 0.2));
        const e = Math.min(d.meta.duration || Infinity, Math.max(end, s + 0.2));
        seg.start = s;
        seg.end = e;
        seg.edited = true;
        return true;
      });
    },

    setSpeaker(id, speaker) {
      return store.commit('改说话人', (d) => {
        for (const seg of d.segments) if (id === 'ALL' || seg.id === id) seg.speaker = speaker;
      });
    },

    toggleFlag(id) {
      return store.commit('标记待复核', (d) => {
        const seg = d.segments.find((s) => s.id === id);
        if (seg) seg.flag = !seg.flag;
      });
    },

    renameSpeaker(id, name) {
      return store.touch((d) => {
        if (d.speakers[id]) d.speakers[id].name = name;
        for (const seg of d.segments) if (seg.speaker === id && !d.speakers[id]) d.speakers[id] = { id, name, color: '#888' };
      });
    },

    addSpeaker(name = '新说话人') {
      return store.commit('新增说话人', (d) => {
        const id = uid('spk');
        const palette = ['#5b8def', '#e08a3c', '#41b883', '#c85fd1', '#e05d5d', '#3fb6c8', '#b0a03c'];
        const color = palette[Object.keys(d.speakers).length % palette.length];
        d.speakers[id] = { id, name, color };
        return id;
      });
    },

    mergeAdjacentShort(maxSec = 1.2) {
      return store.commit('合并过短分段', (d) => {
        let merged = 0;
        for (let i = d.segments.length - 2; i >= 0; i -= 1) {
          const a = d.segments[i];
          const b = d.segments[i + 1];
          // 只合并"数组上相邻且时间上不重叠"的同说话人配对。
          // 少了时间这道门，一次合并会把 a 的终点推到 b 的终点，直接压在第三段上。
          const adjacentInTime = b.start >= a.end - 1e-6;
          if (adjacentInTime && a.speaker === b.speaker && b.end - b.start < maxSec) {
            a.end = b.end;
            a.text = tidyText(`${a.text} ${b.text}`);
            d.segments.splice(i + 1, 1);
            merged += 1;
          }
        }
        return merged || NO_CHANGE;
      });
    },

    normalizeTimeline() {
      return store.commit('规整时间轴', (d) => {
        let fixed = 0;
        for (let i = 0; i < d.segments.length; i += 1) {
          const seg = d.segments[i];
          const prev = d.segments[i - 1];
          if (prev && seg.start < prev.end) {
            const mid = (prev.end + seg.end) / 2;
            prev.end = mid;
            seg.start = mid;
            fixed += 1;
          }
          if (seg.end - seg.start < 0.2) {
            seg.end = seg.start + 0.2;
            fixed += 1;
          }
        }
        return fixed || NO_CHANGE;
      });
    },

    replaceAllText(find, replace, { regex = false, caseSensitive = false } = {}) {
      return store.commit('批量替换', (d) => {
        let hits = 0;
        const re = regex
          ? new RegExp(find, caseSensitive ? 'g' : 'gi')
          : new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), caseSensitive ? 'g' : 'gi');
        for (const seg of d.segments) {
          const next = seg.text.replace(re, replace);
          if (next !== seg.text) {
            hits += 1;
            seg.text = next;
            seg.edited = true;
          }
        }
        return hits || NO_CHANGE; // 无命中就不要留撤销点
      });
    },
  };

  return store;
}

export { DEFAULT_SETTINGS, STORAGE_KEY, SETTINGS_KEY };
