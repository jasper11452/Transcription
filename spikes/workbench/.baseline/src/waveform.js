// 波形层：一个 canvas 上画峰值、说话人色带、分段边界、选区、播放头、可选频谱。
//
// 交互全部在 canvas 上做命中测试（时间 <-> 像素两向换算只有一个来源），
// 因此"点击定位"和"拖拽框选"不会出现视觉位置和实际时间对不上的经典 bug。

import { clamp, timecode } from './util.js';

const MIN_VIEW_SECONDS = 0.4;

export function createWaveform(container, { engine, store, onSelect, onSeek, onRangeCommit, onRegionEdit } = {}) {
  const canvas = document.createElement('canvas');
  canvas.className = 'wave-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'slider');
  canvas.setAttribute('aria-label', '音频波形，左右方向键移动播放头，回车跳转');
  container.appendChild(canvas);

  const overlay = document.createElement('div');
  overlay.className = 'wave-overlay';
  container.appendChild(overlay);

  const tip = document.createElement('div');
  tip.className = 'wave-tip';
  tip.hidden = true;
  container.appendChild(tip);

  const ctx = canvas.getContext('2d');
  let dpr = 1;
  let width = 0;
  let height = 0;

  // 视图：viewStart + viewSpan 决定可视时间窗口
  let viewStart = 0;
  let viewSpan = 30;
  let hoverTime = null;
  let selection = null; // {start, end}
  let dragging = null; // {mode:'select'|'pan'|'edge-start'|'edge-end', anchor, originTime}
  let spectrumOn = false;

  const listeners = new Set();

  function state() {
    return { viewStart, viewSpan, selection, hoverTime, duration: engine.duration };
  }

  function emit() {
    for (const fn of listeners) fn(state());
  }

  function xOf(t) {
    if (!viewSpan) return 0;
    return ((t - viewStart) / viewSpan) * width;
  }

  function tOf(x) {
    return viewStart + (x / Math.max(1, width)) * viewSpan;
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = container.clientWidth;
    height = container.clientHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function setView(start, span) {
    const dur = engine.duration || 1;
    viewSpan = clamp(span, Math.min(MIN_VIEW_SECONDS, dur), Math.max(dur, 1));
    viewStart = clamp(start, 0, Math.max(0, dur - viewSpan));
    emit();
    draw();
  }

  function zoomAt(factor, anchorTime = null) {
    const anchor = anchorTime == null ? viewStart + viewSpan / 2 : anchorTime;
    const ratio = viewSpan ? (anchor - viewStart) / viewSpan : 0.5;
    const nextSpan = clamp(viewSpan / factor, MIN_VIEW_SECONDS, engine.duration || 1);
    setView(anchor - ratio * nextSpan, nextSpan);
  }

  function fit() {
    setView(0, engine.duration || 1);
  }

  function centerOn(t, span = null) {
    const s = span ?? viewSpan;
    setView(t - s / 2, s);
  }

  /** 保证 t 在可视区内；靠近边缘时滚动一屏的 1/3，而不是每帧都滚（不然抖） */
  function keepVisible(t, weight = 0.35) {
    if (t < viewStart + viewSpan * 0.08 || t > viewStart + viewSpan * 0.92) {
      setView(t - viewSpan * weight, viewSpan);
    }
  }

  /* ------------------------------------------------------------- 绘制 */

  function roundRect(x, y, w, h, r) {
    const rr = Math.min(r, h / 2, Math.abs(w) / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
    ctx.lineTo(x + rr, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
    ctx.lineTo(x, y + rr);
    ctx.quadraticCurveTo(x, y, x + rr, y);
    ctx.closePath();
  }

  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function draw() {
    const dur = engine.duration || 0;
    const style = getComputedStyle(document.documentElement);
    const bg = cssVar('--wave-bg', '#101319');
    const gridColor = cssVar('--wave-grid', 'rgba(255,255,255,.08)');
    const waveColor = cssVar('--wave-fg', '#7ea6ff');
    const dimWave = cssVar('--wave-fg-dim', 'rgba(126,166,255,.35)');
    const textColor = cssVar('--text-dim', '#8b93a7');
    const playheadColor = cssVar('--accent', '#ff6b3d');

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    // 声部色带（上半：说话人归属；下半：波形），色带让"谁在说"一眼可见
    const showSpeakers = store.settings.waveColorMode === 'speaker';
    const bandH = showSpeakers ? Math.max(8, height * 0.12) : 0;

    if (showSpeakers) {
      for (const seg of store.doc.segments) {
        if (seg.end < viewStart || seg.start > viewStart + viewSpan) continue;
        const x1 = xOf(seg.start);
        const x2 = xOf(seg.end);
        const sp = store.doc.speakers[seg.speaker];
        ctx.fillStyle = sp?.color || '#666';
        ctx.globalAlpha = 0.85;
        ctx.fillRect(Math.max(0, x1), 0, Math.max(1, Math.min(width, x2) - Math.max(0, x1)), bandH);
        ctx.globalAlpha = 1;
      }
      // 色带里的分段边界刻度
      ctx.strokeStyle = gridColor;
      for (const seg of store.doc.segments) {
        const x = Math.round(xOf(seg.start)) + 0.5;
        if (x < 0 || x > width) continue;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, bandH * 0.6);
        ctx.stroke();
      }
    }

    const waveTop = bandH + (showSpeakers ? 4 : 0);
    const waveH = height - waveTop;
    const mid = waveTop + waveH / 2;

    // 时间网格：按可视跨度选一个"整"间隔（0.1s ~ 10min）
    const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
    const step = steps.find((s) => s >= viewSpan / 10) || 600;
    ctx.strokeStyle = gridColor;
    ctx.fillStyle = textColor;
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textBaseline = 'top';
    const first = Math.floor(viewStart / step) * step;
    for (let t = first; t <= viewStart + viewSpan; t += step) {
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
      ctx.fillStyle = waveColor;
      const pxPerBucket = width / buckets;
      for (let b = 0; b < buckets; b += 1) {
        const min = peaks[b * 2];
        const max = peaks[b * 2 + 1];
        const x = b * pxPerBucket;
        const y1 = mid - max * (waveH / 2 - 4);
        const y2 = mid - min * (waveH / 2 - 4);
        if (showSpeakers) {
          const t = viewStart + (b / buckets) * viewSpan;
          const seg = store.doc.segments.find((s) => t >= s.start && t <= s.end);
          ctx.fillStyle = seg ? store.doc.speakers[seg.speaker]?.color || waveColor : dimWave;
        }
        ctx.fillRect(x, y1, Math.max(1, pxPerBucket * 0.9), Math.max(1, y2 - y1));
      }
      ctx.fillStyle = textColor;
    } else {
      ctx.fillStyle = textColor;
      ctx.font = '13px system-ui, sans-serif';
      ctx.textBaseline = 'middle';
      ctx.fillText('还没有音频：拖入文件、点"载入演示音频"，或直接开始录音', 16, mid);
    }

    // 分区着色（选中以外的区域压暗）
    if (selection) {
      const x1 = xOf(selection.start);
      const x2 = xOf(selection.end);
      ctx.fillStyle = cssVar('--select-fill', 'rgba(255,107,61,.18)');
      ctx.fillRect(x1, bandH, x2 - x1, height - bandH);
      ctx.strokeStyle = playheadColor;
      ctx.lineWidth = 1;
      for (const x of [x1, x2]) {
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, bandH);
        ctx.lineTo(Math.round(x) + 0.5, height);
        ctx.stroke();
      }
      ctx.lineWidth = 1;
    }

    // 循环区间
    if (engine.loop) {
      ctx.fillStyle = cssVar('--loop-fill', 'rgba(65,184,131,.16)');
      ctx.fillRect(xOf(engine.loop.start), bandH, xOf(engine.loop.end) - xOf(engine.loop.start), height - bandH);
    }

    // 播放头：三角形把手 + 竖线
    if (dur > 0) {
      const x = Math.round(xOf(engine.time)) + 0.5;
      if (x >= -2 && x <= width + 2) {
        ctx.strokeStyle = playheadColor;
        ctx.fillStyle = playheadColor;
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

    // hover 竖线
    if (hoverTime != null && !dragging) {
      const x = Math.round(xOf(hoverTime)) + 0.5;
      ctx.strokeStyle = cssVar('--hover-line', 'rgba(255,255,255,.35)');
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, bandH);
      ctx.lineTo(x, height);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 刻度提示：如果 viewStart 不为 0，在左上角说明当前窗口
    if (dur > 0) {
      ctx.fillStyle = textColor;
      ctx.font = '11px ui-monospace, Menlo, monospace';
      ctx.textBaseline = 'top';
      const zoomLabel = `${timecode(viewStart, { ms: false })} – ${timecode(viewStart + viewSpan, { ms: false })}`;
      ctx.fillText(`${zoomLabel}   ×${(dur / viewSpan).toFixed(1)}`, 10, showSpeakers ? bandH + 6 : 6);
    }

    // 拉一条局部参考线表示整体里的位置在 minimap 里（不在主 canvas 画，避免噪音）
    void style;
  }

  /* --------------------------------------------------------- 命中测试 */

  function localX(evt) {
    const rect = canvas.getBoundingClientRect();
    return clamp(evt.clientX - rect.left, 0, width);
  }

  function nearEdge(time) {
    if (!selection) return null;
    const pxPerSec = width / viewSpan;
    const tol = Math.max(4, 6) / pxPerSec;
    if (Math.abs(time - selection.start) <= tol) return 'edge-start';
    if (Math.abs(time - selection.end) <= tol) return 'edge-end';
    return null;
  }

  function segmentAt(time) {
    return store.doc.segments.find((s) => time >= s.start && time <= s.end) || null;
  }

  /* ------------------------------------------------------------ 事件 */

  function pointerDown(e) {
    if (e.button === 1 || (e.button === 0 && (e.altKey || e.metaKey && e.shiftKey))) {
      dragging = { mode: 'pan', originTime: tOf(localX(e)), startView: viewStart };
      canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    if (e.button !== 0) return;
    const t = clamp(tOf(localX(e)), 0, engine.duration);
    const edge = nearEdge(t);
    if (edge) {
      dragging = { mode: edge, anchor: edge === 'edge-start' ? selection.end : selection.start };
      canvas.setPointerCapture(e.pointerId);
      return;
    }
    // shift / cmd 拖拽 = 框选；普通拖拽 = 先当作潜在框选，位移超过阈值才成选区，否则算点击定位
    dragging = { mode: 'select', anchor: t, moved: false, additive: e.shiftKey || e.metaKey || e.ctrlKey };
    canvas.setPointerCapture(e.pointerId);
  }

  function pointerMove(e) {
    const t = clamp(tOf(localX(e)), 0, engine.duration);
    hoverTime = t;
    if (!dragging) {
      const seg = segmentAt(t);
      tip.hidden = false;
      const sp = seg ? store.doc.speakers[seg.speaker]?.name : null;
      tip.textContent = `${timecode(t, { ms: viewSpan < 10 })}${sp ? `  ·  ${sp}` : ''}`;
      const rect = canvas.getBoundingClientRect();
      tip.style.left = `${clamp(e.clientX - rect.left + 8, 4, width - 140)}px`;
      draw();
      return;
    }
    if (dragging.mode === 'pan') {
      const dx = (tOf(localX(e)) - dragging.originTime);
      setView(dragging.startView - dx, viewSpan);
      return;
    }
    if (dragging.mode === 'select') {
      if (Math.abs(t - dragging.anchor) * (width / viewSpan) > 3) dragging.moved = true;
      if (dragging.moved) {
        selection = { start: Math.min(dragging.anchor, t), end: Math.max(dragging.anchor, t) };
        emit();
      }
      draw();
      return;
    }
    if (dragging.mode === 'edge-start' || dragging.mode === 'edge-end') {
      const a = dragging.anchor;
      selection = { start: Math.min(a, t), end: Math.max(a, t) };
      emit();
      draw();
    }
  }

  function pointerUp(e) {
    if (!dragging) return;
    const t = clamp(tOf(localX(e)), 0, engine.duration);
    const mode = dragging.mode;
    const moved = dragging.moved;
    dragging = null;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    if (mode === 'select') {
      if (!moved) {
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          selection = { start: Math.min(selection?.start ?? t, t), end: Math.max(selection?.end ?? t, t) };
        } else {
          selection = null;
        }
        onSeek?.(t, { user: true });
        emit();
        draw();
        return;
      }
      const seg = segmentAt((selection.start + selection.end) / 2);
      if (seg && onSelect) onSelect(seg.id, 'waveform');
      onRangeCommit?.(selection);
    } else if (mode === 'edge-start' || mode === 'edge-end') {
      if (selection && selection.end - selection.start > 0.2) onRangeCommit?.(selection);
      else selection = null;
    }
    emit();
    draw();
  }

  function onWheel(e) {
    e.preventDefault();
    const t = clamp(tOf(localX(e)), 0, engine.duration);
    if (e.ctrlKey || e.metaKey || e.shiftKey) {
      zoomAt(e.deltaY < 0 ? 1.25 : 0.8, t);
      return;
    }
    // 不打字的时候滚轮平移；按住 shift 才缩放，和大多数波形编辑器一致
    const shift = (viewSpan / width) * (e.deltaY + e.deltaX) * 2;
    setView(viewStart + shift, viewSpan);
  }

  function onKey(e) {
    const step = e.shiftKey ? 5 : 1;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      const dir = e.key === 'ArrowRight' ? 1 : -1;
      onSeek?.(clamp(engine.time + dir * (e.altKey ? 0.05 : step), 0, engine.duration), { user: true, nudge: true });
    } else if (e.key === 'Home') {
      e.preventDefault();
      onSeek?.(0, { user: true });
    } else if (e.key === 'End') {
      e.preventDefault();
      onSeek?.(engine.duration, { user: true });
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      engine.toggle();
    } else if (e.key === '+' || e.key === '=') {
      zoomAt(1.4);
    } else if (e.key === '-' || e.key === '_') {
      zoomAt(0.7);
    } else if (e.key === '0') {
      fit();
    } else if (e.key === 'Escape') {
      selection = null;
      emit();
      draw();
    }
  }

  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointercancel', pointerUp);
  canvas.addEventListener('pointerleave', () => {
    hoverTime = null;
    tip.hidden = true;
    draw();
  });
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('keydown', onKey);
  canvas.addEventListener('dblclick', (e) => {
    const t = clamp(tOf(localX(e)), 0, engine.duration);
    const seg = segmentAt(t);
    if (seg) {
      selection = { start: seg.start, end: seg.end };
      onSelect?.(seg.id, 'waveform');
      onRangeCommit?.(selection);
      emit();
      draw();
    }
  });

  const ro = new ResizeObserver(() => resize());
  ro.observe(container);

  /* ------------------------------------------------------ 迷你导航条 */

  const mini = document.createElement('canvas');
  mini.className = 'wave-mini';
  mini.width = 600;
  mini.height = 34;
  container.appendChild(mini);
  const mctx = mini.getContext('2d');

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
        const min = peaks[b * 2];
        const max = peaks[b * 2 + 1];
        const y1 = h / 2 - max * (h / 2 - 3);
        const y2 = h / 2 - min * (h / 2 - 3);
        mctx.fillRect(b, y1, 1, Math.max(1, y2 - y1));
      }
    }
    const x1 = (viewStart / dur) * w;
    const x2 = ((viewStart + viewSpan) / dur) * w;
    mctx.fillStyle = cssVar('--select-fill', 'rgba(255,107,61,.2)');
    mctx.fillRect(x1, 0, Math.max(2, x2 - x1), h);
    mctx.strokeStyle = cssVar('--accent', '#ff6b3d');
    mctx.strokeRect(x1 + 0.5, 0.5, Math.max(2, x2 - x1) - 1, h - 1);
    const px = (engine.time / dur) * w;
    mctx.fillStyle = cssVar('--accent', '#ff6b3d');
    mctx.fillRect(px, 0, 1.5, h);
  }

  let miniDrag = null;
  mini.addEventListener('pointerdown', (e) => {
    const rect = mini.getBoundingClientRect();
    const ratio = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    miniDrag = { mode: ratio * (engine.duration || 0) >= viewStart && ratio * (engine.duration || 0) <= viewStart + viewSpan ? 'move' : 'jump', offset: ratio * (engine.duration || 0) - viewStart };
    mini.setPointerCapture(e.pointerId);
    if (miniDrag.mode === 'jump') setView(ratio * engine.duration - viewSpan / 2, viewSpan);
  });
  mini.addEventListener('pointermove', (e) => {
    if (!miniDrag) return;
    const rect = mini.getBoundingClientRect();
    const ratio = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    const t = ratio * engine.duration;
    setView(miniDrag.mode === 'move' ? t - miniDrag.offset : t - viewSpan / 2, viewSpan);
  });
  mini.addEventListener('pointerup', (e) => {
    miniDrag = null;
    try {
      mini.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  });

  /* ----------------------------------------------------- 频谱/电平条 */

  const meter = document.createElement('canvas');
  meter.className = 'wave-meter';
  meter.width = 160;
  meter.height = 34;
  meter.hidden = true;
  container.appendChild(meter);
  const metx = meter.getContext('2d');

  function drawMeter() {
    const { spectrum } = engine.spectrum();
    metx.clearRect(0, 0, meter.width, meter.height);
    metx.fillStyle = cssVar('--wave-mini-bg', 'rgba(255,255,255,.04)');
    metx.fillRect(0, 0, meter.width, meter.height);
    if (!spectrum) return;
    const bars = 32;
    for (let i = 0; i < bars; i += 1) {
      const v = spectrum[Math.floor((i / bars) * (spectrum.length * 0.7))] / 255;
      const h = Math.pow(v, 1.4) * meter.height;
      const hue = 200 - v * 160;
      metx.fillStyle = `hsl(${hue} 80% 60%)`;
      metx.fillRect(i * (meter.width / bars), meter.height - h, meter.width / bars - 1, h);
    }
  }

  let meterRaf = 0;
  function meterLoop() {
    if (!spectrumOn) return;
    drawMeter();
    meterRaf = requestAnimationFrame(meterLoop);
  }

  function setSpectrum(on) {
    spectrumOn = on;
    meter.hidden = !on;
    cancelAnimationFrame(meterRaf);
    if (on) meterLoop();
  }

  function drawPlayheadOnly() {
    draw();
    drawMini();
  }

  resize();
  drawMini();

  return {
    canvas,
    state,
    onFrame: (fn) => listeners.add(fn),
    draw: drawPlayheadOnly,
    drawMini,
    setView,
    zoomAt,
    fit,
    centerOn,
    keepVisible,
    setSpectrum,
    get spectrumOn() {
      return spectrumOn;
    },
    get selection() {
      return selection;
    },
    set selection(v) {
      selection = v;
      emit();
      draw();
    },
    getView: () => ({ viewStart, viewSpan }),
    setRegionFromSegment(seg) {
      selection = { start: seg.start, end: seg.end };
      emit();
      draw();
    },
    destroy() {
      ro.disconnect();
      cancelAnimationFrame(meterRaf);
      canvas.remove();
      mini.remove();
      meter.remove();
      overlay.remove();
      tip.remove();
    },
  };
}
