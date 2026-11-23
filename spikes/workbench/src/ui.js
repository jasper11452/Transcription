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

/** 只在这里维护一份：弹窗里的表和 README 都从它出 */
const SHORTCUTS = [
  ['播放', [
    ['Space', '播放 / 暂停'],
    ['← / →', '前 / 后 1 秒（Shift 为 5 秒，Alt 为 0.05 秒）'],
    [', / .', '前 / 后一句'],
    ['N', '播放下一段'],
    ['L', '循环当前段'],
    ['[ / ]', '设循环起点 / 终点'],
    ['0', '缩放到整体'],
    ['+ / -', '在播放头处放大 / 缩小'],
    ['B', '用当前选区建分段'],
  ]],
  ['编辑', [
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
    ['Alt + 拖拽', '平移视图'],
  ]],
  ['撤销', [
    ['⌘/Ctrl + Z', '撤销'],
    ['⇧ + ⌘/Ctrl + Z', '重做'],
  ]],
  ['视图与文件', [
    ['?', '打开这张表'],
    ['⌘/Ctrl + K', '命令面板'],
    ['⌘/Ctrl + F', '搜索文本'],
    ['⌘/Ctrl + S', '保存到本地'],
    ['⌘/Ctrl + E', '导出菜单'],
    ['⌘/Ctrl + O', '打开文件'],
    ['滚轮', '左右平移'],
    ['⌘/Ctrl + 滚轮', '缩放'],
  ]],
];

export function buildShortcutTable() {
  const body = document.createElement('div');
  body.innerHTML = SHORTCUTS.map(
    ([name, items]) => `<section class="shortcut-group"><h3>${escapeHtml(name)}</h3><dl>${items
      .map(([key, desc]) => `<div class="shortcut-row"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(desc)}</dd></div>`)
      .join('')}</dl></section>`,
  ).join('');
  return body;
}
