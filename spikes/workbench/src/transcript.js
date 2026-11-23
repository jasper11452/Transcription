// 转录文本层：分段列表 + 跟读高亮 + 搜索筛选 + 内联编辑 + 键盘导航。
//
// 渲染分两条路径，这是这一层唯一的难点：
//   1. 结构变化（增删/顺序/说话人/时间）走 reconcile：按 id 复用 DOM 节点，
//      只有可见集合真的变了才重排，避免打字时把整个列表推倒重来。
//   2. 播放位置变化只走 paintActive：改一个 class，不碰 DOM 结构。

import { escapeHtml, escapeRegExp, timecode, countWords, clamp } from './util.js';
import { LOW_CONFIDENCE } from './stats.js';

export function createTranscriptList(root, { store, onSeek, onEdit, onAction, onSelectionChange } = {}) {
  // 复用 HTML 里的容器：这样跳过锚点、aria 标签都在静态 HTML 里就能读到
  const list = root.querySelector('.seg-list');
  list.tabIndex = 0;

  const nodes = new Map(); // id -> refs
  let order = [];
  let activeId = null;
  let editingId = null;
  let cursorId = null;
  let selected = new Set();
  let query = '';
  let filter = null; // null | 'low' | 'flag' | 'edited' | 说话人 id
  let playhead = 0;

  /* ------------------------------------------------------- 过滤与高亮 */

  function visible() {
    const q = query.trim().toLowerCase();
    return store.doc.segments.filter((seg) => {
      if (filter === 'low' && !(typeof seg.confidence === 'number' && seg.confidence < LOW_CONFIDENCE)) return false;
      if (filter === 'flag' && !seg.flag) return false;
      if (filter === 'edited' && !seg.edited) return false;
      if (filter && filter !== 'low' && filter !== 'flag' && filter !== 'edited' && seg.speaker !== filter) return false;
      return !q || seg.text.toLowerCase().includes(q);
    });
  }

  function marked(text) {
    const q = query.trim();
    if (!q) return escapeHtml(text);
    return escapeHtml(text).replace(new RegExp(`(${escapeRegExp(q)})`, 'gi'), '<mark class="hl">$1</mark>');
  }

  /* ------------------------------------------------------------ 构建 */

  function buildNode(seg) {
    const el = document.createElement('article');
    el.className = 'seg';
    el.dataset.id = seg.id;
    el.setAttribute('role', 'listitem');
    el.tabIndex = -1;
    el.innerHTML = `
      <div class="seg-gutter"><button class="seg-time" data-act="seek"></button></div>
      <div class="seg-body">
        <div class="seg-meta">
          <button class="spk-chip" data-act="speaker" title="点击改说话人"></button>
          <span class="conf-chip" data-act="conf"></span>
          <button class="mini-flag" data-act="flag" title="标为待复核（F）" aria-label="标为待复核">⚑</button>
        </div>
        <div class="seg-text" role="textbox" aria-multiline="true" tabindex="0"></div>
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
      seg,
      timeEl: el.querySelector('.seg-time'),
      chipEl: el.querySelector('.spk-chip'),
      confEl: el.querySelector('.conf-chip'),
      flagEl: el.querySelector('.mini-flag'),
      textEl: el.querySelector('.seg-text'),
      // 记的是"DOM 里现在写着什么"，此刻还是空的；填成 seg.text 会让 paintText 以为画过了
      lastText: null,
      // 高亮取决于搜索词，所以缓存必须把查询一起算进去，否则改词不重画
      lastQuery: '\u0000',
    };
    nodes.set(seg.id, refs);
    return refs;
  }

  function paintMeta(refs) {
    const { seg, el } = refs;
    const sp = store.doc.speakers[seg.speaker];
    const low = typeof seg.confidence === 'number' && seg.confidence < LOW_CONFIDENCE;
    refs.timeEl.textContent = timecode(seg.start, { ms: false });
    refs.timeEl.setAttribute('aria-label', `跳到 ${timecode(seg.start)}`);
    refs.chipEl.textContent = sp?.name || seg.speaker;
    refs.chipEl.style.setProperty('--spk', sp?.color || '#888');
    refs.chipEl.title = `说话人：${sp?.name || seg.speaker}（点击更改）`;
    refs.confEl.textContent = typeof seg.confidence === 'number' ? `${Math.round(seg.confidence * 100)}%` : '—';
    refs.confEl.className = `conf-chip${low ? ' is-low' : ''}`;
    refs.confEl.title = typeof seg.confidence === 'number' ? `引擎置信度 ${(seg.confidence * 100).toFixed(1)}%` : '这个分段没有置信度信息';
    refs.flagEl.classList.toggle('is-on', !!seg.flag);
    el.classList.toggle('is-flagged', !!seg.flag);
    el.classList.toggle('is-edited', !!seg.edited);
    el.classList.toggle('is-low', low);
    el.dataset.speaker = seg.speaker;
  }

  function paintText(refs) {
    if (editingId === refs.seg.id) return; // 正在编辑就别抢
    if (refs.lastText === refs.seg.text && refs.lastQuery === query) return;
    refs.lastText = refs.seg.text;
    refs.lastQuery = query;
    refs.textEl.innerHTML = marked(refs.seg.text);
  }

  function reconcile() {
    const vis = visible();
    const visIds = vis.map((s) => s.id);
    const sameOrder = visIds.length === order.length && visIds.every((id, i) => order[i] === id);

    if (!sameOrder) {
      const seen = new Set(visIds);
      for (const [id, refs] of [...nodes]) {
        if (!seen.has(id)) {
          refs.el.remove();
          nodes.delete(id);
        }
      }
      const frag = document.createDocumentFragment();
      vis.forEach((seg) => frag.appendChild((nodes.get(seg.id) || buildNode(seg)).el));
      list.replaceChildren(frag);
      order = visIds;
      list.dataset.count = String(order.length);
    }
    for (const seg of vis) {
      const refs = nodes.get(seg.id);
      if (!refs) continue;
      refs.seg = seg;
      paintMeta(refs);
      paintText(refs);
    }
    paintActive(playhead, true);
  }

  /* ------------------------------------------------------- 播放高亮 */

  /** 只碰 class，每帧调用也安全 */
  function paintActive(t, force = false) {
    playhead = t;
    const found = store.doc.segments.find((s) => t >= s.start && t <= s.end) || null;
    const nextId = found?.id ?? null;
    if (!force && nextId === activeId) return;
    if (activeId) nodes.get(activeId)?.el.classList.remove('is-active');
    activeId = nextId;
    const refs = activeId ? nodes.get(activeId) : null;
    if (!refs) return;
    refs.el.classList.add('is-active');
    // 只在本段快滑出视野时才滚，否则每段都滚会让眼睛跟不上
    if (document.body.classList.contains('mode-playback') && store.settings.autoScroll) {
      const box = list.getBoundingClientRect();
      const r = refs.el.getBoundingClientRect();
      if (r.top < box.top + box.height * 0.15 || r.bottom > box.bottom - box.height * 0.15) {
        refs.el.scrollIntoView({ block: 'center', behavior: store.settings.reduceMotion ? 'auto' : 'smooth' });
      }
    }
  }

  function scrollToSegment(id, { smooth = true } = {}) {
    const refs = nodes.get(id);
    if (!refs) return;
    refs.el.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' });
  }

  /* --------------------------------------------------------- 选择集 */

  function setSelected(next) {
    const prev = selected;
    selected = new Set(next);
    for (const id of new Set([...prev, ...selected])) nodes.get(id)?.el.classList.toggle('is-selected', selected.has(id));
    onSelectionChange?.([...selected]);
  }

  function setCursor(id, { focus = false } = {}) {
    cursorId = id;
    for (const [nid, refs] of nodes) refs.el.classList.toggle('is-cursor', nid === id);
    if (focus) nodes.get(id)?.el.focus();
  }

  function moveCursor(delta, { extend = false } = {}) {
    const vis = visible().map((s) => s.id);
    if (!vis.length) return;
    const i = clamp(cursorId ? vis.indexOf(cursorId) + delta : 0, 0, vis.length - 1);
    setCursor(vis[i]);
    if (extend) setSelected(selected.has(vis[i]) ? [...selected].filter((x) => x !== vis[i]) : [...selected, vis[i]]);
    scrollToSegment(vis[i], { smooth: false });
  }

  /* ------------------------------------------------------------ 编辑 */

  function beginEdit(id) {
    const refs = nodes.get(id);
    if (!refs) return;
    editingId = id;
    refs.el.classList.add('is-editing');
    refs.textEl.contentEditable = 'true';
    refs.textEl.spellcheck = false;
    refs.textEl.focus();
    // 光标放到末尾：从键盘触发时最自然
    const range = document.createRange();
    range.selectNodeContents(refs.textEl);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function endEdit({ commit = true } = {}) {
    const refs = nodes.get(editingId);
    const id = editingId;
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

  /* ------------------------------------------------------------ 事件 */

  const segIdOf = (target) => target.closest?.('.seg')?.dataset.id;

  list.addEventListener('click', (e) => {
    const id = segIdOf(e.target);
    const refs = nodes.get(id);
    if (!refs) return;
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'seek') return onSeek?.(refs.seg.start, { user: true, segment: refs.seg });
    if (act === 'speaker') return onAction?.('cycle-speaker', { id });
    if (act === 'conf') return onAction?.('explain-confidence', { id });
    if (act === 'split') return onAction?.('split', { id, at: playhead });
    if (act === 'merge') return onAction?.('merge', { id });
    if (act === 'insert') return onAction?.('insert', { id });
    if (act === 'flag') return onAction?.('toggle-flag', { id });
    if (act === 'delete') return onAction?.('delete', { ids: selected.has(id) ? [...selected] : [id] });
    // 点正文以外的区域：选中并跳播
    if (!e.target.closest('.seg-text')) {
      setCursor(id);
      onSeek?.(refs.seg.start, { user: true, segment: refs.seg });
    }
  });

  list.addEventListener('dblclick', (e) => {
    const id = segIdOf(e.target);
    if (id) beginEdit(id);
  });

  // 点走失焦即提交，避免"改完忘了提交"
  list.addEventListener(
    'blur',
    (e) => {
      if (editingId && e.target.classList?.contains('seg-text')) endEdit({ commit: true });
    },
    true,
  );

  list.addEventListener('input', (e) => {
    const segEl = e.target.closest?.('.seg');
    if (editingId && segEl?.dataset.id === editingId) segEl.dataset.words = String(countWords(e.target.innerText));
  });

  list.addEventListener('keydown', (e) => {
    const id = segIdOf(e.target);
    const inEdit = editingId && editingId === id;

    if (inEdit) {
      // 编辑态只放行提交与跳段，其余按键留给文本本身
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        endEdit({ commit: true });
      } else if (e.key === 'Escape') {
        e.preventDefault();
        endEdit({ commit: false });
        const refs = nodes.get(id);
        if (refs) {
          refs.textEl.textContent = refs.seg.text;
          refs.lastText = refs.seg.text;
          refs.lastQuery = query;
        }
      } else if (e.key === 'Tab') {
        e.preventDefault();
        endEdit({ commit: true });
        moveCursor(e.shiftKey ? -1 : 1);
      }
      return;
    }

    const key = e.key;
    const keyOf = (fn) => {
      if (!id) return;
      e.preventDefault();
      fn(nodes.get(id).seg);
    };
    if (key === 'Escape') return setSelected([]);
    if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'j' || key === 'k') {
      if ((key === 'j' || key === 'k') && (e.metaKey || e.ctrlKey)) return;
      e.preventDefault();
      return moveCursor(key === 'ArrowUp' || key === 'k' ? -1 : 1, { extend: e.shiftKey });
    }
    if (key === 'e' || key === 'F2') return keyOf(() => beginEdit(id));
    if (key === 'Enter') return keyOf((seg) => onSeek?.(seg.start, { user: true, segment: seg }));
    if (key === 'x') return keyOf(() => setSelected(selected.has(id) ? [...selected].filter((s) => s !== id) : [...selected, id]));
    if (key === 'f') return keyOf(() => onAction?.('toggle-flag', { id }));
    if (key === 's') return keyOf(() => onAction?.('split', { id, at: playhead }));
    if (key === 'm') return keyOf(() => onAction?.('merge', { id }));
    if (key === 'i') return keyOf(() => onAction?.('insert', { id }));
    if (key === 'Delete' || key === 'Backspace') return keyOf(() => onAction?.('delete', { ids: selected.size ? [...selected] : [id] }));
    if (key === ' ') {
      if (e.target.classList?.contains('seg-text')) return;
      e.preventDefault();
      onAction?.('toggle-play');
    }
  });

  /* ------------------------------------------------------------ 对外 */

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
    setFilter(next) {
      filter = next;
      reconcile();
    },
    setSelected,
    clearSelection: () => setSelected([]),
    get selected() {
      return [...selected];
    },
    setCursor,
    get cursor() {
      return cursorId;
    },
    beginEdit,
    endEdit,
    scrollToSegment,
    activeSegmentId: () => activeId,
    segmentById: (id) => store.doc.segments.find((s) => s.id === id) || null,
    visibleCount: () => order.length,
    focus: () => list.focus(),
  };
}
