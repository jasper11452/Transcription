// 通用 UI：toast、模态、快捷键表、以及"把 HTML 写在 JS 里也还算好读"的少量模板。
// 没有框架，所以这一层要克制：只提供被复用三次以上的东西。

import { escapeHtml } from './util.js';

/* ------------------------------------------------------------- Toast */

export function createToaster(root) {
  const host = document.createElement('div');
  host.className = 'toaster';
  host.setAttribute('role', 'status');
  host.setAttribute('aria-live', 'polite');
  root.appendChild(host);

  const ICONS = { info: 'ℹ', ok: '✓', warn: '!', error: '✕', undo: '↺' };

  function show(message, { kind = 'info', detail = '', timeout = kind === 'error' ? 8000 : 3600, action = null } = {}) {
    const el = document.createElement('div');
    el.className = `toast toast-${kind}`;
    el.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${ICONS[kind] || ICONS.info}</span>
      <div class="toast-body"><div class="toast-msg"></div>${detail ? '<div class="toast-detail"></div>' : ''}</div>
      ${action ? '<button class="toast-action"></button>' : ''}
      <button class="toast-close" aria-label="关闭">×</button>
    `;
    el.querySelector('.toast-msg').textContent = message;
    if (detail) el.querySelector('.toast-detail').textContent = detail;
    if (action) {
      const btn = el.querySelector('.toast-action');
      btn.textContent = action.label;
      btn.addEventListener('click', () => {
        action.run();
        dismiss();
      });
    }
    let timer = 0;
    const dismiss = () => {
      clearTimeout(timer);
      el.classList.add('is-leaving');
      setTimeout(() => el.remove(), 180);
    };
    el.querySelector('.toast-close').addEventListener('click', dismiss);
    host.appendChild(el);
    if (timeout) timer = setTimeout(dismiss, timeout);
    // 悬停暂停自动消失：正在读的时候别把它拿走
    el.addEventListener('mouseenter', () => clearTimeout(timer));
    el.addEventListener('mouseleave', () => {
      if (timeout) timer = setTimeout(dismiss, 1200);
    });
    return { dismiss };
  }

  return {
    show,
    ok: (m, o) => show(m, { ...o, kind: 'ok' }),
    warn: (m, o) => show(m, { ...o, kind: 'warn' }),
    error: (m, o) => show(m, { ...o, kind: 'error' }),
    info: (m, o) => show(m, { ...o, kind: 'info' }),
    host,
  };
}

/* ------------------------------------------------------------ 模态 */

export function createModal(root) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.hidden = true;
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header class="modal-head">
        <h2 id="modal-title"></h2>
        <button class="modal-close" aria-label="关闭">×</button>
      </header>
      <div class="modal-body"></div>
      <footer class="modal-foot"></footer>
    </div>
  `;
  root.appendChild(backdrop);
  const titleEl = backdrop.querySelector('#modal-title');
  const bodyEl = backdrop.querySelector('.modal-body');
  const footEl = backdrop.querySelector('.modal-foot');
  let lastFocus = null;
  let onKey = null;

  function close() {
    backdrop.hidden = true;
    bodyEl.replaceChildren();
    footEl.replaceChildren();
    document.removeEventListener('keydown', onKey, true);
    lastFocus?.focus?.();
  }

  function open({ title, body, actions = [], width = '' }) {
    lastFocus = document.activeElement;
    titleEl.textContent = title;
    bodyEl.replaceChildren();
    if (typeof body === 'string') bodyEl.innerHTML = body;
    else if (body) bodyEl.appendChild(body);
    footEl.replaceChildren();
    for (const a of actions) {
      const btn = document.createElement('button');
      btn.className = `btn ${a.variant || ''}`.trim();
      btn.textContent = a.label;
      btn.addEventListener('click', () => {
        const keep = a.run?.();
        if (keep !== false) close();
      });
      if (a.autofocus) setTimeout(() => btn.focus(), 0);
      footEl.appendChild(btn);
    }
    if (width) backdrop.querySelector('.modal').style.maxWidth = width;
    backdrop.hidden = false;
    onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
      if (e.key === 'Tab') {
        // 焦点困在弹窗内
        const focusables = backdrop.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey, true);
    const firstFocus = backdrop.querySelector('[autofocus], input, textarea, button.btn');
    setTimeout(() => firstFocus?.focus(), 0);
  }

  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });
  backdrop.querySelector('.modal-close').addEventListener('click', close);

  return { open, close, get isOpen() { return !backdrop.hidden; } };
}

/* ------------------------------------------------------- 快捷键总览 */

export function shortcutGroups() {
  return [
    {
      name: '播放',
      items: [
        ['Space', '播放 / 暂停'],
        ['← / →', '前 / 后 1 秒（按住 Shift 为 5 秒，Alt 为 0.05 秒）'],
        [', / .', '前 / 后一句'],
        ['N', '播放下一段'],
        ['L', '循环当前段'],
        ['[ / ]', '设循环起点 / 终点'],
        ['0', '缩放到整体'],
        ['+ / -', '在播放头处放大 / 缩小'],
        ['B', '用当前选区建分段'],
      ],
    },
    {
      name: '编辑',
      items: [
        ['E / F2 / 双击', '编辑这一段文本'],
        ['⌘/Ctrl + Enter', '提交编辑'],
        ['Esc', '取消编辑 / 清除选择'],
        ['S', '在播放头处拆分（文本按时间比例切）'],
        ['M', '与下一段合并'],
        ['I', '在下方插入空段'],
        ['Del', '删除选中段（无选中则删当前段）'],
        ['F', '标为待复核'],
        ['X', '勾选当前段'],
        ['Shift + 上下', '扩展选中范围'],
        ['拖拽波形', '框选时间范围'],
        ['Shift + 拖拽', '追加框选'],
        ['Alt + 拖拽', '平移视图'],
      ],
    },
    {
      name: '撤销',
      items: [
        ['⌘/Ctrl + Z', '撤销'],
        ['⇧ + ⌘/Ctrl + Z', '重做'],
      ],
    },
    {
      name: '视图与文件',
      items: [
        ['?', '打开这张表'],
        ['⌘/Ctrl + K', '命令面板'],
        ['⌘/Ctrl + F', '搜索文本'],
        ['⌘/Ctrl + S', '保存到本地'],
        ['⌘/Ctrl + E', '导出菜单'],
        ['⌘/Ctrl + O', '打开文件'],
        ['滚轮', '左右平移'],
        ['⌘/Ctrl + 滚轮', '缩放'],
      ],
    },
  ];
}

export function buildShortcutTable() {
  const frag = document.createDocumentFragment();
  for (const group of shortcutGroups()) {
    const sec = document.createElement('section');
    sec.className = 'shortcut-group';
    sec.innerHTML = `<h3>${escapeHtml(group.name)}</h3><dl></dl>`;
    const dl = sec.querySelector('dl');
    for (const [key, desc] of group.items) {
      const row = document.createElement('div');
      row.className = 'shortcut-row';
      row.innerHTML = `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(desc)}</dd>`;
      dl.appendChild(row);
    }
    frag.appendChild(sec);
  }
  return frag;
}

/* ------------------------------------------------------------- 小工具 */

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of [].concat(children)) if (c) node.appendChild(c);
  return node;
}

export function sparkline(values, { width = 120, height = 28, color = 'currentColor' } = {}) {
  if (!values.length) return '';
  const max = Math.max(...values, 1);
  const step = width / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - (v / max) * (height - 4) - 2).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>
  </svg>`;
}
