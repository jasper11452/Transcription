// 转录文本层：分段列表 + 跟读高亮 + 搜索 + 内联编辑 + 键盘导航。
//
// 渲染策略（这是这一层唯一的难点）：
//   1. 结构变化（增删改顺序/说话人/时间）走 reconcile：按 id 复用 DOM 节点，
//      只有真正存在过的 id 集合变了才重建，避免输入时整列表重排。
//   2. 播放位置变化只走 paintActive：改两个 class 和一根高亮条，不碰 DOM 结构。
//   3. 正在编辑的段落冻结时间显示和跟读高亮，否则用户打字时会看到数字乱跳。

import { escapeHtml, escapeRegExp, timecode, countWords, clamp } from './util.js';
import { LOW_CONFIDENCE } from './stats.js';

export function createTranscriptList(root, { store, onSeek, onEdit, onAction, onSelectionChange } = {}) {
  // 复用 HTML 里已有的容器（这样跳过锚点、aria 标签都在静态 HTML 里可读），
  // 没有才新建。
  const list = root.querySelector('.seg-list') || document.createElement('div');
  if (!list.isConnected) {
    list.className = 'seg-list';
    list.setAttribute('role', 'list');
    root.appendChild(list);
  }
  list.tabIndex = 0;
  list.setAttribute('aria-label', '转录分段列表');

  const nodes = new Map(); // id -> {el, textEl, timeEl, ...}
  let order = [];
  let activeId = null;
  let editingId = null;
  let cursorId = null;
  let selected = new Set();
  let query = '';
  let filters = { lowConf: false, flagged: false, edited: false, speaker: null };
  let playhead = 0;
  let detached = false;

  /* ------------------------------------------------------------ 过滤 */

  function visibleSegments() {
    const segs = store.doc.segments;
    const q = query.trim();
    return segs.filter((seg) => {
      if (filters.lowConf && !(typeof seg.confidence === 'number' && seg.confidence < LOW_CONFIDENCE)) return false;
      if (filters.flagged && !seg.flag) return false;
      if (filters.edited && !seg.edited) return false;
      if (filters.speaker && seg.speaker !== filters.speaker) return false;
      if (q && !seg.text.toLowerCase().includes(q.toLowerCase())) return false;
      return true;
    });
  }

  function matches(text) {
    const q = query.trim();
    if (!q) return escapeHtml(text);
    const re = new RegExp(`(${escapeRegExp(q)})`, 'gi');
    return escapeHtml(text).replace(re, '<mark class="hl">$1</mark>');
  }

  /* ------------------------------------------------------------ 构建 */

  function buildNode(seg) {
    const el = document.createElement('article');
    el.className = 'seg';
    el.dataset.id = seg.id;
    el.setAttribute('role', 'listitem');
    el.tabIndex = -1;
    el.innerHTML = `
      <div class="seg-gutter">
        <button class="seg-time" data-act="seek" title="跳到这一段（Enter）">--:--</button>
        <span class="seg-index" aria-hidden="true"></span>
      </div>
      <div class="seg-body">
        <div class="seg-meta">
          <button class="spk-chip" data-act="speaker" title="点击改说话人"></button>
          <span class="conf-chip" data-act="conf"></span>
          <span class="seg-flags">
            <button class="mini-flag" data-act="flag" title="标为待复核（F）" aria-label="标为待复核">⚑</button>
          </span>
        </div>
        <div class="seg-text" role="textbox" aria-multiline="true" tabindex="0"></div>
        <div class="seg-readbar" aria-hidden="true"><i></i></div>
      </div>
      <div class="seg-tools">
        <button data-act="split" title="在播放头处拆分（S）" aria-label="拆分">⧇</button>
        <button data-act="merge" title="与下一段合并（M）" aria-label="合并">⇉</button>
        <button data-act="insert" title="在下方插入一段（I）" aria-label="插入">＋</button>
        <button data-act="delete" title="删除这一段（Del）" aria-label="删除">✕</button>
      </div>
    `;
    const refs = {
      el,
      timeEl: el.querySelector('.seg-time'),
      indexEl: el.querySelector('.seg-index'),
      chipEl: el.querySelector('.spk-chip'),
      confEl: el.querySelector('.conf-chip'),
      flagEl: el.querySelector('.mini-flag'),
      textEl: el.querySelector('.seg-text'),
      readbar: el.querySelector('.seg-readbar > i'),
      seg,
      // 它表示"DOM 里现在写着什么"，而此刻还是空的。
      // 填成 seg.text 会让 paintText 以为已经画过而直接返回，正文就永远是空白。
      lastText: null,
      // 高亮依赖搜索词，所以缓存必须把查询一起算进去：
      // 只盯着文本会导致"改了搜索词但文本没变"时永远不重画，高亮永远不出现。
      lastQuery: '\u0000',
    };
    nodes.set(seg.id, refs);
    return refs;
  }

  function paintMeta(refs) {
    const { seg, el } = refs;
    const sp = store.doc.speakers[seg.speaker];
    refs.timeEl.textContent = timecode(seg.start, { ms: false });
    refs.timeEl.setAttribute('aria-label', `跳到 ${timecode(seg.start)}`);
    refs.chipEl.textContent = sp?.name || seg.speaker;
    refs.chipEl.style.setProperty('--spk', sp?.color || '#888');
    refs.chipEl.title = `说话人：${sp?.name || seg.speaker}（点击更改）`;
    const conf = seg.confidence;
    refs.confEl.textContent = typeof conf === 'number' ? `${Math.round(conf * 100)}%` : '—';
    refs.confEl.className = `conf-chip${typeof conf === 'number' && conf < LOW_CONFIDENCE ? ' is-low' : ''}`;
    refs.confEl.title = typeof conf === 'number' ? `引擎置信度 ${(conf * 100).toFixed(1)}%` : '这个分段没有置信度信息';
    refs.flagEl.classList.toggle('is-on', !!seg.flag);
    el.classList.toggle('is-flagged', !!seg.flag);
    el.classList.toggle('is-edited', !!seg.edited);
    el.classList.toggle('is-low', typeof conf === 'number' && conf < LOW_CONFIDENCE);
    el.dataset.speaker = seg.speaker;
  }

  function paintText(refs) {
    if (editingId === refs.seg.id) return; // 正在编辑就别抢
    if (refs.lastText === refs.seg.text && refs.lastQuery === query) return;
    refs.lastText = refs.seg.text;
    refs.lastQuery = query;
    refs.textEl.innerHTML = matches(refs.seg.text);
  }

  /* ------------------------------------------------------- reconcile */

  function reconcile() {
    if (detached) return;
    const vis = visibleSegments();
    const visIds = vis.map((s) => s.id);

    const sameOrder = visIds.length === order.length && visIds.every((id, i) => order[i] === id);
    if (sameOrder) {
      for (const seg of vis) {
        const refs = nodes.get(seg.id);
        if (!refs) continue;
        refs.seg = seg;
        paintMeta(refs);
        paintText(refs);
      }
      updateIndices();
      paintActive(playhead, true);
      return;
    }

    // 重建可见集合：同一个 id 的节点复用，其余移除；顺序不同只做 DOM 重排
    const seen = new Set(visIds);
    for (const [id, refs] of [...nodes]) {
      if (!seen.has(id)) {
        refs.el.remove();
        nodes.delete(id);
      }
    }
    const frag = document.createDocumentFragment();
    vis.forEach((seg) => {
      const refs = nodes.get(seg.id) || buildNode(seg);
      refs.seg = seg;
      paintMeta(refs);
      paintText(refs);
      frag.appendChild(refs.el);
    });
    list.replaceChildren(frag);
    order = visIds;
    updateIndices();
    paintActive(playhead, true);
  }

  function updateIndices() {
    order.forEach((id, i) => {
      const refs = nodes.get(id);
      if (refs) refs.indexEl.textContent = String(i + 1);
    });
    list.dataset.count = String(order.length);
  }

  /* ------------------------------------------------------- 播放高亮 */

  /** 只碰 class 和一个高亮条宽度，每帧调用也安全 */
  function paintActive(t, force = false) {
    playhead = t;
    const segs = store.doc.segments;
    let found = null;
    for (let i = 0; i < segs.length; i += 1) {
      if (t >= segs[i].start && t <= segs[i].end) {
        found = segs[i];
        break;
      }
      if (segs[i].start > t) break;
    }
    const nextId = found?.id ?? null;
    if (force || nextId !== activeId) {
      if (activeId) nodes.get(activeId)?.el.classList.remove('is-active');
      activeId = nextId;
      const refs = activeId ? nodes.get(activeId) : null;
      refs?.el.classList.add('is-active');
      if (refs && document.body.classList.contains('mode-playback') && store.settings.autoScroll) {
        const box = refs.el.closest('.seg-list');
        const r = refs.el.getBoundingClientRect();
        const b = box.getBoundingClientRect();
        // 只在本段快滑出视野时才滚，否则每段都滚会让眼睛跟不上
        if (r.top < b.top + b.height * 0.15 || r.bottom > b.bottom - b.height * 0.15) {
          refs.el.scrollIntoView({ block: 'center', behavior: store.settings.reduceMotion ? 'auto' : 'smooth' });
        }
      }
    }
    const refs = activeId ? nodes.get(activeId) : null;
    if (refs && found) {
      const pct = clamp((t - found.start) / Math.max(0.05, found.end - found.start), 0, 1);
      refs.readbar.style.width = `${pct * 100}%`;
    }
    // 非活动段落的进度条归零（只在确实非零时才碰 DOM）
    for (const id of order) {
      if (id === activeId) continue;
      const r = nodes.get(id);
      if (r && r.readbar.style.width && r.readbar.style.width !== '0%') r.readbar.style.width = '0%';
    }
  }

  function activeSegmentId() {
    return activeId;
  }

  function scrollToSegment(id, { smooth = true } = {}) {
    const refs = nodes.get(id);
    if (!refs) return false;
    refs.el.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' });
    return true;
  }

  /* --------------------------------------------------------- 选择集 */

  function setSelected(next) {
    const prev = selected;
    selected = new Set(next);
    for (const id of new Set([...prev, ...selected])) {
      nodes.get(id)?.el.classList.toggle('is-selected', selected.has(id));
    }
    onSelectionChange?.([...selected]);
  }

  function toggleSelected(id, { additive = true } = {}) {
    if (!additive) setSelected([id]);
    else if (selected.has(id)) {
      selected.delete(id);
      setSelected(selected);
    } else setSelected([...selected, id]);
  }

  function setCursor(id, { focus = false } = {}) {
    cursorId = id;
    for (const [nid, refs] of nodes) refs.el.classList.toggle('is-cursor', nid === id);
    if (focus) {
      const refs = nodes.get(id);
      refs?.el.focus({ preventScroll: false });
    }
  }

  function moveCursor(delta, { extend = false } = {}) {
    const vis = visibleSegments().map((s) => s.id);
    if (!vis.length) return;
    let i = cursorId ? vis.indexOf(cursorId) : -1;
    i = clamp(i < 0 ? 0 : i + delta, 0, vis.length - 1);
    const id = vis[i];
    setCursor(id);
    if (extend) toggleSelected(id);
    scrollToSegment(id, { smooth: false });
  }

  /* --------------------------------------------------------- 编辑 */

  function beginEdit(id) {
    const refs = nodes.get(id);
    if (!refs) return;
    editingId = id;
    refs.el.classList.add('is-editing');
    refs.textEl.contentEditable = 'true';
    refs.textEl.spellcheck = false;
    refs.textEl.focus();
    // 光标放到末尾（从键盘触发时最自然）
    const range = document.createRange();
    range.selectNodeContents(refs.textEl);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function endEdit({ commit = true } = {}) {
    if (!editingId) return;
    const id = editingId;
    const refs = nodes.get(id);
    editingId = null;
    if (!refs) return;
    refs.el.classList.remove('is-editing');
    refs.textEl.contentEditable = 'false';
    const text = refs.textEl.innerText.replace(/\n+$/g, '').trim();
    if (commit && text !== refs.seg.text) {
      store.updateText(id, text);
      onEdit?.({ id, text, before: refs.seg.text });
    }
    refs.lastText = null;
    paintText(refs);
  }

  /* --------------------------------------------------------- 事件 */

  list.addEventListener('click', (e) => {
    const segEl = e.target.closest('.seg');
    if (!segEl) return;
    const id = segEl.dataset.id;
    const act = e.target.closest('[data-act]')?.dataset.act;
    const refs = nodes.get(id);
    if (!refs) return;

    if (act === 'seek') {
      onSeek?.(refs.seg.start, { user: true, segment: refs.seg });
      return;
    }
    if (act === 'flag') {
      onAction?.('toggle-flag', { id });
      return;
    }
    if (act === 'split') {
      onAction?.('split', { id, at: playhead });
      return;
    }
    if (act === 'merge') {
      onAction?.('merge', { id });
      return;
    }
    if (act === 'insert') {
      onAction?.('insert', { id });
      return;
    }
    if (act === 'delete') {
      onAction?.('delete', { ids: selected.has(id) ? [...selected] : [id] });
      return;
    }
    if (act === 'speaker') {
      onAction?.('cycle-speaker', { id });
      return;
    }
    if (act === 'conf') {
      onAction?.('explain-confidence', { id });
      return;
    }

    // 点正文以外的区域：选中 + 跳播
    if (!e.target.closest('.seg-text') || editingId !== id) {
      setCursor(id);
      onSeek?.(refs.seg.start, { user: true, segment: refs.seg });
    }
  });

  list.addEventListener('dblclick', (e) => {
    const segEl = e.target.closest('.seg');
    if (!segEl) return;
    beginEdit(segEl.dataset.id);
  });

  list.addEventListener('blur', (e) => {
    if (e.target.classList?.contains('seg-text') && editingId) endEdit({ commit: true });
  }, true);

  list.addEventListener('keydown', (e) => {
    const segEl = e.target.closest('.seg');
    const id = segEl?.dataset.id;
    const inEdit = editingId && editingId === id;

    if (e.key === 'Escape') {
      if (inEdit) {
        e.preventDefault();
        endEdit({ commit: false });
        const refs = nodes.get(id);
        if (refs) {
          refs.textEl.textContent = refs.seg.text;
          refs.lastText = refs.seg.text;
          refs.lastQuery = query;
        }
      } else {
        setSelected([]);
      }
      return;
    }
    if (inEdit) {
      // 编辑态只放行换行与提交，方向键留给文本本身
      if (e.key === 'Escape') return;
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        endEdit({ commit: true });
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        endEdit({ commit: true });
        moveCursor(e.shiftKey ? -1 : 1);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        moveCursor(1, { extend: e.shiftKey });
        break;
      case 'ArrowUp':
        e.preventDefault();
        moveCursor(-1, { extend: e.shiftKey });
        break;
      case 'j':
        if (e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        moveCursor(1, { extend: e.shiftKey });
        break;
      case 'k':
        if (e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        moveCursor(-1, { extend: e.shiftKey });
        break;
      case 'Enter':
        e.preventDefault();
        if (id) onSeek?.(nodes.get(id).seg.start, { user: true, segment: nodes.get(id).seg });
        break;
      case 'e':
      case 'F2':
        if (!id) return;
        e.preventDefault();
        beginEdit(id);
        break;
      case ' ':
        if (e.target.classList?.contains('seg-text')) return;
        e.preventDefault();
        onAction?.('toggle-play');
        break;
      case 'x':
        if (!id) return;
        e.preventDefault();
        toggleSelected(id);
        break;
      case 'f':
        if (!id) return;
        e.preventDefault();
        onAction?.('toggle-flag', { id });
        break;
      case 's':
        if (!id) return;
        e.preventDefault();
        onAction?.('split', { id, at: playhead });
        break;
      case 'm':
        if (!id) return;
        e.preventDefault();
        onAction?.('merge', { id });
        break;
      case 'i':
        if (!id) return;
        e.preventDefault();
        onAction?.('insert', { id });
        break;
      case 'Delete':
      case 'Backspace':
        if (!id) return;
        e.preventDefault();
        onAction?.('delete', { ids: selected.size ? [...selected] : [id] });
        break;
      case 'n':
        e.preventDefault();
        onAction?.('play-next-segment');
        break;
      default:
        break;
    }
  });

  // 输入法友好：compositionend 之后再算字数，避免中文输入过程被打断
  list.addEventListener('input', (e) => {
    const segEl = e.target.closest?.('.seg');
    if (!segEl || editingId !== segEl.dataset.id) return;
    const refs = nodes.get(segEl.dataset.id);
    if (!refs) return;
    // 编辑中就地更新字数预览，但不写 store（那会触发重渲染打断输入）
    const n = countWords(refs.textEl.innerText);
    segEl.dataset.words = String(n);
  });

  /* --------------------------------------------------------- 对外 */

  return {
    list,
    reconcile,
    paintActive,
    setQuery(q) {
      query = q || '';
      reconcile();
    },
    get query() {
      return query;
    },
    setFilters(next) {
      filters = { ...filters, ...next };
      reconcile();
    },
    get filters() {
      return filters;
    },
    setSelected,
    clearSelection: () => setSelected([]),
    get selected() {
      return [...selected];
    },
    toggleSelected,
    setCursor,
    get cursor() {
      return cursorId;
    },
    moveCursor,
    beginEdit,
    endEdit,
    get editing() {
      return editingId;
    },
    scrollToSegment,
    activeSegmentId,
    segmentById: (id) => store.doc.segments.find((s) => s.id === id) || null,
    detach() {
      detached = true;
    },
    attach() {
      detached = false;
      reconcile();
    },
    visibleCount: () => order.length,
    focus: () => list.focus(),
    root: list,
  };
}
