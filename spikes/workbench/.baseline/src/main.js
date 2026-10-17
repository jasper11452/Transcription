// 装配层：唯一知道"谁认识谁"的地方。
// store / audio / waveform / transcript 之间互不引用，所有接线都在这里，
// 于是要替换任何一层（换引擎、换波形渲染、换列表实现）都只需要动这一个文件。

import { createStore } from './store.js';
import { createAudioEngine, decodeFile, buildDemoAudio, demoDoc, DEMO_SCRIPT } from './audio.js';
import { createWaveform } from './waveform.js';
import { createTranscriptList } from './transcript.js';
import { createPalette } from './palette.js';
import { createToaster, createModal, buildShortcutTable } from './ui.js';
import { buildExport, EXPORTERS, parseSrt } from './export.js';
import { timecode, clock, hms, clamp, uid, debounce, download, escapeHtml, charDiff, countWords } from './util.js';

const $ = (sel) => document.querySelector(sel);

const store = createStore();
const toaster = createToaster(document.body);
const modal = createModal(document.body);

/* ------------------------------------------------------------ 日志面板 */

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

/* -------------------------------------------------------------- 音频层 */

const engine = createAudioEngine({
  onTime: (t, dur) => {
    paintTime(t, dur);
    waveform.draw();
    waveform.drawMini();
    playerUI(t);
  },
  onState: ({ playing }) => {
    document.body.classList.toggle('mode-playback', playing);
    $('#play-icon').innerHTML = `<use href="#i-${playing ? 'pause' : 'play'}"/>`;
    $('#btn-play').setAttribute('aria-pressed', String(playing));
  },
  onError: (e) => log('error', '播放出错', String(e?.message || e)),
});

/* ------------------------------------------------------------- 波形视图 */

const waveform = createWaveform($('#wave-wrap'), {
  engine,
  store,
  onSeek: (t, opts) => seekTo(t, opts),
  onSelect: (id) => {
    transcript.setCursor(id);
    transcript.setSelected([id]);
  },
  onRangeCommit: (range) => {
    // 拖出的范围直接变成一个分段：这是"用波形做校对"最省事的一条路
    transcript.list.focus();
    applyRegion(range);
  },
});

/* ------------------------------------------------------------- 转录列表 */

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

/* ------------------------------------------------------ 播放头 <-> 循环 */

function paintTime(t, dur) {
  $('#time-current').textContent = timecode(t, { ms: false });
  $('#time-total').textContent = timecode(dur || engine.duration, { ms: false });
  $('#status-playhead').textContent = `播放头：${timecode(t)}`;
  const el = $('#seg-scroll');
  void el;
}

function playerUI(t) {
  transcript.paintActive(t);
  if (store.settings.followPlayhead && engine.playing && store.settings.autoScroll) {
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
  waveform.drawMini();
  playerUI(t);
  paintTime(t, engine.duration);
}

/* ---------------------------------------------------------------- 选区 */

function applyRegion(range) {
  if (!range || range.end - range.start < 0.15) return;
  const sel = { start: range.start, end: range.end };
  waveform.selection = sel;
  const covering = store.doc.segments.filter((s) => s.start < sel.end && s.end > sel.start).map((s) => s.id);
  if (covering.length) {
    transcript.setSelected(covering);
    if (covering.length === 1) transcript.setCursor(covering[0]);
  } else {
    transcript.clearSelection();
  }
  paintRegionInfo(sel);
}

function paintRegionInfo(sel) {
  const box = $('#region-info');
  if (!sel) {
    box.hidden = true;
    $('#status-sel').textContent = '选区：无';
    return;
  }
  box.hidden = false;
  const dur = sel.end - sel.start;
  const covered = store.doc.segments.filter((s) => s.start < sel.end && s.end > sel.start);
  const words = covered.reduce((a, s) => a + countWords(s.text), 0);
  $('#region-text').textContent = `${timecode(sel.start)} → ${timecode(sel.end)}（${dur.toFixed(2)}s，${covered.length} 段，${words} 字）`;
  $('#status-sel').textContent = `选区：${clock(dur)}`;
}

function clearRegion() {
  waveform.selection = null;
  paintRegionInfo(null);
}

/* -------------------------------------------------------------- 动作集 */

const SPEAKER_CYCLE = () => Object.keys(store.doc.speakers);

function runAction(action, payload = {}) {
  switch (action) {
    case 'toggle-play':
      engine.toggle();
      break;

    case 'play-next-segment': {
      const t = engine.time;
      const next = store.doc.segments.find((s) => s.start > t + 0.05) || store.doc.segments[0];
      if (next) seekTo(next.start + 0.01, { user: true, segment: next });
      engine.play();
      break;
    }

    case 'prev-segment': {
      const t = engine.time;
      const list = store.doc.segments;
      const cur = list.find((s) => t >= s.start && t <= s.end);
      let target = cur && t - cur.start > 1.2 ? cur : null;
      if (!target) {
        const before = list.filter((s) => s.end <= t + 0.05);
        target = before[before.length - 1] || list[0];
      }
      if (target) seekTo(target.start + 0.01, { user: true, segment: target });
      break;
    }

    case 'next-segment': {
      const t = engine.time;
      const after = store.doc.segments.find((s) => s.start > t + 0.05);
      if (after) seekTo(after.start + 0.01, { user: true, segment: after });
      else engine.seek(engine.duration);
      break;
    }

    case 'seek': {
      seekTo(payload.time ?? engine.time, { user: true, nudge: true });
      break;
    }

    case 'seek-delta': {
      seekTo(clamp(engine.time + payload.delta, 0, engine.duration), { user: true, nudge: true });
      break;
    }

    case 'jump-time': {
      promptJump();
      break;
    }

    case 'split': {
      const id = payload.id || transcript.cursor || transcript.activeSegmentId();
      if (!id) {
        toaster.warn('先把光标放到某一段上再拆分');
        return;
      }
      const at = payload.at ?? engine.time;
      const res = store.splitSegment(id, at);
      // store 返回 null 表示"切不动"（段太短或 id 不存在），必须说出来，不能当成成功
      if (!res) {
        toaster.warn('这一段太短，切不动（两半各需至少 0.2 秒）');
        return;
      }
      log('info', '拆分段', `${timecode(res.head.start)} + ${timecode(res.tail.start)}`);
      break;
    }

    case 'merge': {
      const id = payload.id || transcript.cursor;
      if (!id) return;
      const list = store.doc.segments;
      const i = list.findIndex((s) => s.id === id);
      if (i < 0 || i >= list.length - 1) {
        toaster.warn('这是最后一段，没有可合并的下一段');
        return;
      }
      store.mergeWithNext(id);
      break;
    }

    case 'insert': {
      const id = payload.id || transcript.cursor;
      const i = store.doc.segments.findIndex((s) => s.id === id);
      const seg = store.insertAfter(i);
      transcript.reconcile();
      transcript.setCursor(seg.id);
      transcript.beginEdit(seg.id);
      break;
    }

    case 'delete': {
      const ids = payload.ids || (transcript.selected.length ? transcript.selected : [transcript.cursor].filter(Boolean));
      if (!ids.length) return;
      const removed = store.deleteSegments(ids);
      transcript.clearSelection();
      toaster.info(`删除了 ${removed} 段`, {
        action: { label: '撤销', run: () => store.undo() },
      });
      break;
    }

    case 'toggle-flag': {
      store.toggleFlag(payload.id);
      break;
    }

    case 'cycle-speaker': {
      const order = SPEAKER_CYCLE();
      const seg = store.doc.segments.find((s) => s.id === payload.id);
      if (!seg) return;
      const i = order.indexOf(seg.speaker);
      const next = order[(i + 1) % order.length];
      store.setSpeaker(seg.id, next);
      toaster.info(`改为「${store.doc.speakers[next].name}」`, { timeout: 1600 });
      break;
    }

    case 'explain-confidence': {
      const seg = store.doc.segments.find((s) => s.id === payload.id);
      if (!seg) return;
      modal.open({
        title: '这一段为什么可疑',
        width: '560px',
        body: `
          <p style="margin-top:0">引擎给这一段的置信度是 <strong>${typeof seg.confidence === 'number' ? (seg.confidence * 100).toFixed(1) + '%' : '未提供'}</strong>。</p>
          <p class="side-note">低于 72% 会被标黄。置信度来自引擎自己的对齐结果，不是我们重新判断的——它的意义是"这里值得看一眼"，不是"这里一定是错的"。</p>
          <ul class="side-note">
            <li>时长：${(seg.end - seg.start).toFixed(2)} 秒（过短常意味着被切碎）</li>
            <li>字数：${countWords(seg.text)}</li>
            <li>${seg.edited ? '已经手动改过' : '尚未手动改过'}</li>
          </ul>
        `,
        actions: [
          { label: '标为待复核', run: () => store.toggleFlag(seg.id) },
          { label: '播放这一段', variant: 'primary', run: () => { seekTo(seg.start, { user: true, segment: seg }); engine.play(); } },
        ],
      });
      break;
    }

    case 'build-segment-from-region': {
      const sel = waveform.selection;
      if (!sel) {
        toaster.warn('先在波形上拖出一段范围');
        return;
      }
      const covering = store.doc.segments.filter((s) => s.start < sel.end && s.end > sel.start);
      store.commit('用选区建分段', (d) => {
        const seg = {
          id: uid('seg'),
          start: sel.start,
          end: sel.end,
          speaker: covering[0]?.speaker || Object.keys(d.speakers)[0],
          text: '',
          edited: true,
        };
        // 与已有分段重叠的先裁掉，避免时间轴出现交叠（交叠会让播放定位变得不可解释）
        for (const s of d.segments) {
          if (s.start >= sel.start && s.end <= sel.end) {
            s.__drop = true;
          } else if (s.start < sel.start && s.end > sel.end) {
            const tail = { ...s, id: uid('seg'), start: sel.end, text: '', edited: true };
            s.end = sel.start;
            d.segments.splice(d.segments.indexOf(s) + 1, 0, tail);
            break;
          } else if (s.start < sel.end && s.start >= sel.start) {
            s.start = sel.end;
          } else if (s.end > sel.start && s.end <= sel.end) {
            s.end = sel.start;
          }
        }
        d.segments = d.segments.filter((s) => !s.__drop);
        const at = d.segments.findIndex((s) => s.start > seg.start);
        d.segments.splice(at < 0 ? d.segments.length : at, 0, seg);
        return seg;
      });
      transcript.reconcile();
      toaster.ok('已按选区建立新分段，直接输入文字即可');
      break;
    }

    case 'toggle-loop-segment': {
      const id = transcript.cursor || transcript.activeSegmentId();
      const seg = store.doc.segments.find((s) => s.id === id);
      if (!seg) {
        toaster.warn('先选一段');
        return;
      }
      if (engine.loop && Math.abs(engine.loop.start - seg.start) < 0.01) {
        engine.setLoop(0, 0);
        $('#btn-loop').setAttribute('aria-pressed', 'false');
      } else {
        engine.setLoop(seg.start, seg.end);
        $('#btn-loop').setAttribute('aria-pressed', 'true');
        seekTo(seg.start + 0.01);
        engine.play();
      }
      break;
    }

    case 'loop-region': {
      const sel = waveform.selection;
      if (!sel) {
        toaster.warn('先框选一段');
        return;
      }
      engine.setLoop(sel.start, sel.end);
      $('#btn-loop').setAttribute('aria-pressed', 'true');
      seekTo(sel.start + 0.01);
      engine.play();
      break;
    }

    case 'set-loop-start': {
      const t = engine.time;
      const end = engine.loop?.end ?? Math.min(engine.duration, t + 5);
      engine.setLoop(t, end);
      toaster.info(`循环起点 ${timecode(t)}`);
      break;
    }

    case 'set-loop-end': {
      const t = engine.time;
      const start = engine.loop?.start ?? Math.max(0, t - 5);
      engine.setLoop(start, t);
      toaster.info(`循环终点 ${timecode(t)}`);
      break;
    }

    case 'toggle-skip-silence': {
      const on = !document.body.classList.contains('skip-silence');
      document.body.classList.toggle('skip-silence', on);
      engine.skipSilence = on; // 走公开 setter；之前写的 engine.__skip 是死代码，实际不会跳过任何静音
      $('#btn-skip-silence').setAttribute('aria-pressed', String(on));
      toaster.info(on ? '跳过静音：开' : '跳过静音：关');
      break;
    }

    case 'zoom-in':
      waveform.zoomAt(1.4);
      break;
    case 'zoom-out':
      waveform.zoomAt(0.7);
      break;
    case 'zoom-fit':
      waveform.fit();
      break;

    case 'search-in-transcript':
      $('#search').value = payload.query ?? '';
      transcript.setQuery($('#search').value);
      paintSearchHits();
      $('#seg-scroll').scrollIntoView({ block: 'nearest' });
      break;

    case 'replay-current': {
      const id = transcript.activeSegmentId() || transcript.cursor;
      const seg = store.doc.segments.find((s) => s.id === id);
      if (seg) {
        seekTo(seg.start + 0.01, { user: true });
        engine.play();
      }
      break;
    }

    case 'open-file':
      $('#file-input').click();
      break;

    case 'export':
      openExportDialog();
      break;

    case 'copy-txt':
      copyToClipboard(buildExport(store.doc, 'txt').text, '纯文本已复制');
      break;

    case 'copy-json':
      copyToClipboard(buildExport(store.doc, 'json').text, 'raw.json 已复制');
      break;

    case 'save':
      saveLocal();
      break;

    case 'help':
      openHelp();
      break;

    case 'palette':
      palette.open();
      break;

    case 'undo': {
      const label = store.historyLabels().undo;
      if (store.undo()) toaster.info(`已撤销：${label || '上一步'}`, { timeout: 2000 });
      else toaster.warn('没有可撤销的操作');
      break;
    }

    case 'redo': {
      const label = store.historyLabels().redo;
      if (store.redo()) toaster.info(`已重做：${label || '下一步'}`, { timeout: 2000 });
      else toaster.warn('没有可重做的操作');
      break;
    }

    case 'clear-selection':
      transcript.clearSelection();
      clearRegion();
      break;

    case 'toggle-theme':
      cycleTheme();
      break;

    case 'load-demo':
      loadDemo();
      break;

    default:
      log('warn', `未知动作：${action}`);
  }
}

/* ------------------------------------------------------------ 载入音频 */

async function loadArrayBuffer(buf, meta) {
  const started = performance.now();
  toaster.info('正在解码音频…', { timeout: 0 });
  const audio = await engine.ctx.decodeAudioData(buf.slice(0));
  engine.setBuffer(audio, meta);
  $('#audio-info').textContent = `${timecode(audio.duration, { ms: false })} · ${audio.sampleRate / 1000}kHz · ${audio.numberOfChannels}ch`;
  $('#status-audio').textContent = `音频：${meta.title || '未命名'}（${timecode(audio.duration, { ms: false })}，解码 ${((performance.now() - started) / 1000).toFixed(2)}s）`;
  $('#time-total').textContent = timecode(audio.duration, { ms: false });
  store.touch((d) => {
    d.meta.duration = audio.duration;
    d.meta.title = d.meta.title && d.meta.title !== '未命名转录' ? d.meta.title : meta.title || '未命名转录';
  });
  $('#doc-title').value = store.doc.meta.title;
  waveform.fit();
  waveform.drawMini();
  log('info', `载入音频：${meta.title}`, `${(buf.byteLength / 1048576).toFixed(1)}MB，${timecode(audio.duration)}`);
  return audio;
}

async function loadDemo() {
  try {
    const t0 = performance.now();
    toaster.info('正在合成一段演示音频（约 1–2 秒）…', { timeout: 0 });
    const { audio, meta } = await buildDemoAudio();
    engine.setBuffer(audio, meta);
    $('#audio-info').textContent = `${timecode(audio.duration, { ms: false })} · 合成`;
    $('#time-total').textContent = timecode(audio.duration, { ms: false });
    $('#status-audio').textContent = `音频：演示（合成 ${((performance.now() - t0) / 1000).toFixed(2)}s）`;
    store.replaceDoc(demoDoc(audio.duration));
    transcript.reconcile();
    waveform.fit();
    waveform.drawMini();
    syncAll();
    log('info', '载入演示音频', `13 段，4 个说话人，${timecode(audio.duration)}`);
    toaster.ok('演示音频就绪。按空格播放，或 ⌘K 看都能做什么。', {
      action: { label: '播放', run: () => engine.play(0) },
    });
  } catch (err) {
    log('error', '合成演示音频失败', String(err?.message || err));
    toaster.error('演示音频合成失败', { detail: '这个浏览器的 OfflineAudioContext 可能不可用；可以直接拖入一个音频文件。' });
  }
}

async function handleFiles(files) {
  const list = [...files];
  if (!list.length) return;
  const audioFile = list.find((f) => /^audio\//.test(f.type) || /\.(mp3|wav|m4a|aac|flac|ogg|opus|mp4|mov|webm|mkv)$/i.test(f.name));
  const textFile = list.find((f) => /\.(srt|vtt|txt|json)$/i.test(f.name));
  const jobs = [];
  if (audioFile) jobs.push(loadFile(audioFile));
  if (textFile) jobs.push(loadTextFile(textFile));
  await Promise.all(jobs);
}

async function loadFile(file) {
  try {
    const started = performance.now();
    log('info', `读取文件：${file.name}`, `${(file.size / 1048576).toFixed(1)}MB`);
    const buf = await file.arrayBuffer();
    await loadArrayBuffer(buf, { title: file.name.replace(/\.[^.]+$/, ''), source: file.name, engine: '本机解码' });
    toaster.ok(`已载入 ${file.name}`, { detail: `解码耗时 ${((performance.now() - started) / 1000).toFixed(2)} 秒` });
  } catch (err) {
    log('error', `载入失败：${file.name}`, String(err?.message || err));
    toaster.error('这个文件没能解码', { detail: '浏览器只认它自己支持的编码（mp3/m4a/wav/ogg/webm）。其他格式请先用 ffmpeg 转一下。' });
  }
}

async function loadTextFile(file) {
  try {
    const text = await file.text();
    if (/\.json$/i.test(file.name)) {
      const parsed = JSON.parse(text);
      store.replaceDoc(parsed, { markDirty: true });
      transcript.reconcile();
      syncAll();
      toaster.ok('已导入 raw.json', { detail: `${store.doc.segments.length} 段` });
      return;
    }
    const segs = parseSrt(text);
    if (!segs.length) {
      // 普通文本：按空行切段，时间轴留空，等用户自己对齐
      const paras = text.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean);
      if (!paras.length) throw new Error('这个文本里没有可用内容');
      const each = 4;
      store.replaceDoc(
        {
          meta: { title: file.name.replace(/\.[^.]+$/, ''), duration: paras.length * each, source: file.name, engine: '导入文本' },
          segments: paras.map((p, i) => ({ start: i * each, end: (i + 1) * each - 0.1, speaker: 'spk_a', text: p, edited: true })),
        },
        { markDirty: true },
      );
      transcript.reconcile();
      syncAll();
      toaster.warn('导入的是纯文本：时间轴是估算的，需要人工对齐或配上音频', { detail: `${paras.length} 段` });
      return;
    }
    store.replaceDoc(
      {
        meta: { title: file.name.replace(/\.[^.]+$/, ''), duration: segs[segs.length - 1].end, source: file.name, engine: '导入字幕' },
        segments: segs.map((s) => ({ start: s.start, end: s.end, speaker: 'spk_a', text: s.text, edited: true })),
      },
      { markDirty: true },
    );
    transcript.reconcile();
    syncAll();
    toaster.ok('已导入字幕', { detail: `${segs.length} 段，时间轴来自文件` });
    log('info', `导入字幕：${file.name}`, `${segs.length} 段`);
  } catch (err) {
    log('error', `文本导入失败：${file.name}`, String(err?.message || err));
    toaster.error('这个文本/字幕没能导入', { detail: String(err?.message || err) });
  }
}

/* -------------------------------------------------------------- 录音 */

let recTimer = 0;
async function toggleRecording() {
  const bar = $('#rec-bar');
  if (bar.hidden) {
    try {
      await engine.startRecording();
      bar.hidden = false;
      const t0 = performance.now();
      const meter = $('#rec-meter');
      const mctx = meter.getContext('2d');
      const loop = () => {
        if (bar.hidden) return;
        $('#rec-time').textContent = timecode((performance.now() - t0) / 1000, { ms: false });
        const level = engine.micLevel();
        mctx.clearRect(0, 0, meter.width, meter.height);
        mctx.fillStyle = level > 0.85 ? '#ef5f5f' : level > 0.6 ? '#e0a83c' : '#41b883';
        mctx.fillRect(0, 0, meter.width * level, meter.height);
        recTimer = requestAnimationFrame(loop);
      };
      loop();
      log('info', '开始录音');
    } catch (err) {
      log('error', '麦克风打不开', String(err?.message || err));
      toaster.error('拿不到麦克风', { detail: '浏览器要求 https 或 localhost；也可能是权限被拒绝了。' });
    }
    return;
  }
  cancelAnimationFrame(recTimer);
  bar.hidden = true;
  try {
    const { blob, seconds } = await engine.stopRecording();
    toaster.info(`录音结束 ${seconds.toFixed(1)} 秒，正在解码…`, { timeout: 0 });
    const buf = await blob.arrayBuffer();
    await loadArrayBuffer(buf, { title: `录音 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`, source: '麦克风录音', engine: '本机录音' });
    store.replaceDoc({
      meta: { ...store.doc.meta, title: `录音 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`, source: '麦克风录音' },
      segments: [],
    });
    transcript.reconcile();
    syncAll();
    toaster.ok('录音已就绪', { detail: '这条录音没有转录文本——本页面只做校对，不做识别。' });
  } catch (err) {
    log('error', '录音处理失败', String(err?.message || err));
    toaster.error('录音没能载入', { detail: String(err?.message || err) });
  }
}

/* ------------------------------------------------------ 导出 / 复制 */

function openExportDialog() {
  const body = document.createElement('div');
  body.innerHTML = `
    <div class="export-grid" id="export-grid"></div>
    <div class="field" style="margin-top:16px">
      <label>选项</label>
      <label class="switch"><input type="checkbox" id="exp-ts" /><span>纯文本里带上时间戳</span></label>
      <label class="switch"><input type="checkbox" id="exp-spk" /><span>纯文本里带上说话人</span></label>
      <label class="switch"><input type="checkbox" id="exp-strict" checked /><span>导出前检查：空段、重叠、超长行</span></label>
    </div>
    <div id="export-warn"></div>
    <pre class="preview" id="export-preview" aria-live="polite"></pre>
  `;
  const grid = body.querySelector('#export-grid');
  let current = 'srt';

  function currentDoc() {
    const d = {
      ...store.doc,
      stats: store.stats,
      segments: store.doc.segments.map((s) => ({ ...s })),
    };
    return d;
  }

  function buildWithOptions() {
    const doc = currentDoc();
    if (current === 'txt' || current === 'txt_time' || current === 'txt_speaker') {
      const ts = body.querySelector('#exp-ts').checked;
      const spk = body.querySelector('#exp-spk').checked;
      const kind = ts || spk ? (spk ? 'txt_speaker' : 'txt_time') : 'txt';
      return { ...buildExport(doc, kind), kind };
    }
    return { ...buildExport(doc, current), kind: current };
  }

  function check(doc) {
    const problems = [];
    const empty = doc.segments.filter((s) => !s.text.trim());
    if (empty.length) problems.push(`${empty.length} 段是空的（字幕里会被跳过，txt 里会留空行）`);
    let overlap = 0;
    for (let i = 1; i < doc.segments.length; i += 1) if (doc.segments[i].start < doc.segments[i - 1].end - 0.001) overlap += 1;
    if (overlap) problems.push(`${overlap} 处时间重叠（字幕里会同时显示两行）`);
    const tooLong = doc.segments.filter((s) => s.text.length > 42 && !/[\n]/.test(s.text) && s.end - s.start > 0 && (s.text.length / (s.end - s.start)) > 30);
    if (tooLong.length) problems.push(`${tooLong.length} 段的字数密度过高（可能是把整段塞进一条字幕）`);
    const tooShort = doc.segments.filter((s) => s.end - s.start < 0.5);
    if (tooShort.length) problems.push(`${tooShort.length} 段短于 0.5 秒（字幕会一闪而过）`);
    return problems;
  }

  function renderPreview() {
    const { text, filename } = buildWithOptions();
    body.querySelector('#export-preview').textContent = `${filename}\n${'─'.repeat(30)}\n${text.split('\n').slice(0, 18).join('\n')}\n${text.split('\n').length > 18 ? `… 共 ${text.split('\n').length} 行` : ''}`;
    const warnBox = body.querySelector('#export-warn');
    warnBox.replaceChildren();
    if (body.querySelector('#exp-strict').checked) {
      const problems = check(currentDoc());
      if (problems.length) {
        const box = document.createElement('div');
        box.className = 'field-hint';
        box.style.color = 'var(--warn)';
        box.innerHTML = `导出前检查发现：<br>· ${problems.map(escapeHtml).join('<br>· ')}`;
        warnBox.appendChild(box);
      } else {
        const box = document.createElement('div');
        box.className = 'field-hint';
        box.style.color = 'var(--ok)';
        box.textContent = '检查通过：没有空段、重叠或异常密度。';
        warnBox.appendChild(box);
      }
    }
  }

  for (const [kind, ex] of Object.entries(EXPORTERS)) {
    if (kind === 'txt_time' || kind === 'txt_speaker') continue; // 这两个由选项切换，不单独列
    const btn = document.createElement('button');
    btn.className = 'export-card';
    btn.type = 'button';
    btn.innerHTML = `<strong>${ex.label}</strong><span>${describe(kind)}</span>`;
    btn.addEventListener('click', () => {
      current = kind;
      for (const b of grid.children) b.classList.toggle('export-card-active', b === btn);
      for (const b of grid.children) b.style.borderColor = b === btn ? 'var(--accent)' : '';
      renderPreview();
    });
    grid.appendChild(btn);
  }

  function describe(kind) {
    return {
      txt: '一行一段，最通用',
      srt: '带序号和时间码，字幕软件都认',
      vtt: '带说话人标记，网页播放器用',
      md: '表格，粘进文档里',
      json: '分段级原始数据，给别的工具接',
    }[kind] || '';
  }

  body.querySelectorAll('input').forEach((i) => i.addEventListener('change', renderPreview));
  // 默认选 srt：这个工作台的主要产物
  grid.children[1]?.click();
  renderPreview();

  modal.open({
    title: '导出',
    body,
    width: '760px',
    actions: [
      {
        label: '复制到剪贴板',
        run: () => {
          const { text } = buildWithOptions();
          copyToClipboard(text, '已复制到剪贴板');
        },
      },
      {
        label: '下载文件',
        variant: 'primary',
        run: () => {
          const { text, filename, mime } = buildWithOptions();
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
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
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

/* -------------------------------------------------------------- 保存 */

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
  $('#save-state').textContent = '已自动保存';
  $('#save-state').classList.remove('is-dirty');
  $('#save-state').classList.add('is-saved');
  setTimeout(() => {
    $('#save-state').classList.remove('is-saved');
    if (!store.dirty) $('#save-state').textContent = '已保存到本机';
  }, 1600);
}, 700);

/* --------------------------------------------------------- 提示与帮助 */

function openHelp() {
  modal.open({
    title: '快捷键与用法',
    width: '680px',
    body: buildShortcutTable(),
    actions: [{ label: '知道了', variant: 'primary' }],
  });
}

function promptJump() {
  const body = document.createElement('div');
  body.innerHTML = `
    <div class="field">
      <label for="jump-input">跳到时间点（支持 12:30、750、1:02:03.5 三种写法）</label>
      <input type="text" id="jump-input" value="${timecode(engine.time)}" autofocus />
      <div class="field-hint" id="jump-hint">当前播放位置 ${timecode(engine.time)}</div>
    </div>
  `;
  const input = body.querySelector('#jump-input');
  const hint = body.querySelector('#jump-hint');
  const preview = () => {
    const parsed = parseFlexibleTime(input.value);
    hint.textContent =
      parsed == null
        ? '看不懂这个时间，试试 12:30 或 120.5（秒）'
        : `${timecode(parsed)} · 第 ${nearestSegmentIndex(parsed) + 1} 段`;
    hint.style.color = parsed == null ? 'var(--warn)' : 'var(--text-faint)';
  };
  input.addEventListener('input', preview);
  preview();
  modal.open({
    title: '跳到时间点',
    body,
    actions: [
      { label: '取消' },
      {
        label: '跳转',
        variant: 'primary',
        run: () => {
          const parsed = parseFlexibleTime(input.value);
          if (parsed == null) {
            toaster.warn('这个时间看不懂');
            return false;
          }
          seekTo(parsed, { user: true });
        },
      },
    ],
  });
  setTimeout(() => input.select(), 30);
}

function parseFlexibleTime(raw) {
  const s = String(raw || '').trim();
  if (!s) return null;
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  const parts = s.split(':').map((p) => p.trim());
  if (parts.some((p) => p === '' || isNaN(Number(p)))) return null;
  let total = 0;
  for (const p of parts) total = total * 60 + Number(p);
  return total;
}

function nearestSegmentIndex(t) {
  let best = 0;
  let bestD = Infinity;
  store.doc.segments.forEach((s, i) => {
    const d = Math.min(Math.abs(s.start - t), Math.abs(s.end - t));
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}

/* ------------------------------------------------------------ 主题 */

function cycleTheme() {
  const order = ['dark', 'light', 'auto'];
  const cur = store.settings.theme;
  const next = order[(order.indexOf(cur) + 1) % order.length];
  store.setSetting('theme', next);
  applyTheme();
  toaster.info(`主题：${{ dark: '深色', light: '浅色', auto: '跟随系统' }[next]}`, { timeout: 1500 });
}

function applyTheme() {
  const mode = store.settings.theme;
  const resolved = mode === 'auto' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : mode;
  document.documentElement.dataset.theme = resolved;
  $('#btn-theme').textContent = resolved === 'dark' ? '◐' : '◑';
  document.body.classList.toggle('reduce-motion', store.settings.reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

/* ------------------------------------------------------- 说话人 / 侧栏 */

function paintSpeakers() {
  const listEl = $('#speaker-list');
  const bulkSel = $('#bulk-speaker');
  listEl.replaceChildren();
  const counts = new Map();
  for (const seg of store.doc.segments) counts.set(seg.speaker, (counts.get(seg.speaker) || 0) + 1);

  for (const sp of Object.values(store.doc.speakers)) {
    const li = document.createElement('li');
    li.className = 'speaker-row';
    li.innerHTML = `
      <span class="dot" style="background:${sp.color}"></span>
      <input type="text" value="${escapeHtml(sp.name)}" aria-label="说话人名称" />
      <span class="count">${counts.get(sp.id) || 0}</span>
    `;
    const input = li.querySelector('input');
    input.addEventListener('change', () => store.renameSpeaker(sp.id, input.value || sp.name));
    li.addEventListener('click', () => {
      const first = store.doc.segments.find((s) => s.speaker === sp.id);
      if (first) seekTo(first.start, { user: true, segment: first });
    });
    listEl.appendChild(li);
  }

  const cur = bulkSel.value;
  bulkSel.replaceChildren(new Option('设为说话人…', ''));
  for (const sp of Object.values(store.doc.speakers)) bulkSel.appendChild(new Option(sp.name, sp.id));
  bulkSel.value = cur;
}

function paintStats() {
  const s = store.stats;
  const grid = $('#stat-grid');
  const rows = [
    ['时长', timecode(s.duration, { ms: false })],
    ['分段', String(s.segments)],
    ['字数', String(s.words)],
    ['说话占比', `${(s.coverage * 100).toFixed(1)}%`],
    ['平均段长', `${s.avgSegment.toFixed(2)}s`],
    ['语速', `${s.wpm.toFixed(0)} 字/分`],
    ['手动改动', `${s.edited} 段`],
    ['待复核', `${s.lowConf} 段`],
  ];
  grid.replaceChildren();
  for (const [k, v] of rows) {
    const d = document.createElement('div');
    d.innerHTML = `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`;
    grid.appendChild(d);
  }
  const bars = $('#stat-bars');
  bars.replaceChildren();
  for (const sp of s.speakers) {
    const row = document.createElement('div');
    row.className = 'spk-bar';
    row.title = `${sp.name}：${hms(sp.seconds)}，${sp.segments} 段，${sp.words} 字`;
    row.innerHTML = `
      <span class="spk-bar-name">${escapeHtml(sp.name)}</span>
      <span class="spk-bar-track"><span class="spk-bar-fill" style="width:${(sp.share * 100).toFixed(1)}%;background:${sp.color}"></span></span>
      <span class="spk-bar-val">${(sp.share * 100).toFixed(0)}%</span>
    `;
    bars.appendChild(row);
  }
}

function paintSelectionToolbar(ids) {
  const bar = $('#sel-toolbar');
  bar.hidden = ids.length === 0;
  $('#sel-count').textContent = `已选 ${ids.length} 段`;
  $('#foot-words').textContent = ids.length
    ? `选中 ${ids.reduce((a, id) => a + countWords(store.doc.segments.find((s) => s.id === id)?.text || ''), 0)} 字`
    : `${store.stats.words} 字 · ${hms(store.stats.speakingTime)} 有声音`;
}

function paintSearchHits() {
  const q = transcript.query.trim();
  const el = $('#search-hits');
  if (!q) {
    el.textContent = '';
    $('#seg-count').textContent = `${store.doc.segments.length} 段`;
    return;
  }
  const hits = store.doc.segments.filter((s) => s.text.toLowerCase().includes(q.toLowerCase())).length;
  el.textContent = `${hits} 段命中`;
  $('#seg-count').textContent = `${transcript.visibleCount()} / ${store.doc.segments.length} 段`;
}

function paintStatus() {
  const { undo, redo } = store.historyLabels();
  $('#status-history').textContent = undo ? `可撤销：${undo}` : redo ? `可重做：${redo}` : '无可撤销';
  $('#btn-undo').disabled = !store.canUndo;
  $('#btn-redo').disabled = !store.canRedo;
  const v = waveform.getView();
  $('#status-view').textContent = `视图：${timecode(v.viewStart, { ms: false })}–${timecode(v.viewStart + v.viewSpan, { ms: false })}`;
  $('#status-store').textContent = store.dirty ? '本地存档：有未保存改动' : '本地存档：已同步';
  $('#status-store').classList.toggle('is-warn', store.dirty);
}

function syncAll() {
  paintSpeakers();
  paintStats();
  paintStatus();
  paintSearchHits();
  $('#seg-count').textContent = `${transcript.visibleCount()} / ${store.doc.segments.length} 段`;
  $('#audio-info').textContent =
    engine.duration > 0
      ? `${timecode(engine.duration, { ms: false })} · ${engine.buffer?.sampleRate / 1000 || '?'}kHz · ${engine.buffer?.numberOfChannels || '?'}ch`
      : '未载入';
}

/* --------------------------------------------------------------- 命令 */

function commands() {
  const hasSeg = store.doc.segments.length > 0;
  const hasAudio = engine.duration > 0;
  const sel = waveform.selection;
  return [
    { id: 'play', title: '播放 / 暂停', group: '播放', shortcut: 'Space', pinned: true, run: () => runAction('toggle-play') },
    { id: 'next', title: '播放下一段', group: '播放', shortcut: 'N', run: () => runAction('play-next-segment') },
    { id: 'prev', title: '上一段', group: '播放', shortcut: ',', when: () => hasSeg, run: () => runAction('prev-segment') },
    { id: 'next-s', title: '下一段（不播放）', group: '播放', shortcut: '.', when: () => hasSeg, run: () => runAction('next-segment') },
    { id: 'back5', title: '后退 5 秒', group: '播放', shortcut: '⇧←', when: () => hasAudio, run: () => runAction('seek-delta', { delta: -5 }) },
    { id: 'fwd5', title: '前进 5 秒', group: '播放', shortcut: '⇧→', when: () => hasAudio, run: () => runAction('seek-delta', { delta: 5 }) },
    { id: 'jump', title: '跳到时间点…', group: '播放', keywords: 'goto seek 定位', when: () => hasAudio, run: () => runAction('jump-time') },
    { id: 'rate', title: '切换播放速度', group: '播放', keywords: 'speed 变速', when: () => hasAudio, run: cycleRate },
    { id: 'loop-seg', title: '循环当前段', group: '播放', shortcut: 'L', when: () => hasSeg, run: () => runAction('toggle-loop-segment') },
    { id: 'loop-region', title: '循环选区', group: '播放', when: () => !!sel, run: () => runAction('loop-region') },
    { id: 'skip-sil', title: '跳过静音 开/关', group: '播放', keywords: 'silence vad', when: () => hasAudio, run: () => runAction('toggle-skip-silence') },
    { id: 'replay', title: '重放当前段', group: '播放', shortcut: '↩', when: () => hasSeg, run: () => runAction('replay-current') },
    { id: 'rate1', title: '速度归 1×', group: '播放', when: () => hasAudio, run: () => setRate(1) },

    { id: 'edit', title: '编辑当前段文本', group: '编辑', shortcut: 'E', when: () => hasSeg, run: () => transcript.beginEdit(transcript.cursor || transcript.activeSegmentId()) },
    { id: 'split', title: '在播放头处拆分', group: '编辑', shortcut: 'S', when: () => hasSeg, run: () => runAction('split') },
    { id: 'merge', title: '与下一段合并', group: '编辑', shortcut: 'M', when: () => hasSeg, run: () => runAction('merge') },
    { id: 'insert', title: '在下方插入一段', group: '编辑', shortcut: 'I', when: () => hasSeg, run: () => runAction('insert') },
    { id: 'del', title: '删除选中 / 当前段', group: '编辑', shortcut: 'Del', when: () => hasSeg, run: () => runAction('delete') },
    { id: 'flag', title: '标为待复核', group: '编辑', shortcut: 'F', when: () => hasSeg, run: () => runAction('toggle-flag', { id: transcript.cursor }) },
    { id: 'newseg', title: '用选区建分段', group: '编辑', shortcut: 'B', when: () => !!sel, run: () => runAction('build-segment-from-region') },
    { id: 'mergeshort', title: '合并所有过短分段', group: '编辑', keywords: 'cleanup 清理', when: () => hasSeg, run: () => bulkOp('merge-short') },
    { id: 'normalize', title: '规整时间轴（消除重叠）', group: '编辑', when: () => hasSeg, run: () => bulkOp('normalize') },
    { id: 'replace', title: '查找替换…', group: '编辑', keywords: 'regex 专名', when: () => hasSeg, run: () => bulkOp('replace') },
    { id: 'hotwords', title: '用热词表替换专名…', group: '编辑', keywords: 'hotword 人名 公司', when: () => hasSeg, run: () => bulkOp('hotwords') },

    { id: 'search', title: '搜索转录文本', group: '导航', shortcut: '⌘F', pinned: true, run: () => { $('#search').focus(); $('#search').select(); } },
    { id: 'top', title: '跳到第一段', group: '导航', when: () => hasSeg, run: () => { const s = store.doc.segments[0]; seekTo(s.start, { user: true, segment: s }); transcript.scrollToSegment(s.id); } },
    { id: 'bottom', title: '跳到最后一段', group: '导航', when: () => hasSeg, run: () => { const s = store.doc.segments.at(-1); seekTo(s.start, { user: true, segment: s }); transcript.scrollToSegment(s.id); } },
    { id: 'low', title: '跳到下一个低置信度段', group: '导航', keywords: 'confidence 可疑', when: () => hasSeg, run: jumpLowConfidence },
    { id: 'cursor', title: '按光标段播放', group: '导航', when: () => hasSeg, run: () => { const s = store.doc.segments.find((x) => x.id === transcript.cursor); if (s) seekTo(s.start, { user: true, segment: s }); } },

    { id: 'zoom-in', title: '波形放大', group: '视图', shortcut: '+', when: () => hasAudio, run: () => waveform.zoomAt(1.4) },
    { id: 'zoom-out', title: '波形缩小', group: '视图', shortcut: '-', when: () => hasAudio, run: () => waveform.zoomAt(0.7) },
    { id: 'fit', title: '波形适配整体', group: '视图', shortcut: '0', when: () => hasAudio, run: () => waveform.fit() },
    { id: 'spectrum', title: '实时频谱 开/关', group: '视图', run: () => setSpectrum(!waveform.spectrumOn) },
    { id: 'theme', title: '切换主题（深/浅/跟随系统）', group: '视图', run: cycleTheme },
    { id: 'side', title: '显示/隐藏右侧栏', group: '视图', run: toggleSidebar },
    { id: 'font', title: '放大转录字号', group: '视图', run: () => bumpFont(0.05) },
    { id: 'font-', title: '缩小转录字号', group: '视图', run: () => bumpFont(-0.05) },

    { id: 'export', title: '导出…', group: '文件', shortcut: '⌘E', pinned: true, when: () => hasSeg, run: () => runAction('export') },
    { id: 'copytxt', title: '复制纯文本', group: '文件', when: () => hasSeg, run: () => runAction('copy-txt') },
    { id: 'copyjson', title: '复制 raw.json', group: '文件', when: () => hasSeg, run: () => runAction('copy-json') },
    { id: 'open', title: '打开音频 / 字幕文件…', group: '文件', shortcut: '⌘O', run: () => runAction('open-file') },
    { id: 'demo', title: '载入演示音频（无需素材）', group: '文件', keywords: 'demo 示例', run: loadDemo },
    { id: 'record', title: '录一段音频', group: '文件', keywords: 'mic 麦克风', run: toggleRecording },
    { id: 'save', title: '保存到本机', group: '文件', shortcut: '⌘S', run: () => runAction('save') },
    { id: 'import-srt', title: '导入 .srt 字幕', group: '文件', run: () => { $('#file-input').click(); } },
    { id: 'reset', title: '清空全部（含本地存档）', group: '文件', run: clearAll },

    { id: 'undo', title: '撤销', group: '历史', shortcut: '⌘Z', when: () => store.canUndo, run: () => runAction('undo'), pinned: true },
    { id: 'redo', title: '重做', group: '历史', shortcut: '⇧⌘Z', when: () => store.canRedo, run: () => runAction('redo') },
    { id: 'help', title: '快捷键与用法', group: '帮助', shortcut: '?', pinned: true, run: openHelp },
    { id: 'log', title: '把日志钉到侧栏顶部', group: '帮助', run: () => { $('#log-list').closest('.card').scrollIntoView({ block: 'start' }); } },
    { id: 'stats-log', title: '把当前统计写进日志', group: '帮助', run: () => log('info', '统计快照', `${store.stats.segments} 段 / ${store.stats.words} 字 / 覆盖率 ${(store.stats.coverage * 100).toFixed(1)}%`) },
  ];
}

function cycleRate() {
  const rates = [0.75, 1, 1.25, 1.5, 1.75, 2];
  const cur = Number($('#rate-select').value);
  const next = rates[(rates.indexOf(cur) + 1) % rates.length];
  setRate(next);
}

function setRate(r) {
  $('#rate-select').value = String(r);
  engine.setRate(Number(r));
  store.setSetting('playbackRate', Number(r), { silent: true });
  toaster.info(`播放速度 ${r}×`, { timeout: 1400 });
}

function setSpectrum(on) {
  waveform.setSpectrum(on);
  $('#btn-spectrum').setAttribute('aria-pressed', String(on));
  $('#btn-spectrum').classList.toggle('is-active', on);
  store.setSetting('showSpectrum', on, { silent: true });
}

function bumpFont(delta) {
  const next = clamp(store.settings.fontScale + delta, 0.85, 1.4);
  store.setSetting('fontScale', next);
  document.documentElement.style.setProperty('--font-scale', String(next));
  toaster.info(`字号 ${(next * 100).toFixed(0)}%`, { timeout: 1400 });
}

function toggleSidebar() {
  const side = document.querySelector('.pane-side');
  const hidden = side.style.display === 'none';
  side.style.display = hidden ? '' : 'none';
}

function jumpLowConfidence() {
  const from = store.doc.segments.findIndex((s) => s.id === transcript.cursor);
  const list = store.doc.segments;
  for (let i = 1; i <= list.length; i += 1) {
    const seg = list[(from + i + list.length) % list.length];
    if (typeof seg.confidence === 'number' && seg.confidence < 0.72) {
      transcript.setCursor(seg.id);
      transcript.setSelected([seg.id]);
      transcript.scrollToSegment(seg.id);
      seekTo(seg.start, { user: true, segment: seg });
      return;
    }
  }
  toaster.ok('没有低于 72% 的分段了');
}

function bulkOp(op) {
  switch (op) {
    case 'merge-short': {
      const n = store.mergeAdjacentShort(1.2);
      toaster.info(n ? `合并了 ${n} 处过短分段` : '没有需要合并的短段');
      break;
    }
    case 'normalize': {
      const n = store.normalizeTimeline();
      toaster.info(n ? `规整了 ${n} 处时间问题` : '时间轴本来就是干净的');
      break;
    }
    case 'replace':
      openReplaceDialog();
      break;
    case 'hotwords':
      openHotwordsDialog();
      break;
    case 'parse-srt':
      $('#file-input').click();
      break;
    default:
      break;
  }
}

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

  const preview = () => {
    const f = find.value;
    if (!f) {
      prev.textContent = '';
      return;
    }
    let re;
    try {
      re = rx.checked ? new RegExp(f, cs.checked ? 'g' : 'gi') : new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), cs.checked ? 'g' : 'gi');
    } catch (err) {
      prev.textContent = `正则有问题：${err.message}`;
      prev.style.color = 'var(--danger)';
      return;
    }
    prev.style.color = 'var(--text-faint)';
    const hits = store.doc.segments.filter((s) => re.test(s.text));
    re.lastIndex = 0;
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
            return false;
          }
          let n = 0;
          try {
            n = store.replaceAllText(find.value, rep.value, { regex: rx.checked, caseSensitive: cs.checked });
          } catch (err) {
            toaster.error('替换失败', { detail: String(err.message) });
            return false;
          }
          toaster.ok(n ? `改动了 ${n} 段` : '没有命中任何分段', {
            action: { label: '撤销', run: () => store.undo() },
          });
          log('info', '批量替换', `${find.value} → ${rep.value}，${n} 段`);
        },
      },
    ],
  });
}

function openHotwordsDialog() {
  const sample = '张砚秋=张晏秋\n磬石科技=青石科技\nASR工坊=ASR 工坊';
  const body = document.createElement('div');
  body.innerHTML = `
    <p class="side-note" style="margin-top:0">每行一条 <code>错=对</code>。这是确定性替换，留痕、可撤销、只作用于文本，不碰时间轴。</p>
    <div class="field">
      <label for="hw-area">热词表</label>
      <textarea id="hw-area" spellcheck="false">${escapeHtml(sample)}</textarea>
      <div class="field-hint" id="hw-hint">解析结果会显示在这里</div>
    </div>
  `;
  const area = body.querySelector('#hw-area');
  const hint = body.querySelector('#hw-hint');
  const pairs = () =>
    area.value
      .split('\n')
      .map((l) => l.split('=').map((p) => p.trim()))
      .filter((p) => p.length === 2 && p[0] && p[1]);

  const refresh = () => {
    const p = pairs();
    const hits = p.reduce((acc, [bad]) => acc + store.doc.segments.filter((s) => s.text.includes(bad)).length, 0);
    hint.textContent = `${p.length} 条规则，会命中 ${hits} 段`;
  };
  area.addEventListener('input', refresh);
  refresh();

  modal.open({
    title: '热词表替换',
    body,
    actions: [
      { label: '取消' },
      {
        label: '应用',
        variant: 'primary',
        run: () => {
          const p = pairs();
          if (!p.length) {
            toaster.warn('没有解析出任何规则（格式：错=对）');
            return false;
          }
          store.commit(`热词替换 ${p.length} 条`, (d) => {
            let n = 0;
            for (const seg of d.segments) {
              let t = seg.text;
              for (const [bad, good] of p) t = t.split(bad).join(good);
              if (t !== seg.text) {
                seg.text = t;
                seg.edited = true;
                n += 1;
              }
            }
            return n;
          });
          log('info', '应用热词表', `${p.length} 条规则`);
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

/* -------------------------------------------------------------- 接线 */

const palette = createPalette(document.body, {
  getCommands: commands,
  onRun: (cmd) => runAction(cmd.id, cmd.args),
  toaster,
});

function bind() {
  $('#btn-play').addEventListener('click', () => runAction('toggle-play'));
  $('#btn-demo').addEventListener('click', loadDemo);
  $('#btn-open').addEventListener('click', () => runAction('open-file'));
  $('#btn-record').addEventListener('click', toggleRecording);
  $('#btn-rec-stop').addEventListener('click', toggleRecording);
  $('#btn-export').addEventListener('click', () => runAction('export'));
  $('#btn-undo').addEventListener('click', () => runAction('undo'));
  $('#btn-redo').addEventListener('click', () => runAction('redo'));
  $('#btn-palette').addEventListener('click', () => palette.open());
  $('#btn-help').addEventListener('click', openHelp);
  $('#btn-theme').addEventListener('click', cycleTheme);
  $('#btn-fit').addEventListener('click', () => waveform.fit());
  $('#btn-zoom-in').addEventListener('click', () => waveform.zoomAt(1.4));
  $('#btn-zoom-out').addEventListener('click', () => waveform.zoomAt(0.7));
  $('#btn-spectrum').addEventListener('click', () => setSpectrum(!waveform.spectrumOn));
  $('#btn-loop').addEventListener('click', () => runAction('toggle-loop-segment'));
  $('#btn-skip-silence').addEventListener('click', () => runAction('toggle-skip-silence'));
  $('#btn-prev').addEventListener('click', () => runAction('prev-segment'));
  $('#btn-next').addEventListener('click', () => runAction('next-segment'));
  $('#btn-region-seg').addEventListener('click', () => runAction('build-segment-from-region'));
  $('#btn-region-loop').addEventListener('click', () => runAction('loop-region'));
  $('#btn-region-clear').addEventListener('click', () => runAction('clear-selection'));
  $('#btn-add-speaker').addEventListener('click', () => {
    const id = store.addSpeaker(`说话人 ${Object.keys(store.doc.speakers).length + 1}`);
    const input = [...document.querySelectorAll('.speaker-row input')].at(-1);
    input?.focus();
    input?.select();
    void id;
  });
  $('#btn-clear-log').addEventListener('click', () => logList.replaceChildren());
  $('#btn-copy-json').addEventListener('click', () => runAction('copy-json'));
  $('#btn-copy-txt').addEventListener('click', () => runAction('copy-txt'));
  $('#btn-clear-all').addEventListener('click', clearAll);

  $('#rate-select').addEventListener('change', (e) => setRate(e.target.value));
  $('#volume').addEventListener('input', (e) => engine.setVolume(Number(e.target.value)));

  document.querySelectorAll('.seg-btn[data-mode]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.seg-btn[data-mode]').forEach((b) => b.classList.toggle('is-active', b === btn));
      store.setSetting('waveColorMode', btn.dataset.mode);
      waveform.draw();
    });
  });

  const search = $('#search');
  search.addEventListener('input', () => {
    transcript.setQuery(search.value);
    paintSearchHits();
  });
  search.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      search.value = '';
      transcript.setQuery('');
      paintSearchHits();
      transcript.focus();
    }
  });

/** 筛选按钮的状态必须同时反映到 aria 与 class，否则读屏用户不知道筛没筛 */
  const toggleFilter = (btn, key) => {
    btn.setAttribute('aria-pressed', String(btn.classList.contains('is-active')));
    btn.addEventListener('click', () => {
      const on = !btn.classList.contains('is-active');
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-pressed', String(on));
      transcript.setFilters({ [key]: on });
      paintSearchHits();
    });
  };
  toggleFilter($('#btn-filter-low'), 'lowConf');
  toggleFilter($('#btn-filter-flag'), 'flagged');
  toggleFilter($('#btn-filter-edited'), 'edited');
  $('#btn-filter-clear').addEventListener('click', () => {
    for (const b of document.querySelectorAll('#btn-filter-low, #btn-filter-flag, #btn-filter-edited')) b.classList.remove('is-active');
    transcript.setFilters({ lowConf: false, flagged: false, edited: false, speaker: null });
    $('#search').value = '';
    transcript.setQuery('');
    paintSearchHits();
    toaster.info('已清除全部筛选', { timeout: 1500 });
  });
  $('#btn-filter-speaker').addEventListener('click', () => {
    const id = transcript.cursor ? transcript.segmentById(transcript.cursor)?.speaker : null;
    if (!id) {
      toaster.warn('先把光标落到某一段上，再按说话人筛选');
      return;
    }
    const name = store.doc.speakers[id]?.name || id;
    transcript.setFilters({ speaker: id });
    paintSearchHits();
    toaster.info(`只显示「${name}」的段落`, {
      action: { label: '取消', run: () => { transcript.setFilters({ speaker: null }); paintSearchHits(); } },
    });
  });

  // details 下拉：点一下就收起来，否则菜单会一直挂着挡视线
  for (const d of document.querySelectorAll('details.more-menu')) {
    d.addEventListener('click', (e) => {
      const item = e.target.closest('.more-item, summary');
      if (item && item.tagName === 'BUTTON') setTimeout(() => { d.open = false; }, 0);
    });
    d.addEventListener('toggle', () => {
      if (!d.open) return;
      for (const other of document.querySelectorAll('details.more-menu')) if (other !== d) other.open = false;
    });
  }
  $('#btn-jump').addEventListener('click', () => runAction('jump-time'));
  $('#btn-replay').addEventListener('click', () => runAction('replay-current'));

  $('#sel-clear').addEventListener('click', () => runAction('clear-selection'));
  for (const b of document.querySelectorAll('[data-bulk]')) {
    b.addEventListener('click', () => {
      const ids = transcript.selected;
      switch (b.dataset.bulk) {
        case 'merge':
          store.mergeRange(ids);
          transcript.clearSelection();
          break;
        case 'delete':
          runAction('delete', { ids });
          break;
        case 'flag':
          store.commit('批量标记待复核', (d) => {
            for (const seg of d.segments) if (ids.includes(seg.id)) seg.flag = true;
            return true;
          });
          break;
        case 'copy':
          copyToClipboard(
            store.doc.segments.filter((s) => ids.includes(s.id)).map((s) => s.text).join('\n'),
            `已复制 ${ids.length} 段`,
          );
          break;
        default:
          break;
      }
    });
  }
  $('#bulk-speaker').addEventListener('change', (e) => {
    const ids = transcript.selected;
    if (!e.target.value || !ids.length) return;
    store.commit(`批量改说话人（${ids.length} 段）`, (d) => {
      for (const seg of d.segments) if (ids.includes(seg.id)) seg.speaker = e.target.value;
    });
    e.target.value = '';
  });

  for (const b of document.querySelectorAll('[data-bulkop]')) {
    b.addEventListener('click', () => bulkOp(b.dataset.bulkop));
  }

  $('#set-autoscroll').addEventListener('change', (e) => store.setSetting('autoScroll', e.target.checked));
  $('#set-spectrum').addEventListener('change', (e) => setSpectrum(e.target.checked));
  $('#set-conf').addEventListener('change', (e) => store.setSetting('confidenceHints', e.target.checked));
  $('#set-motion').addEventListener('change', (e) => {
    store.setSetting('reduceMotion', e.target.checked);
    applyTheme();
  });
  $('#set-font').addEventListener('input', (e) => {
    store.setSetting('fontScale', Number(e.target.value), { silent: true });
    document.documentElement.style.setProperty('--font-scale', e.target.value);
  });

  $('#doc-title').addEventListener('change', (e) => {
    store.touch((d) => {
      d.meta.title = e.target.value.trim() || '未命名转录';
    });
    document.title = `${store.doc.meta.title} · 转录工作台`;
    markDirtyFlash();
    autosave();
  });

  $('#file-input').addEventListener('change', (e) => {
    handleFiles(e.target.files);
    e.target.value = '';
  });

  /* 拖放：整页接收，覆盖浏览器默认打开行为 */
  let dragDepth = 0;
  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragDepth += 1;
    document.body.classList.add('is-dropping');
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('dragleave', (e) => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) document.body.classList.remove('is-dropping');
  });
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    dragDepth = 0;
    document.body.classList.remove('is-dropping');
    if (e.dataTransfer?.files?.length) handleFiles(e.dataTransfer.files);
    else if (e.dataTransfer?.getData('text/plain')) {
      // 拖入一段文字也能当转录用（有人就是从聊天窗口拖过来的）
      const text = e.dataTransfer.getData('text/plain');
      const paras = text.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean);
      if (paras.length) {
        store.replaceDoc(
          { meta: { title: '拖入的文本', duration: paras.length * 4, source: '拖放文本', engine: '手动' }, segments: paras.map((p, i) => ({ start: i * 4, end: i * 4 + 3.9, speaker: 'spk_a', text: p, edited: true })) },
          { markDirty: true },
        );
        transcript.reconcile();
        syncAll();
        toaster.ok(`已把拖入的文本当转录载入（${paras.length} 段，时间轴为估算）`);
      }
    }
  });

  /* 全局快捷键。用捕获阶段先看一眼输入焦点，避免在输入框里抢按键 */
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    const typing = t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    const mod = e.metaKey || e.ctrlKey;

    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      palette.toggle();
      return;
    }
    if (mod && e.key.toLowerCase() === 'f') {
      e.preventDefault();
      $('#search').focus();
      $('#search').select();
      return;
    }
    if (mod && e.key.toLowerCase() === 's') {
      e.preventDefault();
      saveLocal();
      return;
    }
    if (mod && e.key.toLowerCase() === 'e') {
      e.preventDefault();
      runAction('export');
      return;
    }
    if (mod && e.key.toLowerCase() === 'o') {
      e.preventDefault();
      runAction('open-file');
      return;
    }
    if (mod && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      runAction(e.shiftKey ? 'redo' : 'undo');
      return;
    }
    if (mod && e.key.toLowerCase() === 'i') {
      e.preventDefault();
      runAction('insert');
      return;
    }

    if (typing || palette.isOpen || modal.isOpen) return;

    switch (e.key) {
      case ' ':
        e.preventDefault();
        runAction('toggle-play');
        break;
      case '?':
        e.preventDefault();
        openHelp();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        runAction('seek-delta', { delta: e.shiftKey ? -5 : e.altKey ? -0.05 : -1 });
        break;
      case 'ArrowRight':
        e.preventDefault();
        runAction('seek-delta', { delta: e.shiftKey ? 5 : e.altKey ? 0.05 : 1 });
        break;
      case ',':
        e.preventDefault();
        runAction('prev-segment');
        break;
      case '.':
        e.preventDefault();
        runAction('next-segment');
        break;
      case 'n':
        e.preventDefault();
        runAction('play-next-segment');
        break;
      case 'l':
        e.preventDefault();
        runAction('toggle-loop-segment');
        break;
      case 'b':
        e.preventDefault();
        runAction('build-segment-from-region');
        break;
      case '[':
        e.preventDefault();
        runAction('set-loop-start');
        break;
      case ']':
        e.preventDefault();
        runAction('set-loop-end');
        break;
      case '0':
        e.preventDefault();
        waveform.fit();
        break;
      case '+':
      case '=':
        e.preventDefault();
        waveform.zoomAt(1.4);
        break;
      case '-':
        e.preventDefault();
        waveform.zoomAt(0.7);
        break;
      case 'r':
        if (!e.shiftKey) {
          e.preventDefault();
          toggleRecording();
        }
        break;
      default:
        break;
    }
  });

  window.addEventListener('beforeunload', (e) => {
    // 只有真的存在"磁盘上没有的转录改动"才拦。
    // 用内容指纹而不是 dirty 标志：切主题、点筛选、播放这类动作都已被自动保存，
    // 再弹一个离开确认是没有意义的拦截（还会让用户以为改动没存住）。
    if (!store.unsavedWork) return;
    e.preventDefault();
    e.returnValue = '';
  });

  window.addEventListener('resize', debounce(() => {
    waveform.draw();
    waveform.drawMini();
  }, 120));
}

/* -------------------------------------------------------------- 启动 */

function bootstrap() {
  const { settings } = store.load();
  applyTheme();
  document.documentElement.style.setProperty('--font-scale', String(settings.fontScale));
  $('#set-autoscroll').checked = settings.autoScroll;
  $('#set-spectrum').checked = settings.showSpectrum;
  $('#set-conf').checked = settings.confidenceHints;
  $('#set-motion').checked = settings.reduceMotion;
  $('#set-font').value = String(settings.fontScale);
  $('#rate-select').value = String(settings.playbackRate);
  waveform.setView(0, 30);
  waveform.setSpectrum(settings.showSpectrum);
  $('#btn-spectrum').setAttribute('aria-pressed', String(settings.showSpectrum));
  $('#btn-spectrum').classList.toggle('is-active', settings.showSpectrum);
  for (const b of document.querySelectorAll('.seg-btn[data-mode]')) b.classList.toggle('is-active', b.dataset.mode === settings.waveColorMode);

  bind();

  // 恢复上次的转录（有存档就接着干）
  if (store.doc.segments.length) {
    transcript.reconcile();
    syncAll();
    $('#doc-title').value = store.doc.meta.title;
    document.title = `${store.doc.meta.title} · 转录工作台`;
    log('info', '已从本地存档恢复', `${store.doc.segments.length} 段`);
    toaster.info('恢复了上次的转录文本', {
      timeout: 6000,
      action: { label: '载入演示音频', run: loadDemo },
    });
  } else {
    syncAll();
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
