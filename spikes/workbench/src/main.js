// 装配层：唯一知道"谁认识谁"的地方。
// store / audio / waveform / transcript 互不引用，所有接线都集中在这里，
// 于是要换掉任何一层（换引擎、换波形渲染、换列表实现）都只动这一个文件。

import { createStore, NO_CHANGE } from './store.js';
import { createAudioEngine, buildDemoAudio, demoDoc, DEMO_SCRIPT } from './audio.js';
import { createWaveform } from './waveform.js';
import { createTranscriptList } from './transcript.js';
import { createPalette } from './palette.js';
import { createToaster, createModal, buildShortcutTable } from './ui.js';
import { buildExport, EXPORTERS, parseSrt } from './export.js';
import { timecode, clock, hms, countWords, clamp, escapeHtml, charDiff, debounce, download, uid } from './util.js';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const store = createStore();
const toaster = createToaster(document.body);
const modal = createModal(document.body);

/* ------------------------------------------------------------ 日志 */

const logList = $('#log-list');
function log(kind, message, detail = '') {
  const li = document.createElement('li');
  li.className = kind;
  li.innerHTML = `<time>${new Date().toLocaleTimeString('zh-CN', { hour12: false })}</time>${escapeHtml(message)}${detail ? ` — ${escapeHtml(detail)}` : ''}`;
  logList.prepend(li);
  while (logList.children.length > 60) logList.lastElementChild.remove();
}
store.on('error', ({ message, detail }) => {
  log('error', message, detail);
  toaster.error(message, { detail });
});

/* ------------------------------------------------------------ 音频层 */

const engine = createAudioEngine({
  onTime: (t, dur) => {
    paintTime(t, dur);
    waveform.draw();
    playerUI(t);
  },
  onState: ({ playing }) => {
    document.body.classList.toggle('mode-playback', playing);
    $('#play-icon').innerHTML = `<use href="#i-${playing ? 'pause' : 'play'}"/>`;
    $('#btn-play').setAttribute('aria-pressed', String(playing));
  },
  onError: (e) => log('error', '播放出错', String(e?.message || e)),
});

/* ----------------------------------------------------------- 波形视图 */

const waveform = createWaveform($('#wave-wrap'), {
  engine,
  store,
  onSeek: (t, opts) => seekTo(t, opts),
  onSelect: (id) => transcript.setCursor(id),
  // 拖出来的范围直接当一个分段用：这是"用波形做校对"最省事的一条路
  onRangeCommit: (range) => {
    transcript.focus();
    applyRegion(range);
  },
});

/* ----------------------------------------------------------- 转录列表 */

const transcript = createTranscriptList($('#seg-scroll'), {
  store,
  onSeek: (t, opts) => seekTo(t, opts),
  onEdit: ({ id, before, text }) => {
    const d = charDiff(before, text);
    log('info', `修改了第 ${store.doc.segments.findIndex((s) => s.id === id) + 1} 段`, d.removed || d.added ? `-${d.removed.slice(0, 30)} +${d.added.slice(0, 30)}` : '');
    markDirtyFlash();
  },
  onAction: (action, payload) => runAction(action, payload),
  onSelectionChange: (ids) => paintSelectionToolbar(ids),
});

/* ------------------------------------------------------ 播放头与选区 */

function paintTime(t, dur) {
  $('#time-current').textContent = timecode(t, { ms: false });
  $('#time-total').textContent = timecode(dur || engine.duration, { ms: false });
  $('#status-playhead').textContent = `播放头：${timecode(t)}`;
}
function playerUI(t) {
  transcript.paintActive(t);
  if (engine.playing && store.settings.autoScroll) {
    const id = transcript.activeSegmentId();
    if (id) transcript.scrollToSegment(id);
  }
}

function seekTo(t, { user = false, segment = null, nudge = false } = {}) {
  engine.seek(t);
  if (user) {
    document.body.dataset.userSeek = '1';
    if (segment) {
      transcript.setCursor(segment.id);
      if (!nudge) transcript.setSelected([segment.id]);
    }
  }
  waveform.keepVisible(t);
  waveform.draw();
  playerUI(t);
  paintTime(t, engine.duration);
}

function applyRegion(range) {
  if (!range || range.end - range.start < 0.15) return;
  waveform.selection = range;
  const covering = store.doc.segments.filter((s) => s.start < range.end && s.end > range.start).map((s) => s.id);
  transcript.setSelected(covering);
  if (covering.length === 1) transcript.setCursor(covering[0]);
  paintRegionInfo(range);
}

function paintRegionInfo(sel) {
  const box = $('#region-info');
  box.hidden = !sel;
  if (!sel) {
    $('#status-sel').textContent = '选区：无';
    return;
  }
  const covered = store.doc.segments.filter((s) => s.start < sel.end && s.end > sel.start);
  const words = covered.reduce((a, s) => a + countWords(s.text), 0);
  $('#region-text').textContent = `${timecode(sel.start)} → ${timecode(sel.end)}（${(sel.end - sel.start).toFixed(2)}s，${covered.length} 段，${words} 字）`;
  $('#status-sel').textContent = `选区：${clock(sel.end - sel.start)}`;
}

function clearRegion() {
  waveform.selection = null;
  paintRegionInfo(null);
}

/* ------------------------------------------------------------ 动作表 */

/** 当前段落：优先光标所在，其次播放头所在 */
function currentSeg() {
  return transcript.segmentById(transcript.cursor) || transcript.segmentById(transcript.activeSegmentId()) || null;
}

function seekSegment(seg, { play = false } = {}) {
  if (!seg) return;
  seekTo(seg.start + 0.01, { user: true, segment: seg });
  transcript.scrollToSegment(seg.id);
  if (play) engine.play(seg.start + 0.01);
}

/** 前后段：dir < 0 是上一段，dir > 0 是下一段 */
function stepSegment(dir, { play = false } = {}) {
  const segs = store.doc.segments;
  const t = engine.time;
  if (!segs.length) return;
  seekSegment(dir > 0 ? segs.find((s) => s.start > t + 0.05) || segs[0] : [...segs].reverse().find((s) => s.start < t - 0.05) || segs.at(-1), { play });
}

function togglePlay() {
  engine.toggle();
}

function deleteSegments(ids) {
  const targets = ids?.length ? ids : [currentSeg()?.id].filter(Boolean);
  if (!targets.length) return;
  store.deleteSegments(targets);
  transcript.clearSelection();
  toaster.info(`删除了 ${targets.length} 段`, {
    action: {
      label: '撤销',
      run: () => {
        store.undo();
        transcript.reconcile();
      },
    },
  });
}

/** 循环区间 = 选中段的并集，或当前段 */
function toggleLoop() {
  if (engine.loop) {
    engine.setLoop(0, 0);
    paintLoop();
    return;
  }
  const ids = transcript.selected.length ? transcript.selected : [currentSeg()?.id].filter(Boolean);
  const segs = store.doc.segments.filter((s) => ids.includes(s.id));
  if (!segs.length) return toaster.warn('先选中一段再循环');
  engine.setLoop(Math.min(...segs.map((s) => s.start)), Math.max(...segs.map((s) => s.end)));
  paintLoop();
  engine.play(engine.loop.start);
}

function paintLoop() {
  const on = !!engine.loop;
  $('#btn-loop').classList.toggle('is-active', on);
  $('#btn-loop').setAttribute('aria-pressed', String(on));
  const loopEl = $('#status-loop');
  loopEl.hidden = !on;
  if (on) loopEl.textContent = `循环：${timecode(engine.loop.start, { ms: false })}–${timecode(engine.loop.end, { ms: false })}`;
  const v = waveform.getView();
  $('#status-view').textContent = `视图：${timecode(v.viewStart, { ms: false })}–${timecode(v.viewStart + v.viewSpan, { ms: false })}`;
}

function toggleSkipSilence() {
  const on = !engine.skipSilence;
  engine.skipSilence = on;
  $('#btn-skip-silence').classList.toggle('is-active', on);
  toaster.info(on ? '已开启跳过静音' : '已关闭跳过静音', { timeout: 1500 });
}

function jumpLowConfidence() {
  const segs = store.doc.segments;
  const t = engine.time;
  const i = segs.findIndex((s) => s.start > t + 0.05 && typeof s.confidence === 'number' && s.confidence < 0.72);
  const hit = i >= 0 ? segs[i] : segs.find((s) => typeof s.confidence === 'number' && s.confidence < 0.72);
  if (!hit) return toaster.info('没有低置信度的段落了');
  seekSegment(hit, { play: true });
}

/** [ 与 ] 设循环区间的起点 / 终点 */
function setLoopEdge(edge) {
  const t = engine.time;
  const cur = engine.loop || { start: t, end: t };
  engine.setLoop(edge === 'start' ? Math.min(t, cur.end - 0.2) : cur.start, edge === 'start' ? cur.end : Math.max(t, cur.start + 0.2));
  paintLoop();
}

/**
 * 唯一的动作表：既能被按钮/快捷键派发，也是命令面板的候选来源。
 *
 * 为什么要合成一张表：之前同一个动作要写三遍——runAction 的 switch、
 * commands() 里的一条候选、再加按键映射和 bind() 里的接线。
 * 加一个功能要改四处，忘改一处就会出现"面板里看得见但点了没反应"。
 * 现在只有这里的 run() 是实现，其余三处都是它的投影。
 *
 * title 为空的条目不进命令面板（纯内部动作或纯按键动作）。
 */
const ACTIONS = {
  /* 播放 */
  'toggle-play': { title: '播放 / 暂停', group: '播放', shortcut: 'Space', pinned: true, run: togglePlay },
  'play-next-segment': { title: '播放下一段', group: '播放', shortcut: 'N', when: hasSeg, run: () => stepSegment(1, { play: true }) },
  'prev-segment': { title: '上一段', group: '播放', shortcut: ',', when: hasSeg, run: () => stepSegment(-1) },
  'next-segment': { title: '下一段（不播放）', group: '播放', shortcut: '.', when: hasSeg, run: () => stepSegment(1) },
  'replay-current': { title: '重放当前段', group: '播放', when: hasSeg, run: () => seekSegment(currentSeg(), { play: true }) },
  'jump-time': { title: '跳到时间点…', group: '播放', keywords: 'goto 定位', when: hasAudio, run: promptJump },
  'toggle-skip-silence': { title: '跳过静音 开/关', group: '播放', keywords: 'silence vad', when: hasAudio, run: toggleSkipSilence },
  'toggle-loop-segment': { title: '循环当前段 / 选区', group: '播放', shortcut: 'L', when: hasSeg, run: toggleLoop },
  'loop-region': {
    when: () => !!waveform.selection,
    run: () => {
      engine.setLoop(waveform.selection.start, waveform.selection.end);
      paintLoop();
      engine.play(engine.loop.start);
    },
  },
  'seek-back': { title: '后退 5 秒', group: '播放', shortcut: '⇧←', when: hasAudio, run: () => engine.nudge(-5) },
  'seek-fwd': { title: '前进 5 秒', group: '播放', shortcut: '⇧→', when: hasAudio, run: () => engine.nudge(5) },

  /* 编辑 */
  edit: { title: '编辑当前段文本', group: '编辑', shortcut: 'E', when: hasSeg, run: () => transcript.beginEdit(currentSeg()?.id) },
  split: {
    title: '在播放头处拆分', group: '编辑', shortcut: 'S', when: hasSeg,
    run: (p) => {
      const seg = currentSeg();
      // 切点由 store 夹到段内（两半各至少 0.2s）；它拒了就说明这一段太短，必须说出来
      const res = seg && store.splitSegment(seg.id, p.at ?? engine.time);
      if (!res || res === NO_CHANGE) return toaster.warn('这一段太短，切不动（两半各需至少 0.2 秒）');
      log('info', '拆分段', `${timecode(res.head.start)} + ${timecode(res.tail.start)}`);
      return undefined;
    },
  },
  merge: {
    title: '与下一段合并', group: '编辑', shortcut: 'M', when: hasSeg,
    run: (p) => {
      const segs = store.doc.segments;
      const i = segs.findIndex((s) => s.id === (p.id || currentSeg()?.id));
      if (i < 0 || i >= segs.length - 1) return toaster.warn('这是最后一段，没有可合并的下一段');
      store.mergeWithNext(segs[i].id);
      return undefined;
    },
  },
  insert: {
    title: '在下方插入一段', group: '编辑', shortcut: 'I', when: hasSeg,
    run: (p) => {
      const i = store.doc.segments.findIndex((s) => s.id === (p.id || currentSeg()?.id));
      if (i < 0) return undefined;
      const made = store.insertAfter(i);
      transcript.reconcile();
      transcript.setCursor(made.id);
      transcript.beginEdit(made.id);
      return undefined;
    },
  },
  delete: { title: '删除选中 / 当前段', group: '编辑', shortcut: 'Del', when: hasSeg, run: (p) => deleteSegments(p.ids) },
  'toggle-flag': {
    title: '标为待复核', group: '编辑', shortcut: 'F', when: hasSeg,
    run: (p) => {
      const id = p.id || currentSeg()?.id;
      if (!id) return undefined;
      const now = store.toggleFlag(id);
      log('info', now ? '标记待复核' : '取消待复核', `${store.doc.segments.findIndex((s) => s.id === id) + 1} 段`);
      return undefined;
    },
  },
  'cycle-speaker': {
    run: (p) => {
      const keys = Object.keys(store.doc.speakers);
      const cur = store.doc.segments.find((s) => s.id === p.id)?.speaker;
      store.setSpeaker(p.id, keys[(keys.indexOf(cur) + 1) % keys.length]);
    },
  },
  'explain-confidence': {
    run: (p) => {
      const s = store.doc.segments.find((x) => x.id === p.id);
      if (!s) return;
      const low = typeof s.confidence === 'number' && s.confidence < 0.72;
      toaster.info(typeof s.confidence === 'number' ? `引擎置信度 ${(s.confidence * 100).toFixed(1)}%` : '这一段没有置信度信息', {
        detail: typeof s.confidence === 'number' && low ? '低于阈值，建议听一遍或标记待复核。' : '高于阈值，一般不需要回听。',
      });
    },
  },
  'build-segment-from-region': {
    title: '用选区建分段', group: '编辑', shortcut: 'B',
    when: () => !!waveform.selection,
    run: () => {
      const sel = waveform.selection;
      if (!sel) return toaster.warn('先在波形上拖出一个范围');
      store.commit('用选区建分段', (d) => {
        let at = 0;
        while (at < d.segments.length && d.segments[at].start < sel.start) at += 1;
        d.segments.splice(at, 0, { id: uid('seg'), start: sel.start, end: sel.end, speaker: d.segments[at - 1]?.speaker || 'spk_a', text: '', edited: true, flag: true });
      });
      clearRegion();
      transcript.reconcile();
      return undefined;
    },
  },
  'merge-short': { title: '合并所有过短分段', group: '编辑', keywords: 'cleanup 清理', when: hasSeg, run: () => bulkOp('merge-short') },
  normalize: { title: '规整时间轴（消除重叠）', group: '编辑', when: hasSeg, run: () => bulkOp('normalize') },
  replace: { title: '查找替换…', group: '编辑', keywords: 'regex 专名', when: hasSeg, run: openReplaceDialog },
  hotwords: { title: '用热词表替换专名…', group: '编辑', keywords: 'hotword 人名 公司', when: hasSeg, run: openHotwordsDialog },
  'clear-selection': {
    run: () => {
      transcript.clearSelection();
      clearRegion();
    },
  },

  /* 导航 */
  search: { title: '搜索转录文本', group: '导航', shortcut: '⌘F', pinned: true, run: () => $('#search').focus() },
  low: { title: '跳到下一个低置信度段', group: '导航', keywords: 'confidence 可疑', when: hasSeg, run: jumpLowConfidence },

  /* 视图 */
  'zoom-in': { title: '波形放大', group: '视图', shortcut: '+', when: hasAudio, run: () => waveform.zoomAt(1.4) },
  'zoom-out': { title: '波形缩小', group: '视图', shortcut: '-', when: hasAudio, run: () => waveform.zoomAt(0.7) },
  fit: { title: '波形适配整体', group: '视图', shortcut: '0', when: hasAudio, run: () => waveform.fit() },
  'toggle-theme': { title: '切换主题（深 / 浅 / 跟随系统）', group: '视图', run: cycleTheme },

  /* 文件与历史 */
  export: { title: '导出…', group: '文件', shortcut: '⌘E', pinned: true, when: hasSeg, run: openExportDialog },
  'copy-txt': {
    title: '复制纯文本', group: '文件', when: hasSeg,
    run: () => copyToClipboard(buildExport(exportDoc(), 'txt').text, '已复制纯文本'),
  },
  'copy-json': {
    title: '复制 raw.json', group: '文件', when: hasSeg,
    run: () => copyToClipboard(buildExport(exportDoc(), 'json').text, '已复制 raw.json'),
  },
  'open-file': { title: '打开音频 / 字幕文件…', group: '文件', shortcut: '⌘O', run: () => $('#file-input').click() },
  'load-demo': { title: '载入演示音频（无需素材）', group: '文件', keywords: 'demo 示例', run: loadDemo },
  save: { title: '保存到本机', group: '文件', shortcut: '⌘S', run: saveLocal },
  reset: { title: '清空全部（含本地存档）', group: '文件', run: clearAll },
  undo: { title: '撤销', group: '历史', shortcut: '⌘Z', pinned: true, when: () => store.canUndo, run: () => (store.undo(), transcript.reconcile()) },
  redo: { title: '重做', group: '历史', shortcut: '⇧⌘Z', when: () => store.canRedo, run: () => (store.redo(), transcript.reconcile()) },
  help: { title: '快捷键与用法', group: '帮助', shortcut: '?', pinned: true, run: openHelp },
};

function hasSeg() {
  return store.doc.segments.length > 0;
}
function hasAudio() {
  return engine.duration > 0;
}

function runAction(action, payload = {}) {
  const entry = ACTIONS[action];
  if (!entry) return void log('warn', `未知动作：${action}`);
  return entry.run(payload);
}

/* ---------------------------------------------------------- 载入音频 */

function exportDoc() {
  return { ...store.doc, stats: store.stats, segments: store.doc.segments.map((s) => ({ ...s })) };
}

async function loadArrayBuffer(buf, meta) {
  try {
    const started = performance.now();
    toaster.info('正在解码音频…', { timeout: 0 });
    const audio = await engine.ctx.decodeAudioData(buf.slice(0));
    engine.setBuffer(audio, meta);
    $('#status-audio').textContent = `音频：${meta.title}（${((performance.now() - started) / 1000).toFixed(1)}s 解码）`;
    waveform.fit();
    syncAll();
    log('info', `载入音频：${meta.title}`, `${(buf.byteLength / 1048576).toFixed(1)}MB，${timecode(audio.duration)}`);
    paintTime(0, audio.duration);
    return true;
  } catch (err) {
    log('error', '音频解码失败', String(err?.message || err));
    toaster.error('这个文件没能解码', { detail: '浏览器只认自己支持的编码（mp3/m4a/wav/ogg/webm），其他格式先用 ffmpeg 转一下。' });
    return false;
  }
}

async function loadDemo() {
  try {
    toaster.info('正在合成一段演示音频（约 1–2 秒）…', { timeout: 0 });
    const { audio, meta } = await buildDemoAudio();
    engine.setBuffer(audio, meta);
    $('#status-audio').textContent = '音频：演示（合成）';
    store.replaceDoc(demoDoc(audio.duration));
    transcript.reconcile();
    waveform.fit();
    paintTime(0, audio.duration);
    syncAll();
    log('info', '载入演示音频', `${DEMO_SCRIPT.length} 段，${timecode(audio.duration)}`);
    toaster.ok('演示音频就绪。按空格播放，或 ⌘K 看都能做什么。', { action: { label: '播放', run: () => engine.play(0) } });
  } catch (err) {
    log('error', '合成演示音频失败', String(err?.message || err));
    toaster.error('演示音频合成失败', { detail: '这个浏览器的 OfflineAudioContext 可能不可用；可以直接拖入一个音频文件。' });
  }
}

async function loadFile(file) {
  const buf = await file.arrayBuffer();
  return loadArrayBuffer(buf, { title: file.name.replace(/\.[^.]+$/, ''), source: file.name, engine: '本机解码' });
}

function adoptDoc(doc, message, { kind = 'ok' } = {}) {
  store.replaceDoc(doc, { markDirty: true });
  transcript.reconcile();
  syncAll();
  toaster[kind]?.(message) ?? toaster.ok(message);
}

async function loadTextFile(file) {
  try {
    const text = await file.text();
    const title = file.name.replace(/\.[^.]+$/, '');
    if (/\.json$/i.test(file.name)) {
      adoptDoc(JSON.parse(text), '已导入 raw.json');
    } else {
      const segs = parseSrt(text);
      if (segs.length) {
        adoptDoc(
          { meta: { title, duration: segs.at(-1).end, source: file.name, engine: '导入字幕' }, segments: segs.map((s) => ({ start: s.start, end: s.end, speaker: 'spk_a', text: s.text, edited: true })) },
          '已导入字幕',
        );
      } else {
        // 普通文本：按空行切段，时间轴按 4 秒估算，等用户自己配音频
        const paras = text.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean);
        if (!paras.length) throw new Error('这个文本里没有可用内容');
        adoptDoc(
          { meta: { title, duration: paras.length * 4, source: file.name, engine: '导入文本' }, segments: paras.map((p, i) => ({ start: i * 4, end: (i + 1) * 4 - 0.1, speaker: 'spk_a', text: p, edited: true })) },
          '导入的是纯文本：时间轴是估算的，需要人工对齐或配上音频',
          { kind: 'warn' },
        );
      }
    }
    log('info', `导入文本：${file.name}`, `${store.doc.segments.length} 段`);
  } catch (err) {
    log('error', `文本导入失败：${file.name}`, String(err?.message || err));
    toaster.error('这个文本/字幕没能导入', { detail: String(err?.message || err) });
  }
}

function handleFiles(files) {
  const picked = [...files];
  if (!picked.length) return;
  const audio = picked.find((f) => /^audio\//.test(f.type) || /\.(mp3|wav|m4a|aac|flac|ogg|opus|mp4|mov|webm|mkv)$/i.test(f.name));
  const text = picked.find((f) => /\.(srt|vtt|txt|json)$/i.test(f.name));
  if (text) loadTextFile(text);
  if (!audio) return;
  log('info', `读取文件：${audio.name}`, `${(audio.size / 1048576).toFixed(1)}MB`);
  loadFile(audio).then((ok) => ok && toaster.ok(`已载入 ${audio.name}`));
}

/* -------------------------------------------------------- 导出 / 复制 */

function openExportDialog() {
  const body = document.createElement('div');
  body.innerHTML = `
    <div class="export-grid" id="export-grid"></div>
    <div class="field" style="margin-top:16px">
      <label>选项</label>
      <label class="switch"><input type="checkbox" id="exp-ts" /><span>纯文本里带上时间戳</span></label>
      <label class="switch"><input type="checkbox" id="exp-spk" /><span>纯文本里带上说话人</span></label>
    </div>
    <div id="export-warn"></div>
    <pre class="preview" id="export-preview" aria-live="polite"></pre>
  `;
  const grid = body.querySelector('#export-grid');
  let current = 'srt';

  function build() {
    const ts = body.querySelector('#exp-ts').checked;
    const spk = body.querySelector('#exp-spk').checked;
    const kind = current === 'txt' ? (spk ? 'txt_speaker' : ts ? 'txt_time' : 'txt') : current;
    return buildExport(exportDoc(), kind);
  }

  /** 导出前检查：这些是"产物会难看"的常见原因，不是错误，所以只提示不拦 */
  function problems() {
    const segs = store.doc.segments;
    const out = [];
    const empty = segs.filter((s) => !s.text.trim()).length;
    const overlap = segs.filter((s, i) => i > 0 && s.start < segs[i - 1].end - 0.001).length;
    const dense = segs.filter((s) => s.text.length / Math.max(0.1, s.end - s.start) > 30).length;
    const short = segs.filter((s) => s.end - s.start < 0.5).length;
    if (empty) out.push(`${empty} 段是空的（字幕里会被跳过）`);
    if (overlap) out.push(`${overlap} 处时间重叠（字幕里会同时显示两行）`);
    if (dense) out.push(`${dense} 段字数密度过高（多半是把整段塞进一条字幕）`);
    if (short) out.push(`${short} 段短于 0.5 秒（字幕会一闪而过）`);
    return out;
  }

  function render() {
    const { text, filename } = build();
    const lines = text.split('\n');
    body.querySelector('#export-preview').textContent = `${filename}\n${'─'.repeat(30)}\n${lines.slice(0, 18).join('\n')}${lines.length > 18 ? `\n… 共 ${lines.length} 行` : ''}`;
    const issues = problems();
    body.querySelector('#export-warn').innerHTML = issues.length
      ? `<div class="field-hint is-warn">导出前检查发现：<br>· ${issues.map(escapeHtml).join('<br>· ')}</div>`
      : '<div class="field-hint is-ok">检查通过：没有空段、重叠或异常密度。</div>';
  }

  const DESCRIBE = { txt: '一行一段，最通用', srt: '带序号和时间码，字幕软件都认', vtt: '带说话人标记，网页播放器用', md: '表格，粘进文档里', json: '分段级原始数据，给别的工具接' };
  for (const kind of Object.keys(EXPORTERS)) {
    if (kind.startsWith('txt_')) continue; // 这两个由上面的选项切换，不单独列
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'export-card';
    btn.innerHTML = `<strong>${escapeHtml(EXPORTERS[kind].label)}</strong><span>${escapeHtml(DESCRIBE[kind] || '')}</span>`;
    btn.addEventListener('click', () => {
      current = kind;
      for (const b of grid.children) b.classList.toggle('is-active', b === btn);
      render();
    });
    grid.appendChild(btn);
  }
  body.querySelectorAll('input').forEach((i) => i.addEventListener('change', render));
  grid.children[1]?.click(); // 默认 srt：这个工作台的主要产物
  render();

  modal.open({
    title: '导出',
    body,
    width: '760px',
    actions: [
      { label: '复制到剪贴板', run: () => copyToClipboard(build().text, '已复制到剪贴板') },
      {
        label: '下载文件',
        variant: 'primary',
        run: () => {
          const { text, filename, mime } = build();
          download(new Blob([text], { type: mime }), filename);
          log('info', `导出 ${filename}`, `${text.length} 字符`);
          toaster.ok(`已下载 ${filename}`);
        },
      },
    ],
  });
}

async function copyToClipboard(text, okMessage) {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else {
      // http 下的兜底：临时 textarea + execCommand
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toaster.ok(okMessage, { detail: `${text.length} 字符` });
  } catch (err) {
    log('error', '复制失败', String(err?.message || err));
    modal.open({
      title: '剪贴板不可用，请手动复制',
      width: '640px',
      body: `<pre class="preview" style="max-height:52vh">${escapeHtml(text.slice(0, 20000))}</pre>`,
      actions: [{ label: '关闭', variant: 'primary' }],
    });
  }
}

/* ---------------------------------------------------------- 保存与状态 */

function saveLocal() {
  store.markSaved();
  $('#save-state').textContent = '已保存到本机';
  toaster.ok('已保存在这台浏览器里', { detail: '关掉页面再回来还在。要给别人就导出文件。' });
  log('info', '手动保存', `${store.doc.segments.length} 段`);
}

function markDirtyFlash() {
  const el = $('#save-state');
  el.textContent = '未保存的改动';
  el.classList.add('is-dirty');
}

const autosave = debounce(() => {
  const el = $('#save-state');
  el.textContent = '已自动保存';
  el.classList.replace('is-dirty', 'is-saved');
  setTimeout(() => {
    el.classList.remove('is-saved');
    if (!store.dirty) el.textContent = '已保存到本机';
  }, 1600);
}, 700);

function paintSearchHits() {
  const q = transcript.query.trim();
  const n = transcript.visibleCount();
  $('#search-hits').textContent = q ? `命中 ${n} 段` : $('#filter-menu').open || $$('.pane-tools .is-active').length ? `筛出 ${n} 段` : '';
}

function paintSelectionToolbar(ids) {
  const bar = $('#sel-toolbar');
  bar.hidden = !ids.length;
  if (!ids.length) return;
  $('#sel-count').textContent = `已选 ${ids.length} 段`;
  const opts = [`<option value="">设为说话人…</option>`, ...Object.values(store.doc.speakers).map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`)];
  $('#bulk-speaker').innerHTML = opts.join('');
}

function paintSpeakers() {
  const rows = store.stats.speakers;
  const max = Math.max(...rows.map((r) => r.seconds), 1);
  $('#stat-grid').innerHTML = [
    ['时长', timecode(store.stats.duration, { ms: false })],
    ['说话时长', hms(store.stats.speechSec)],
    ['分段', `${store.stats.segments} 段`],
    ['字数', `${store.stats.words} 字`],
    ['语速', `${Math.round(store.stats.wpm)} 字/分`],
    ['平均段长', `${store.stats.avgSegment.toFixed(1)} 秒`],
    ['待复核', `${store.stats.lowConf} 段`],
    ['改过', `${store.stats.edited} 段`],
  ]
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join('');
  $('#stat-bars').innerHTML = rows
    .map(
      (r) => `<div class="spk-bar" title="${escapeHtml(r.name)}：${hms(r.seconds)}，${r.segments} 段">
        <span class="spk-bar-name">${escapeHtml(r.name)}</span>
        <span class="spk-bar-track"><i style="width:${(r.seconds / max) * 100}%;background:${r.color}"></i></span>
        <span class="spk-bar-val">${Math.round(r.share * 100)}%</span>
      </div>`,
    )
    .join('');
  $('#speaker-list').innerHTML = Object.values(store.doc.speakers)
    .map((s) => `<li class="speaker-row"><i style="background:${s.color}"></i><input value="${escapeHtml(s.name)}" data-spk="${escapeHtml(s.id)}" aria-label="说话人名称" /></li>`)
    .join('');
}

function paintStatus() {
  const h = store.historyLabels();
  $('#status-history').textContent = h.undo ? `可撤销：${h.undo}` : h.redo ? `可重做：${h.redo}` : '无可撤销';
  $('#status-store').textContent = store.unsavedWork ? '本地存档：有未落盘的改动' : '本地存档：正常';
  $('#save-state').textContent = store.unsavedWork ? '未保存的改动' : '已保存到本机';
  $('#save-state').classList.toggle('is-dirty', store.unsavedWork);
  $('#seg-count').textContent = `${store.doc.segments.length} 段`;
  // 音频摘要在 syncAll 里统一写：以前有三处各写一半，合成那条就不带 kHz/ch
  $('#audio-info').textContent = engine.duration > 0 ? `${timecode(engine.duration, { ms: false })} · ${engine.buffer?.sampleRate / 1000 || '?'}kHz · ${engine.buffer?.numberOfChannels || '?'}ch` : '未载入';
  $('#foot-words').textContent = `${store.stats.words} 字 · ${Math.round(store.stats.wpm)} 字/分`;
  $('#btn-undo').disabled = !store.canUndo;
  $('#btn-redo').disabled = !store.canRedo;
}

function syncAll() {
  paintStatus();
  paintSpeakers();
  paintLoop();
  paintSearchHits();
}

/* ---------------------------------------------------------- 对话框 */

function openHelp() {
  const body = document.createElement('div');
  body.className = 'help';
  body.appendChild(buildShortcutTable());
  modal.open({ title: '快捷键与用法', body, width: '880px' });
}

/** 跳到时间点：1:23.5 / 83 / 00:01:23 都认 */
function promptJump() {
  const body = document.createElement('div');
  body.innerHTML = `<div class="field"><label for="jump-input">跳到（1:23.5 / 83 / 00:01:23 都认）</label><input id="jump-input" placeholder="00:26" autocomplete="off" /></div>`;
  const input = body.querySelector('#jump-input');
  const go = () => {
    const parts = input.value.trim().split(':');
    const t = !parts.length || parts.some((p) => p === '' || isNaN(Number(p))) ? null : parts.reduce((a, p) => a * 60 + Number(p), 0);
    if (t == null || t < 0) {
      toaster.warn('看不懂这个时间，试试 1:23.5 这种写法');
      return true;
    }
    seekTo(clamp(t, 0, engine.duration), { user: true });
    return undefined;
  };
  submitOnEnter(input, go, modal);
  modal.open({ title: '跳到时间点', body, width: '420px', actions: [{ label: '取消' }, { label: '跳过去', variant: 'primary', run: go }] });
}

function submitOnEnter(input, run, dialog) {
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (run() === undefined) dialog.close();
  });
}

/**
 * 查找替换。预览用的匹配规则和真正替换的完全一致，
 * 否则会给出和结果对不上的提示。
 */
function openReplaceDialog() {
  const body = document.createElement('div');
  body.innerHTML = `
    <div class="field"><label for="rp-find">查找</label><input type="text" id="rp-find" autofocus /></div>
    <div class="field"><label for="rp-rep">替换为</label><input type="text" id="rp-rep" /></div>
    <label class="switch"><input type="checkbox" id="rp-regex" /><span>用正则表达式</span></label>
    <label class="switch"><input type="checkbox" id="rp-case" /><span>区分大小写</span></label>
    <div class="field-hint" id="rp-preview"></div>
  `;
  const find = body.querySelector('#rp-find');
  const rep = body.querySelector('#rp-rep');
  const rx = body.querySelector('#rp-regex');
  const cs = body.querySelector('#rp-case');
  const prev = body.querySelector('#rp-preview');

  const matcher = () => {
    const f = find.value;
    if (!f) return null;
    const flags = cs.checked ? 'g' : 'gi';
    return rx.checked ? new RegExp(f, flags) : new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags);
  };
  const preview = () => {
    let re;
    try {
      re = matcher();
    } catch (err) {
      return void (prev.textContent = `正则有问题：${err.message}`);
    }
    if (!re) return void (prev.textContent = '');
    const hits = store.doc.segments.filter((s) => re.test(s.text));
    prev.textContent = hits.length ? `${hits.length} 段会被改动。示例：${hits[0].text.replace(re, rep.value || '').slice(0, 60)}` : '没有命中';
  };
  [find, rep].forEach((i) => i.addEventListener('input', preview));
  [rx, cs].forEach((i) => i.addEventListener('change', preview));

  modal.open({
    title: '查找替换',
    body,
    actions: [
      { label: '取消' },
      {
        label: '全部替换',
        variant: 'primary',
        run: () => {
          if (!find.value) {
            toaster.warn('先填查找内容');
            return true;
          }
          let n = 0;
          try {
            n = store.replaceAllText(find.value, rep.value, { regex: rx.checked, caseSensitive: cs.checked });
          } catch (err) {
            toaster.error('替换失败', { detail: String(err.message) });
            return true;
          }
          toaster.ok(n ? `改动了 ${n} 段` : '没有命中任何分段', { action: { label: '撤销', run: () => store.undo() } });
          log('info', '批量替换', `${find.value} → ${rep.value}，${n} 段`);
          transcript.reconcile();
          return undefined;
        },
      },
    ],
  });
}

/** 热词表：每行「错的 = 对的」。专名列表就是这一步的全部输入。 */
function openHotwordsDialog() {
  const body = document.createElement('div');
  body.innerHTML = `
    <p class="field-hint">每行一条，写成「错的 = 对的」。</p>
    <div class="field"><textarea id="hot-words" rows="8" spellcheck="false" placeholder="涨三 = 张三&#10;阿离谱 = Arip"></textarea></div>
    <p class="field-hint" id="hot-count"></p>
  `;
  const area = body.querySelector('#hot-words');
  const count = body.querySelector('#hot-count');
  const pairs = () =>
    area.value
      .split('\n')
      .map((l) => l.split('=').map((x) => x.trim()))
      .filter((p) => p[0] && p[1]);
  const refresh = () => (count.textContent = pairs().length ? `${pairs().length} 条规则` : '还没有有效规则');
  area.addEventListener('input', refresh);
  refresh();
  modal.open({
    title: '热词表替换',
    body,
    width: '560px',
    actions: [
      { label: '取消' },
      {
        label: '应用',
        variant: 'primary',
        run: () => {
          const rules = pairs();
          const total = rules.reduce((acc, [from, to]) => acc + store.replaceAllText(from, to), 0);
          toaster[total ? 'ok' : 'warn'](total ? `共替换 ${total} 段` : '没有命中任何专名');
          transcript.reconcile();
          return undefined;
        },
      },
    ],
  });
}

function clearAll() {
  modal.open({
    title: '清空全部？',
    width: '460px',
    body: '<p style="margin:0">转录文本和音频都会被清掉，本地存档也会重置。这一步不能撤销。</p>',
    actions: [
      { label: '算了' },
      {
        label: '清空',
        variant: 'danger',
        run: () => {
          engine.setBuffer(null);
          store.clearAll();
          transcript.reconcile();
          clearRegion();
          syncAll();
          $('#doc-title').value = store.doc.meta.title;
          toaster.ok('已清空');
        },
      },
    ],
  });
}

function bulkOp(op) {
  if (op === 'merge-short') {
    const n = store.mergeAdjacentShort(1.2);
    toaster.info(n ? `合并了 ${n} 处过短分段` : '没有需要合并的短段');
    transcript.reconcile();
  } else if (op === 'normalize') {
    const n = store.normalizeTimeline();
    toaster.info(n ? `规整了 ${n} 处时间问题` : '时间轴本来就是干净的');
    transcript.reconcile();
  } else if (op === 'replace') openReplaceDialog();
  else if (op === 'hotwords') openHotwordsDialog();
  else if (op === 'parse-srt') $('#file-input').click();
}

/* ------------------------------------------------------ 主题与字号 */

function cycleTheme() {
  const order = ['dark', 'light', 'auto'];
  const next = order[(order.indexOf(store.settings.theme) + 1) % order.length];
  store.setSetting('theme', next);
  applyTheme();
  toaster.info(`主题：${{ dark: '深色', light: '浅色', auto: '跟随系统' }[next]}`, { timeout: 1500 });
}

function applyTheme() {
  const mode = store.settings.theme;
  const dark = mode === 'dark' || (mode === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.body.classList.toggle('reduce-motion', store.settings.reduceMotion);
}

/* ------------------------------------------------------------ 命令 */

/** 命令面板的候选直接由动作表投影出来，不再单独维护一份列表 */
function commands() {
  return Object.entries(ACTIONS)
    .filter(([, a]) => a.title && (!a.when || a.when()))
    .map(([id, a]) => ({ id, title: a.title, group: a.group, shortcut: a.shortcut, keywords: a.keywords, pinned: a.pinned }));
}

/* ------------------------------------------------------------ 接线 */

const palette = createPalette(document.body, {
  getCommands: commands,
  onRun: (cmd) => runAction(cmd.id),
  toaster,
});

function bind() {
  const on = (sel, evt, fn) => $(sel).addEventListener(evt, fn);

  // 按钮接线：HTML 里的 data-action 指到动作表的键。
  // 以前每个按钮在这里写一行，漏写就成了"看得见但点不动"；
  // 现在唯一可能漏的是 HTML 属性，而那一眼就能看出来。
  for (const el of $$('[data-action]')) el.addEventListener('click', () => runAction(el.dataset.action, el.dataset));
  on('#btn-palette', 'click', () => palette.open());
  on('#btn-open', 'click', () => $('#file-input').click());
  on('#btn-demo', 'click', loadDemo);
  on('#btn-zoom-in', 'click', () => waveform.zoomAt(1.4));
  on('#btn-zoom-out', 'click', () => waveform.zoomAt(0.7));
  on('#btn-clear-log', 'click', () => logList.replaceChildren());
  on('#btn-clear-all', 'click', clearAll);
  on('#btn-add-speaker', 'click', () => {
    store.addSpeaker(`说话人 ${Object.keys(store.doc.speakers).length + 1}`);
    paintSpeakers();
    $$('.speaker-row input').at(-1)?.focus();
  });
  on('#speaker-list', 'change', (e) => e.target.dataset.spk && store.renameSpeaker(e.target.dataset.spk, e.target.value.trim() || e.target.dataset.spk));

  // 设置项：每个都是"改 store 再让界面跟上"，没有更聪明的做法
  const settings = {
    '#rate-select': ['change', (e) => (engine.setRate(Number(e.target.value)), store.setSetting('playbackRate', Number(e.target.value), { silent: true }))],
    '#volume': ['input', (e) => engine.setVolume(Number(e.target.value))],
    '#set-font': ['input', (e) => store.setSetting('fontScale', Number(e.target.value), { silent: true })],
    '#set-autoscroll': ['change', (e) => store.setSetting('autoScroll', e.target.checked)],
    '#set-motion': ['change', (e) => (store.setSetting('reduceMotion', e.target.checked), applyTheme())],
    '#doc-title': [
      'change',
      (e) => {
        store.touch((d) => {
          d.meta.title = e.target.value.trim() || '未命名转录';
        });
        document.title = `${store.doc.meta.title} · 转录工作台`;
        markDirtyFlash();
        autosave();
      },
    ],
    '#file-input': ['change', (e) => (handleFiles(e.target.files), (e.target.value = ''))],
  };
  for (const [sel, [evt, fn]] of Object.entries(settings)) on(sel, evt, fn);

  // 波形着色：只留"按说话人 / 单色"两档
  for (const b of $$('.seg-btn[data-mode]')) {
    b.addEventListener('click', () => {
      for (const o of $$('.seg-btn[data-mode]')) o.classList.toggle('is-active', o === b);
      store.setSetting('waveColorMode', b.dataset.mode, { silent: true });
      waveform.draw();
    });
  }

  /* 搜索与筛选。筛选是互斥的："只显示低置信"时再叠"只显示待复核"没有意义 */
  const search = $('#search');
  const applyFilter = (next) => {
    transcript.setFilter(next);
    for (const b of $$('[data-filter]')) b.classList.toggle('is-active', b.dataset.filter === next);
    paintSearchHits();
  };
  const clearSearch = () => {
    search.value = '';
    transcript.setQuery('');
    applyFilter(null);
  };
  search.addEventListener('input', () => {
    transcript.setQuery(search.value);
    paintSearchHits();
  });
  search.addEventListener('keydown', (e) => e.key === 'Escape' && (clearSearch(), transcript.focus()));
  on('#btn-filter-clear', 'click', clearSearch);
  for (const b of $$('[data-filter]')) {
    if (b.id !== 'btn-filter-clear') b.addEventListener('click', () => applyFilter(b.classList.contains('is-active') ? null : b.dataset.filter));
  }
  on('#btn-filter-speaker', 'click', () => {
    const spk = store.doc.speakers[currentSeg()?.speaker];
    if (!spk) return toaster.warn('先把光标落到某一段上，再按说话人筛选');
    applyFilter(spk.id);
    toaster.info(`只显示「${spk.name}」的段落`, { action: { label: '取消', run: () => applyFilter(null) } });
  });

  // details 下拉：点完一项自动收起，否则菜单一直挂着挡视线
  for (const d of $$('details.more-menu')) {
    d.addEventListener('click', (e) => e.target.closest('button') && setTimeout(() => (d.open = false), 0));
    d.addEventListener('toggle', () => d.open && $$('details.more-menu').forEach((o) => o !== d && (o.open = false)));
  }

  /* 多选工具栏 */
  on('#sel-clear', 'click', () => runAction('clear-selection'));
  for (const b of $$('[data-bulk]')) b.addEventListener('click', () => bulkSelection(b.dataset.bulk));
  on('#bulk-speaker', 'change', (e) => {
    const ids = transcript.selected;
    if (!e.target.value || !ids.length) return;
    store.commit(`批量改说话人（${ids.length} 段）`, (d) => {
      for (const s of d.segments) if (ids.includes(s.id)) s.speaker = e.target.value;
    });
    e.target.value = '';
  });
  for (const b of $$('[data-bulkop]')) b.addEventListener('click', () => bulkOp(b.dataset.bulkop));

  /* 拖放：整页接收，覆盖浏览器默认的打开行为 */
  let dragDepth = 0;
  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragDepth += 1;
    document.body.classList.add('is-dropping');
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) document.body.classList.remove('is-dropping');
  });
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    dragDepth = 0;
    document.body.classList.remove('is-dropping');
    if (e.dataTransfer?.files?.length) return handleFiles(e.dataTransfer.files);
    // 拖入一段文字也能当转录用（有人就是从聊天窗口直接拖过来的）
    const paras = (e.dataTransfer?.getData('text/plain') || '')
      .split(/\n{2,}/)
      .map((x) => x.trim())
      .filter(Boolean);
    if (!paras.length) return;
    adoptDoc(
      { meta: { title: '拖入的文本', duration: paras.length * 4, source: '拖放文本', engine: '手动' }, segments: paras.map((p, i) => ({ start: i * 4, end: i * 4 + 3.9, speaker: 'spk_a', text: p, edited: true })) },
      `已把拖入的文本当转录载入（${paras.length} 段，时间轴为估算）`,
    );
  });

  /* 全局快捷键。先看焦点，别在输入框里抢按键 */
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    const typing = t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    const key = e.key;
    if (e.metaKey || e.ctrlKey) {
      const k = key.toLowerCase();
      if (!'kfseoz'.includes(k)) return;
      e.preventDefault();
      if (k === 'k') return palette.toggle();
      if (k === 'f') return search.focus();
      if (k === 's') return saveLocal();
      if (k === 'e') return openExportDialog();
      if (k === 'o') return $('#file-input').click();
      return runAction(e.shiftKey ? 'redo' : 'undo');
    }
    if (typing || palette.isOpen || modal.isOpen) return;

    // 单键动作：一个键对一个函数，没有中间层
    const single = {
      ' ': togglePlay,
      '?': openHelp,
      ',': () => stepSegment(-1),
      '.': () => stepSegment(1),
      n: () => stepSegment(1, { play: true }),
      l: toggleLoop,
      b: () => runAction('build-segment-from-region'),
      '[': () => setLoopEdge('start'),
      ']': () => setLoopEdge('end'),
      '0': () => waveform.fit(),
      '+': () => waveform.zoomAt(1.4),
      '=': () => waveform.zoomAt(1.4),
      '-': () => waveform.zoomAt(0.7),
      ArrowLeft: () => engine.nudge(e.shiftKey ? -5 : e.altKey ? -0.05 : -1),
      ArrowRight: () => engine.nudge(e.shiftKey ? 5 : e.altKey ? 0.05 : 1),
      // 这几个以前 waveform.js 在 canvas 上又绑了一遍，同一个键走两遍：
      // → 一次跳 2 秒、+ 一次放 1.4²、Space 开关相消看着像没反应。
      Home: () => seekTo(0, { user: true }),
      End: () => seekTo(engine.duration, { user: true }),
      Escape: () => {
        waveform.selection = null;
        transcript.setSelected([]);
      },
    }[key];
    if (single) {
      e.preventDefault();
      single();
    }
  });

  window.addEventListener('beforeunload', (e) => {
    // 只有真的存在"磁盘上没有的转录改动"才拦。用内容指纹而不是 dirty 标志：
    // 切主题、点筛选这类动作都已经被自动保存，再弹一次是没有意义的拦截。
    if (!store.unsavedWork) return;
    e.preventDefault();
    e.returnValue = '';
  });

  window.addEventListener(
    'resize',
    debounce(() => waveform.draw(), 120),
  );
}

/** 多选工具栏上的批量操作 */
function bulkSelection(op) {
  const ids = transcript.selected;
  if (op === 'merge') store.mergeRange(ids);
  else if (op === 'delete') return runAction('delete', { ids });
  else if (op === 'flag') {
    store.commit('批量标记待复核', (d) => {
      for (const s of d.segments) if (ids.includes(s.id)) s.flag = true;
    });
  } else if (op === 'copy') {
    return copyToClipboard(store.doc.segments.filter((s) => ids.includes(s.id)).map((s) => s.text).join('\n'), `已复制 ${ids.length} 段`);
  }
  transcript.clearSelection();
  transcript.reconcile();
}

/* ------------------------------------------------------------ 启动 */

function bootstrap() {
  const { settings } = store.load();
  applyTheme();
  document.documentElement.style.setProperty('--font-scale', String(settings.fontScale));
  $('#set-autoscroll').checked = settings.autoScroll;
  $('#set-motion').checked = settings.reduceMotion;
  $('#set-font').value = String(settings.fontScale);
  $('#rate-select').value = String(settings.playbackRate);
  waveform.setView(0, 30);
  bind();

  transcript.reconcile();
  syncAll();
  $('#doc-title').value = store.doc.meta.title;
  document.title = `${store.doc.meta.title} · 转录工作台`;

  if (store.doc.segments.length) {
    log('info', '已从本地存档恢复', `${store.doc.segments.length} 段`);
    toaster.info('恢复了上次的转录文本', { timeout: 6000, action: { label: '载入演示音频', run: loadDemo } });
  } else {
    // 第一次打开：直接把演示音频加载好，别让人对着一张空页面发呆
    loadDemo();
  }

  store.subscribe(() => {
    transcript.reconcile();
    syncAll();
    markDirtyFlash();
    autosave();
  });

  log('info', '工作台就绪', `离线可用、无外部请求；${DEMO_SCRIPT.length} 段演示脚本内置`);
  window.__workbench = { store, engine, waveform, transcript, runAction, commands, loadDemo };
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootstrap);
else bootstrap();
