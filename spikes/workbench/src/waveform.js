// 波形层：一个 canvas 上画峰值、说话人色带、时间网格、选区、播放头，外加一条全局迷你条。
//
// 命中测试全在 canvas 上做：时间 <-> 像素的换算只有 xOf/tOf 两个函数，
// 于是"点得准不准"只有一个地方可能出错。

import { clamp, timecode } from './util.js';

const MIN_VIEW_SECONDS = 0.4;
const GRID_STEPS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

export function createWaveform(container, { engine, store, onSelect, onSeek, onRangeCommit } = {}) {
  const canvas = document.createElement('canvas');
  canvas.className = 'wave-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'slider');
  canvas.setAttribute('aria-label', '音频波形，左右方向键移动播放头，回车跳转');
  container.appendChild(canvas);

  const mini = document.createElement('canvas');
  mini.className = 'wave-mini';
  mini.width = 600;
  mini.height = 34;
  mini.title = '点击跳到该位置';
  container.appendChild(mini);
  const mctx = mini.getContext('2d');

  const tip = document.createElement('div');
  tip.className = 'wave-tip';
  tip.hidden = true;
  container.appendChild(tip);

  const ctx = canvas.getContext('2d');
  let dpr = 1;
  let width = 0;
  let height = 0;

  let viewStart = 0;
  let viewSpan = 30;
  let hoverTime = null;
  let selection = null; // {start, end}
  let dragging = null; // {mode:'select'|'pan'|'edge-start'|'edge-end', anchor}

  /* ------------------------------------------------ 时间 <-> 像素 */

  const xOf = (t) => (viewSpan ? ((t - viewStart) / viewSpan) * width : 0);
  const tOf = (x) => viewStart + (x / Math.max(1, width)) * viewSpan;
  const localX = (e) => clamp(e.clientX - canvas.getBoundingClientRect().left, 0, width);
  const localT = (e) => clamp(tOf(localX(e)), 0, engine.duration);
  const segmentAt = (t) => store.doc.segments.find((s) => t >= s.start && t <= s.end) || null;

  function cssVar(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function setView(start, span) {
    const dur = engine.duration || 1;
    viewSpan = clamp(span, Math.min(MIN_VIEW_SECONDS, dur), Math.max(dur, 1));
    viewStart = clamp(start, 0, Math.max(0, dur - viewSpan));
    draw();
  }

  function zoomAt(factor, anchorTime = null) {
    const anchor = anchorTime == null ? viewStart + viewSpan / 2 : anchorTime;
    const ratio = viewSpan ? (anchor - viewStart) / viewSpan : 0.5;
    const nextSpan = clamp(viewSpan / factor, MIN_VIEW_SECONDS, engine.duration || 1);
    setView(anchor - ratio * nextSpan, nextSpan);
  }

  const fit = () => setView(0, engine.duration || 1);

  /** 保证 t 在可视区内：靠近边缘时整屏滚 1/3，而不是每帧都滚（不然会抖） */
  function keepVisible(t, weight = 0.35) {
    if (t < viewStart + viewSpan * 0.08 || t > viewStart + viewSpan * 0.92) setView(t - viewSpan * weight, viewSpan);
  }

  /* ------------------------------------------------------------ 绘制 */

  function draw() {
    const dur = engine.duration || 0;
    const bg = cssVar('--wave-bg', '#101319');
    const grid = cssVar('--wave-grid', 'rgba(255,255,255,.08)');
    const waveColor = cssVar('--wave-fg', '#7ea6ff');
    const dimWave = cssVar('--wave-fg-dim', 'rgba(126,166,255,.35)');
    const textColor = cssVar('--text-dim', '#8b93a7');
    const accent = cssVar('--accent', '#ff6b3d');
    const showSpeakers = store.settings.waveColorMode === 'speaker';
    const bandH = showSpeakers ? Math.max(8, height * 0.12) : 0;
    const waveTop = bandH + (showSpeakers ? 4 : 0);
    const waveH = height - waveTop;
    const mid = waveTop + waveH / 2;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    // 声部色带：谁在说话一眼可见
    if (showSpeakers) {
      for (const seg of store.doc.segments) {
        if (seg.end < viewStart || seg.start > viewStart + viewSpan) continue;
        const x1 = Math.max(0, xOf(seg.start));
        const x2 = Math.min(width, xOf(seg.end));
        ctx.fillStyle = store.doc.speakers[seg.speaker]?.color || '#666';
        ctx.globalAlpha = 0.85;
        ctx.fillRect(x1, 0, Math.max(1, x2 - x1), bandH);
        ctx.globalAlpha = 1;
      }
    }

    // 时间网格：按可视跨度挑一个"整"间隔
    const step = GRID_STEPS.find((s) => s >= viewSpan / 10) || 600;
    ctx.strokeStyle = grid;
    ctx.fillStyle = textColor;
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textBaseline = 'top';
    for (let t = Math.floor(viewStart / step) * step; t <= viewStart + viewSpan; t += step) {
      const x = Math.round(xOf(t)) + 0.5;
      if (x < -40 || x > width + 40) continue;
      ctx.beginPath();
      ctx.moveTo(x, waveTop);
      ctx.lineTo(x, height);
      ctx.stroke();
      ctx.fillText(timecode(t, { ms: step < 1 }).slice(step < 60 ? 3 : 0), x + 3, height - 14);
    }

    // 波形
    if (engine.buffer) {
      const buckets = Math.max(80, Math.floor(width));
      const peaks = engine.peaks(buckets);
      const pxPerBucket = width / buckets;
      for (let b = 0; b < buckets; b += 1) {
        const x = b * pxPerBucket;
        const y1 = mid - peaks[b * 2 + 1] * (waveH / 2 - 4);
        const y2 = mid - peaks[b * 2] * (waveH / 2 - 4);
        if (showSpeakers) {
          const seg = segmentAt(viewStart + (b / buckets) * viewSpan);
          ctx.fillStyle = seg ? store.doc.speakers[seg.speaker]?.color || waveColor : dimWave;
        } else {
          ctx.fillStyle = waveColor;
        }
        ctx.fillRect(x, y1, Math.max(1, pxPerBucket * 0.9), Math.max(1, y2 - y1));
      }
    } else {
      ctx.fillStyle = textColor;
      ctx.font = '13px system-ui, sans-serif';
      ctx.textBaseline = 'middle';
      ctx.fillText('还没有音频：拖入文件，或点"演示音频"', 16, mid);
    }

    // 选区与循环区间
    if (selection) {
      const x1 = xOf(selection.start);
      const x2 = xOf(selection.end);
      ctx.fillStyle = cssVar('--select-fill', 'rgba(255,107,61,.18)');
      ctx.fillRect(x1, bandH, x2 - x1, height - bandH);
      ctx.strokeStyle = accent;
      for (const x of [x1, x2]) {
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, bandH);
        ctx.lineTo(Math.round(x) + 0.5, height);
        ctx.stroke();
      }
    }
    if (engine.loop) {
      ctx.fillStyle = cssVar('--loop-fill', 'rgba(65,184,131,.16)');
      ctx.fillRect(xOf(engine.loop.start), bandH, xOf(engine.loop.end) - xOf(engine.loop.start), height - bandH);
    }

    // 播放头
    if (dur > 0) {
      const x = Math.round(xOf(engine.time)) + 0.5;
      if (x >= -2 && x <= width + 2) {
        ctx.strokeStyle = accent;
        ctx.fillStyle = accent;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, waveTop);
        ctx.lineTo(x, height);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - 6, bandH);
        ctx.lineTo(x + 6, bandH);
        ctx.lineTo(x, bandH + 8);
        ctx.closePath();
        ctx.fill();
        ctx.lineWidth = 1;
      }
    }

    // hover 参考线
    if (hoverTime != null && !dragging) {
      ctx.strokeStyle = cssVar('--hover-line', 'rgba(255,255,255,.35)');
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(Math.round(xOf(hoverTime)) + 0.5, bandH);
      ctx.lineTo(Math.round(xOf(hoverTime)) + 0.5, height);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 左上角：当前窗口范围与缩放倍数
    if (dur > 0) {
      ctx.fillStyle = textColor;
      ctx.font = '11px ui-monospace, Menlo, monospace';
      ctx.textBaseline = 'top';
      ctx.fillText(`${timecode(viewStart, { ms: false })} – ${timecode(viewStart + viewSpan, { ms: false })}   ×${(dur / viewSpan).toFixed(1)}`, 10, showSpeakers ? bandH + 6 : 6);
    }
  }

  function drawMini() {
    const dur = engine.duration || 1;
    const w = mini.width;
    const h = mini.height;
    mctx.clearRect(0, 0, w, h);
    mctx.fillStyle = cssVar('--wave-mini-bg', 'rgba(255,255,255,.04)');
    mctx.fillRect(0, 0, w, h);
    if (engine.buffer) {
      const peaks = engine.peaks(w);
      mctx.fillStyle = cssVar('--wave-fg-dim', 'rgba(126,166,255,.5)');
      for (let b = 0; b < w; b += 1) {
        const y1 = h / 2 - peaks[b * 2 + 1] * (h / 2 - 3);
        const y2 = h / 2 - peaks[b * 2] * (h / 2 - 3);
        mctx.fillRect(b, y1, 1, Math.max(1, y2 - y1));
      }
    }
    const x1 = (viewStart / dur) * w;
    const w1 = Math.max(2, ((viewStart + viewSpan) / dur) * w - x1);
    mctx.fillStyle = cssVar('--select-fill', 'rgba(255,107,61,.2)');
    mctx.fillRect(x1, 0, w1, h);
    mctx.strokeStyle = cssVar('--accent', '#ff6b3d');
    mctx.strokeRect(x1 + 0.5, 0.5, w1 - 1, h - 1);
    mctx.fillStyle = cssVar('--accent', '#ff6b3d');
    mctx.fillRect((engine.time / dur) * w, 0, 1.5, h);
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = container.clientWidth;
    height = container.clientHeight - mini.height - 8;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(Math.max(1, height) * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
    drawMini();
  }

  /* ------------------------------------------------------------ 事件 */

  function nearEdge(t) {
    if (!selection) return null;
    const tol = 6 / (width / viewSpan);
    if (Math.abs(t - selection.start) <= tol) return 'edge-start';
    if (Math.abs(t - selection.end) <= tol) return 'edge-end';
    return null;
  }

  canvas.addEventListener('pointerdown', (e) => {
    if (e.button === 1 || (e.button === 0 && (e.altKey || (e.metaKey && e.shiftKey)))) {
      dragging = { mode: 'pan', origin: localT(e), startView: viewStart };
      canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    if (e.button !== 0) return;
    const t = localT(e);
    const edge = nearEdge(t);
    dragging = edge
      ? { mode: edge, anchor: edge === 'edge-start' ? selection.end : selection.start }
      : { mode: 'select', anchor: t, moved: false, additive: e.shiftKey || e.metaKey || e.ctrlKey };
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener('pointermove', (e) => {
    const t = localT(e);
    hoverTime = t;
    if (!dragging) {
      const seg = segmentAt(t);
      const sp = seg ? store.doc.speakers[seg.speaker]?.name : null;
      tip.hidden = false;
      tip.textContent = `${timecode(t, { ms: viewSpan < 10 })}${sp ? `  ·  ${sp}` : ''}`;
      tip.style.left = `${clamp(e.clientX - canvas.getBoundingClientRect().left + 8, 4, Math.max(4, width - 140))}px`;
      draw();
      return;
    }
    if (dragging.mode === 'pan') {
      setView(dragging.startView - (localT(e) - dragging.origin), viewSpan);
      return;
    }
    if (dragging.mode === 'select' && !dragging.moved && Math.abs(t - dragging.anchor) * (width / viewSpan) > 3) dragging.moved = true;
    const anchor = dragging.anchor;
    if (dragging.mode === 'select' && !dragging.moved) {
      draw();
      return;
    }
    selection = { start: Math.min(anchor, t), end: Math.max(anchor, t) };
    draw();
  });

  canvas.addEventListener('pointerup', (e) => {
    if (!dragging) return;
    const { mode, moved } = dragging;
    dragging = null;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* 指针已经释放 */
    }
    const t = localT(e);
    if (mode === 'select') {
      if (!moved) {
        const additive = e.shiftKey || e.metaKey || e.ctrlKey;
        selection = additive ? { start: Math.min(selection?.start ?? t, t), end: Math.max(selection?.end ?? t, t) } : null;
        onSeek?.(t, { user: true });
      } else {
        const seg = segmentAt((selection.start + selection.end) / 2);
        if (seg) onSelect?.(seg.id);
        onRangeCommit?.(selection);
      }
    } else if (mode === 'edge-start' || mode === 'edge-end') {
      if (selection && selection.end - selection.start > 0.2) onRangeCommit?.(selection);
      else selection = null;
    }
    draw();
  });

  canvas.addEventListener('pointercancel', () => {
    dragging = null;
  });

  canvas.addEventListener('pointerleave', () => {
    hoverTime = null;
    tip.hidden = true;
    draw();
  });

  // 滚轮平移，按住修饰键缩放（和多数波形编辑器一致）
  canvas.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey || e.shiftKey) zoomAt(e.deltaY < 0 ? 1.25 : 0.8, localT(e));
      else setView(viewStart + (viewSpan / width) * (e.deltaY + e.deltaX) * 2, viewSpan);
    },
    { passive: false },
  );

  canvas.addEventListener('dblclick', (e) => {
    const seg = segmentAt(localT(e));
    if (!seg) return;
    selection = { start: seg.start, end: seg.end };
    onSelect?.(seg.id);
    onRangeCommit?.(selection);
    draw();
  });

  // 迷你条：点一下就跳过去
  mini.addEventListener('pointerdown', (e) => {
    const ratio = clamp((e.clientX - mini.getBoundingClientRect().left) / mini.getBoundingClientRect().width, 0, 1);
    setView(ratio * (engine.duration || 0) - viewSpan / 2, viewSpan);
  });

  const ro = new ResizeObserver(() => resize());
  ro.observe(container);
  resize();

  return {
    canvas,
    draw() {
      draw();
      drawMini();
    },
    drawMini,
    setView,
    zoomAt,
    fit,
    keepVisible,
    get selection() {
      return selection;
    },
    set selection(v) {
      selection = v;
      draw();
    },
    getView: () => ({ viewStart, viewSpan }),
    destroy() {
      ro.disconnect();
      canvas.remove();
      mini.remove();
      tip.remove();
    },
  };
}
