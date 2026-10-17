// 命令面板：所有能点的东西都有一条命令，键盘能走完全程。
//
// 这不是"顺手加的搜索框"。作用是把 40 多个动作压成一个统一的入口，
// 因此新功能只需要在 commands 里加一条，不需要再想它该放在哪个菜单里。
// 同时它也是这个页面的自我说明书：敲 ? 之前先 ⌘K 搜一遍就大概知道能干什么。

import { escapeHtml, escapeRegExp } from './util.js';

/** 模糊打分：连续匹配加分，词首加分，跨词匹配扣分 */
export function fuzzyScore(text, query) {
  if (!query) return 1;
  const t = text.toLowerCase();
  const q = query.toLowerCase();
  let ti = 0;
  let score = 0;
  let streak = 0;
  for (const ch of q) {
    const idx = t.indexOf(ch, ti);
    if (idx < 0) return 0;
    streak = idx === ti ? streak + 1 : 0;
    score += 10 + streak * 4 - Math.min(6, idx - ti);
    if (idx === 0 || /[\s·（(]/.test(t[idx - 1])) score += 8;
    ti = idx + 1;
  }
  return Math.max(0, score - (t.length - q.length) * 0.15);
}

export function createPalette(root, { getCommands, onRun, toaster } = {}) {
  const backdrop = document.createElement('div');
  backdrop.className = 'palette-backdrop';
  backdrop.hidden = true;
  backdrop.innerHTML = `
    <div class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
      <div class="palette-input-row">
        <span class="palette-caret" aria-hidden="true">›</span>
        <input class="palette-input" type="text" placeholder='输入命令，或搜索分段文本（前缀 s:）' autocomplete="off" spellcheck="false" />
        <kbd class="palette-hint">Esc</kbd>
      </div>
      <ul class="palette-list" role="listbox" aria-label="命令候选"></ul>
      <footer class="palette-foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
        <span><kbd>↵</kbd> 执行</span>
        <span><kbd>Tab</kbd> 搜分段</span>
        <span class="palette-count"></span>
      </footer>
    </div>
  `;
  root.appendChild(backdrop);
  const input = backdrop.querySelector('.palette-input');
  const list = backdrop.querySelector('.palette-list');
  const countEl = backdrop.querySelector('.palette-count');
  let index = 0;
  let items = [];
  let lastFocus = null;
  let mode = 'command'; // command | search

  function commands() {
    return (getCommands?.() || []).filter((c) => !c.when || c.when());
  }

  function compute() {
    const raw = input.value;
    mode = raw.startsWith('s:') ? 'search' : 'command';
    if (mode === 'search') {
      // 前缀 s: 是进入"搜分段文本"的显式开关，命令模式永远优先在前
      const q = raw.slice(2).trim();
      items = q ? [{ id: 'search-in-transcript', title: `在转录里搜索「${q}」`, group: '搜索', run: () => onRun?.({ id: 'search-in-transcript', args: { query: q } }) }] : [];
    } else {
      const q = raw.trim();
      items = commands()
        .map((c) => ({ c, s: fuzzyScore(`${c.title} ${c.group || ''} ${c.keywords || ''}`, q) + (c.pinned && !q ? 30 : 0) }))
        .filter((x) => (q ? x.s > 0 : true))
        .sort((a, b) => b.s - a.s)
        .slice(0, 60)
        .map((x) => x.c);
    }
    index = Math.min(index, Math.max(0, items.length - 1));
    render();
  }

  function render() {
    list.replaceChildren();
    countEl.textContent = `${items.length} 条`;
    if (!items.length) {
      const li = document.createElement('li');
      li.className = 'palette-empty';
      li.textContent = '没有匹配的命令。试试「导出」「说话人」「循环」这类词。';
      list.appendChild(li);
      return;
    }
    items.forEach((cmd, i) => {
      const li = document.createElement('li');
      li.className = `palette-item${i === index ? ' is-active' : ''}${cmd.disabled ? ' is-disabled' : ''}`;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', i === index ? 'true' : 'false');
      const q = mode === 'search' ? '' : input.value.trim();
      const title = q ? escapeHtml(cmd.title).replace(new RegExp(`(${escapeRegExp(q)})`, 'gi'), '<mark>$1</mark>') : escapeHtml(cmd.title);
      li.innerHTML = `
        <span class="palette-title">${title}</span>
        ${cmd.group ? `<span class="palette-group">${escapeHtml(cmd.group)}</span>` : ''}
        ${cmd.shortcut ? `<kbd class="palette-key">${escapeHtml(cmd.shortcut)}</kbd>` : ''}
      `;
      li.addEventListener('mouseenter', () => {
        index = i;
        render();
      });
      li.addEventListener('click', () => run(i));
      list.appendChild(li);
    });
    list.querySelector('.is-active')?.scrollIntoView({ block: 'nearest' });
  }

  function run(i = index) {
    const cmd = items[i];
    if (!cmd || cmd.disabled) return;
    close();
    try {
      cmd.run();
    } catch (err) {
      toaster?.error(`命令执行失败：${cmd.title}`, { detail: String(err?.message || err) });
    }
  }

  function open(initial = '') {
    lastFocus = document.activeElement;
    backdrop.hidden = false;
    input.value = initial;
    index = 0;
    compute();
    setTimeout(() => {
      input.focus();
      input.select();
    }, 0);
  }

  function close() {
    backdrop.hidden = true;
    lastFocus?.focus?.();
  }

  input.addEventListener('input', () => {
    index = 0;
    compute();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      index = Math.min(index + 1, items.length - 1);
      render();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      index = Math.max(index - 1, 0);
      render();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      run();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      if (!input.value.startsWith('s:')) {
        input.value = `s:${input.value}`;
        index = 0;
        compute();
      }
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  });
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  return {
    open,
    close,
    toggle: () => (backdrop.hidden ? open() : close()),
    get isOpen() {
      return !backdrop.hidden;
    },
    get items() {
      return items;
    },
  };
}
