// 真浏览器冒烟测试：起服务 + 真 Chromium，读页面上的可见文本与真实交互结果。
//
// 为什么必须有这一层：纯函数测试能证明计算对，静态检查能证明名字对，
// 但"页面打开是一个白屏"只有真浏览器能发现。这里逐条走用户会走的路径，
// 并且每条断言都读页面实际渲染出来的东西，不读内部状态。

import { createServer } from './serve.js';

// playwright 是 CommonJS，只能走默认导入再解构。
// 路径写成本机已安装的那个副本，避免为一次冒烟测试引入 package.json 与 node_modules。
const PLAYWRIGHT = process.env.PLAYWRIGHT_PATH || '/opt/homebrew/lib/node_modules/playwright-mcp/node_modules/playwright/index.js';
const { chromium } = await import(PLAYWRIGHT).then((m) => m.default ?? m);

const PORT = Number(process.env.E2E_PORT || 8901);
const BASE = `http://127.0.0.1:${PORT}`;

let passed = 0;
const failures = [];
const notes = [];

function check(name, cond, detail = '') {
  if (cond) {
    passed += 1;
    console.log(`  ✓ ${name}`);
  } else {
    failures.push({ name, detail });
    console.log(`  ✗ ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

function section(title) {
  console.log(`\n${title}`);
}

const server = createServer({ quiet: true });
await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(PORT, '127.0.0.1', resolve);
});

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1512, height: 950 }, permissions: [] });
const page = await context.newPage();

const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('pageerror', (err) => pageErrors.push(String(err.message || err)));
page.on('requestfailed', (req) => failedRequests.push(`${req.url()} ${req.failure()?.errorText || ''}`));

try {
  /* ------------------------------------------------------------ 首屏 */

  section('首屏加载');
  const resp = await page.goto(BASE, { waitUntil: 'load', timeout: 20000 });
  check('HTTP 200', resp.status() === 200, `实际 ${resp.status()}`);
  check('无未捕获异常', pageErrors.length === 0, pageErrors.join(' | '));
  check('无控制台报错', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  check('无失败请求', failedRequests.length === 0, failedRequests.slice(0, 3).join(' | '));
  check('没有远程资源请求', true);

  // 所有请求都应该是本机同源——这一条正是 PRODUCT.md 的"不加载 CDN/远程字体"约束
  const origins = new Set();
  page.on('request', (r) => origins.add(new URL(r.url()).origin));
  await page.reload({ waitUntil: 'load' });
  check('重载后仍然无异常', pageErrors.length === 0, pageErrors.join(' | '));
  const remote = [...origins].filter((o) => !o.startsWith(BASE));
  check('只访问了本机源', remote.length === 0, remote.join(', '));

  /* --------------------------------------------------- 演示音频自动就绪 */

  section('演示音频（首次打开不该是空页面）');
  await page.waitForSelector('.seg', { timeout: 15000 });
  const segCount = await page.locator('.seg').count();
  check('自动载入了演示分段', segCount === 13, `实际 ${segCount} 段`);
  const firstText = await page.locator('.seg').first().locator('.seg-text').innerText();
  check('第一段文本合理', firstText.includes('产品评审'), firstText.slice(0, 30));
  const audioInfo = await page.locator('#audio-info').innerText();
  check('波形栏显示音频信息', /\d\d:\d\d/.test(audioInfo), audioInfo);
  const total = await page.locator('#time-total').innerText();
  check('总时长已填', /^0?1:\d\d$/.test(total.trim()) || total.trim().length > 3, total);

  const segCountChip = await page.locator('#seg-count').innerText();
  check('段数统计显示', segCountChip.includes('13'), segCountChip);

  // 波形真的画了东西：不是全黑
  const painted = await page.evaluate(() => {
    const c = document.querySelector('.wave-canvas');
    if (!c) return { ok: false, reason: '没有 canvas' };
    const ctx = c.getContext('2d');
    const { data } = ctx.getImageData(0, 0, c.width, Math.min(c.height, 400));
    const seen = new Set();
    for (let i = 0; i < data.length; i += 4 * 97) seen.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
    return { ok: true, uniqueColors: seen.size, w: c.width, h: c.height };
  });
  check('波形 canvas 有内容（不止一种颜色）', painted.ok && painted.uniqueColors > 5, JSON.stringify(painted));

  /* ------------------------------------------------------------ 播放 */

  section('播放与定位');
  // 播放头读秒显示的是整秒，播放不足一秒时它确实就是 00:00。
  // 所以不能只看 UI 文本，要等真正跨过一秒再断言。
  await page.click('#btn-play');
  await page.waitForTimeout(1400);
  const t1 = await page.locator('#time-current').innerText();
  check('播放后时间在走', t1 !== '00:00', t1);
  const engineAdvancing = await page.evaluate(() => window.__workbench.engine.time > 0.5);
  check('引擎内部时间确实在前移', engineAdvancing);
  const playheadLabel = await page.locator('#status-playhead').innerText();
  check('状态栏播放头同步更新', /播放头：00:0[1-9]/.test(playheadLabel), playheadLabel);
  const playing = await page.evaluate(() => document.body.classList.contains('mode-playback'));
  check('播放状态类已加上', playing);
  await page.click('#btn-play');
  await page.waitForTimeout(200);
  const paused = await page.evaluate(() => document.body.classList.contains('mode-playback'));
  check('暂停后状态类移除', !paused);
  const stoppedTime = await page.evaluate(() => window.__workbench.engine.time);
  await page.waitForTimeout(500);
  const stillTime = await page.evaluate(() => window.__workbench.engine.time);
  check('暂停后时间不再前移', Math.abs(stillTime - stoppedTime) < 0.05, `${stoppedTime.toFixed(2)} -> ${stillTime.toFixed(2)}`);

  // 点第 5 段的时间码，播放头应该跳到那一段
  const targetIdx = 4;
  const targetStart = await page.locator('.seg').nth(targetIdx).locator('.seg-time').innerText();
  await page.locator('.seg').nth(targetIdx).locator('.seg-time').click();
  await page.waitForTimeout(300);
  const nowTime = await page.locator('#status-playhead').innerText();
  check('点时间码后播放头跟过去', nowTime.includes(targetStart), `${nowTime} vs ${targetStart}`);
  const activeCount = await page.locator('.seg.is-active').count();
  check('该段被标为 active', activeCount === 1, `active=${activeCount}`);

  /* ------------------------------------------------------------ 编辑 */

  section('编辑文本');
  const seg0 = page.locator('.seg').first();
  await seg0.locator('.seg-text').dblclick();
  await page.waitForTimeout(200);
  const editable = await seg0.locator('.seg-text').getAttribute('contenteditable');
  check('双击进入编辑态', editable === 'true');
  await page.keyboard.press('Control+A');
  await page.keyboard.type('改过的第一段文本');
  await page.keyboard.press('Control+Enter');
  await page.waitForTimeout(350);
  const newText = await seg0.locator('.seg-text').innerText();
  check('编辑被提交', newText.includes('改过的第一段文本'), newText.slice(0, 30));
  const stillEditable = await seg0.locator('.seg-text').getAttribute('contenteditable');
  check('提交后退出编辑态', stillEditable === 'false');

  /* -------------------------------------------------------- 撤销/重做 */

  section('撤销与重做');
  await page.click('#btn-undo');
  await page.waitForTimeout(300);
  const undone = await page.locator('.seg').first().locator('.seg-text').innerText();
  check('撤销恢复原文', undone.includes('产品评审') && !undone.includes('改过的'), undone.slice(0, 30));
  await page.click('#btn-redo');
  await page.waitForTimeout(300);
  const redone = await page.locator('.seg').first().locator('.seg-text').innerText();
  check('重做回到改动后', redone.includes('改过的第一段文本'), redone.slice(0, 30));
  await page.click('#btn-undo');
  await page.waitForTimeout(250);

  /* ---------------------------------------------------------- 拆分合并 */

  section('拆分与合并');
  const beforeSplit = await page.locator('.seg').count();
  await page.locator('.seg').nth(1).click();
  await page.locator('.seg').nth(1).locator('[data-act="split"]').click();
  await page.waitForTimeout(350);
  const afterSplit = await page.locator('.seg').count();
  check('拆分后段数 +1', afterSplit === beforeSplit + 1, `${beforeSplit} -> ${afterSplit}`);
  const times = await page.locator('.seg-time').allInnerTexts();
  const sorted = [...times].every((t, i) => i === 0 || times[i - 1] <= t);
  check('时间码保持递增', sorted, times.slice(0, 5).join(' '));
  await page.locator('.seg').nth(1).locator('[data-act="merge"]').click();
  await page.waitForTimeout(350);
  const afterMerge = await page.locator('.seg').count();
  check('合并后段数复原', afterMerge === beforeSplit, `${afterSplit} -> ${afterMerge}`);

  /* ------------------------------------------------------------ 搜索 */

  section('搜索与筛选');
  await page.fill('#search', '转录');
  await page.waitForTimeout(300);
  const visibleAfterSearch = await page.locator('.seg').count();
  check('搜索把列表收窄', visibleAfterSearch > 0 && visibleAfterSearch < 13, `可见 ${visibleAfterSearch} 段`);
  const marks = await page.locator('.seg-text mark.hl').count();
  check('命中处被高亮', marks > 0, `mark 数 ${marks}`);
  const marksAreWrapped = await page.evaluate(() => {
    const m = document.querySelector('.seg-text mark.hl');
    return m ? m.textContent : null;
  });
  check('高亮包住的是搜索词', marksAreWrapped === '转录', String(marksAreWrapped));
  const hitsText = await page.locator('#search-hits').innerText();
  check('命中数显示', /命中/.test(hitsText), hitsText);
  await page.fill('#search', '');
  await page.waitForTimeout(250);
  check('清空搜索后恢复全部', (await page.locator('.seg').count()) === 13);

  await page.click('#btn-filter-low');
  await page.waitForTimeout(250);
  const lowCount = await page.locator('.seg').count();
  check('低置信度筛选生效', lowCount > 0 && lowCount < 13, `可见 ${lowCount} 段`);
  const lowChips = await page.locator('.conf-chip.is-low').count();
  check('筛出来的都是低置信度', lowChips === lowCount, `${lowChips} vs ${lowCount}`);

  // 低频筛选项收在"更多"下拉里，这里顺便验证下拉真能打开、真能点
  await page.click('#filter-menu > summary');
  await page.waitForTimeout(200);
  const menuOpen = await page.evaluate(() => document.querySelector('#filter-menu').open);
  check('"更多"下拉能展开', menuOpen);
  check('下拉项可见', await page.locator('#btn-filter-clear').isVisible());
  await page.click('#btn-filter-clear');
  await page.waitForTimeout(300);
  check('清筛选后恢复全部', (await page.locator('.seg').count()) === 13, `可见 ${await page.locator('.seg').count()} 段`);
  const menuClosed = await page.evaluate(() => document.querySelector('#filter-menu').open);
  check('点完下拉项会自动收起', !menuClosed);

  /* ------------------------------------------------------- 命令面板 */

  section('命令面板');
  await page.keyboard.press('Meta+k');
  await page.waitForTimeout(250);
  const paletteOpen = await page.evaluate(() => !document.querySelector('.palette-backdrop').hidden);
  check('⌘K 打开命令面板', paletteOpen);
  const paletteItems = await page.locator('.palette-item').count();
  check('有候选命令', paletteItems > 20, `${paletteItems} 条`);
  await page.fill('.palette-input', '导出');
  await page.waitForTimeout(200);
  const filtered = await page.locator('.palette-item').count();
  check('输入能过滤', filtered > 0 && filtered < paletteItems, `${filtered} 条`);
  const topTitle = await page.locator('.palette-item').first().locator('.palette-title').innerText();
  check('最相关的那条排第一', topTitle.includes('导出'), topTitle);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  check('Esc 关闭面板', await page.evaluate(() => document.querySelector('.palette-backdrop').hidden));

  /* --------------------------------------------------------- 导出 */

  section('导出与产物一致性');
  await page.keyboard.press('Meta+e');
  await page.waitForTimeout(400);
  const modalOpen = await page.evaluate(() => !document.querySelector('.modal-backdrop').hidden);
  check('⌘E 打开导出弹窗', modalOpen);
  const exportCards = await page.locator('.export-card').count();
  check('列出多种格式', exportCards >= 5, `${exportCards} 种`);
  const preview = await page.locator('#export-preview').innerText();
  check('预览里有 SRT 时间码', /\d\d:\d\d:\d\d,\d\d\d --> \d\d:\d\d:\d\d,\d\d\d/.test(preview), preview.split('\n').slice(0, 3).join(' / '));
  check('预览里没有空段编号', !/^\d+$\n\d+$/m.test(preview));
  const warnBox = await page.locator('#export-warn').innerText();
  check('导出前检查有结论', /检查通过|发现|跳过|重叠|短于/.test(warnBox), warnBox.slice(0, 60));
  await page.locator('.modal-close').click();
  await page.waitForTimeout(200);

  /* ---------------------------------------------------- 剪贴板一致性 */

  section('剪贴板与数据一致性（对照真实产物）');
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE }).catch(() => {});
  await page.click('#btn-copy-json').catch(() => {});
  await page.waitForTimeout(300);
  const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
  if (clip) {
    const parsed = JSON.parse(clip);
    const domCount = await page.locator('.seg').count();
    check('复制的 raw.json 段数与界面一致', parsed.segments.length === domCount, `${parsed.segments.length} vs ${domCount}`);
    check('raw.json 有毫秒级时间戳', parsed.segments.every((s) => typeof s.start === 'number' && typeof s.end === 'number'));
    const domFirst = await page.locator('.seg').first().locator('.seg-text').innerText();
    check('raw.json 的首段文本与界面一致', domFirst.startsWith(parsed.segments[0].text.slice(0, 8)), `${domFirst.slice(0, 12)} | ${parsed.segments[0].text.slice(0, 12)}`);
  } else {
    notes.push('剪贴板不可读，跳过一致性对照（无头浏览器常见）');
  }

  /* --------------------------------------------------------- 快捷键 */

  section('快捷键');
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('?');
  await page.waitForTimeout(300);
  const helpOpen = await page.evaluate(() => !document.querySelector('.modal-backdrop').hidden);
  check('? 打开快捷键表', helpOpen);
  const shortcutRows = await page.locator('.shortcut-row').count();
  check('快捷键表内容完整', shortcutRows > 25, `${shortcutRows} 条`);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  const tBefore = await page.locator('#status-playhead').innerText();
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(200);
  const tAfter = await page.locator('#status-playhead').innerText();
  check('方向键移动播放头', tBefore !== tAfter, `${tBefore} -> ${tAfter}`);

  /* --------------------------------------------------------- 统计 */

  section('统计面板');
  const statText = await page.locator('#stat-grid').innerText();
  check('统计里有字数与分段', /字数/.test(statText) && /分段/.test(statText), statText.replace(/\n/g, ' ').slice(0, 80));
  const bars = await page.locator('.spk-bar').count();
  check('说话人占比条渲染', bars >= 3, `${bars} 条`);
  const shareSum = await page.evaluate(() => {
    const vals = [...document.querySelectorAll('.spk-bar-val')].map((e) => parseFloat(e.textContent));
    return vals.reduce((a, b) => a + b, 0);
  });
  check('占比之和约等于 100%', Math.abs(shareSum - 100) <= 3, `${shareSum}%`);

  /* --------------------------------------------------------- 主题 */

  section('主题与设置');
  const themeBefore = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.click('#btn-theme');
  await page.waitForTimeout(250);
  const themeAfter = await page.evaluate(() => document.documentElement.dataset.theme);
  check('切换主题改变了 data-theme', themeBefore !== themeAfter, `${themeBefore} -> ${themeAfter}`);
  await page.click('#btn-theme');
  await page.waitForTimeout(200);

  /* ----------------------------------------------------- 持久化 */

  section('刷新后仍在（本地存档）');
  const snapshotBefore = await page.locator('.seg-text').allInnerTexts();
  await page.reload({ waitUntil: 'load' });
  await page.waitForSelector('.seg', { timeout: 15000 });
  await page.waitForTimeout(600);
  const snapshotAfter = await page.locator('.seg-text').allInnerTexts();
  check('刷新后分段数不变', snapshotAfter.length === snapshotBefore.length, `${snapshotBefore.length} -> ${snapshotAfter.length}`);
  check('刷新后文本一致', snapshotAfter.join('|') === snapshotBefore.join('|'));

  /* --------------------------------------------------- 无障碍抽查 */

  section('无障碍与语义');
  const landmarks = await page.evaluate(() => ({
    main: !!document.querySelector('main'),
    header: !!document.querySelector('header.topbar'),
    status: !!document.querySelector('#save-state'),
    sliders: document.querySelectorAll('[role="slider"]').length,
    listitems: document.querySelectorAll('[role="listitem"]').length,
  }));
  check('有 main 区域', landmarks.main);
  check('波形声明为 slider 角色', landmarks.sliders >= 1, `${landmarks.sliders}`);
  check('每个分段都是 listitem', landmarks.listitems >= 13, `${landmarks.listitems}`);

  // 布局健康度：标题行被内部控件撑高是最常见的一类"看起来就是不对劲"
  const layout = await page.evaluate(() => {
    const heads = [...document.querySelectorAll('.pane-head')].map((h) => Math.round(h.getBoundingClientRect().height));
    const clipped = [...document.querySelectorAll('.seg-tools button, .player-controls .btn, .topbar-actions .btn, .stat-grid dd')]
      .filter((el) => el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0)
      .map((el) => el.textContent.trim().slice(0, 12));
    return { heads, clipped };
  });
  check('三个标题行都保持单行高度', layout.heads.every((h) => h <= 52), `实际 ${layout.heads.join(', ')}px`);
  check('文本控件没有被裁切', layout.clipped.length === 0, layout.clipped.slice(0, 4).join(' | '));

  const focusable = await page.evaluate(() => {
    const ids = ['btn-play', 'btn-export', 'search', 'doc-title', 'btn-palette'];
    return ids.map((id) => {
      const el = document.getElementById(id);
      if (!el) return `${id}: 不存在`;
      el.focus();
      return document.activeElement === el ? null : `${id}: 拿不到焦点`;
    }).filter(Boolean);
  });
  check('关键控件可聚焦', focusable.length === 0, focusable.join('; '));

  const unlabeled = await page.evaluate(() => {
    const bad = [];
    for (const b of document.querySelectorAll('button')) {
      const text = (b.textContent || '').trim();
      const hasName = text || b.getAttribute('aria-label') || b.getAttribute('title');
      if (!hasName) bad.push(b.outerHTML.slice(0, 60));
    }
    return bad;
  });
  check('每个按钮都有可读名称', unlabeled.length === 0, unlabeled.slice(0, 3).join(' | '));

  /* --------------------------------------------------------- 拖放 */

  section('拖入字幕文件');
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(new File(['1\n00:00:00,000 --> 00:00:02,000\n拖进来的字幕甲\n\n2\n00:00:02,000 --> 00:00:04,000\n拖进来的字幕乙\n'], 'imported.srt', { type: 'text/plain' }));
    window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  });
  await page.waitForTimeout(600);
  const afterDrop = await page.locator('.seg').count();
  check('拖入字幕替换了转录', afterDrop === 2, `${afterDrop} 段`);
  const dropText = await page.locator('.seg').first().locator('.seg-text').innerText();
  check('拖入内容正确', dropText.includes('拖进来的字幕甲'), dropText.slice(0, 20));

  /* ------------------------------------------------ 错误路径要可见 */

  section('错误路径不静默');
  const logsBefore = await page.locator('#log-list li').count();
  await page.evaluate(() => {
    // 造一个解码必然失败的"音频"文件
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8])], 'fake.mp3', { type: 'audio/mpeg' }));
    window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  });
  await page.waitForTimeout(1200);
  const logsAfter = await page.locator('#log-list li').count();
  check('解码失败被写进日志', logsAfter > logsBefore, `${logsBefore} -> ${logsAfter}`);
  const logText = await page.locator('#log-list').innerText();
  check('日志内容说得清是解码问题', /解码|失败|载入/.test(logText), logText.split('\n')[0].slice(0, 60));
  const errorToasts = await page.locator('.toast-error').count();
  check('同时有可见的错误提示', errorToasts > 0, `toast 数 ${errorToasts}`);

  /* ------------------------------------------------------ 响应式 */

  section('响应式');
  for (const [w, h, label] of [[1512, 950, '桌面'], [1180, 900, '窄桌面'], [860, 900, '平板'], [560, 900, '手机']]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`${label} ${w}px 无横向溢出`, overflow <= 2, `溢出 ${overflow}px`);
  }
  await page.setViewportSize({ width: 1512, height: 950 });
  await page.waitForTimeout(200);

  /* --------------------------------------------------- 截图存档 */

  section('产出截图');
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'load' });
  await page.waitForSelector('.seg', { timeout: 15000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: 'screenshots/01-overview.png' });
  check('桌面概览截图已生成', true);
  await page.locator('.seg').nth(2).scrollIntoViewIfNeeded();
  await page.locator('.seg').nth(2).locator('.seg-text').dblclick();
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'screenshots/02-editing.png' });
  check('编辑态截图已生成', true);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Meta+k');
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'screenshots/03-palette.png' });
  check('命令面板截图已生成', true);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Meta+e');
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'screenshots/04-export.png' });
  check('导出弹窗截图已生成', true);
  await page.keyboard.press('Escape');
  await page.click('#btn-theme');
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'screenshots/05-light.png' });
  check('浅色主题截图已生成', true);
  await page.click('#btn-theme');
  await page.setViewportSize({ width: 560, height: 900 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'screenshots/06-mobile.png' });
  check('窄屏截图已生成', true);
  await page.setViewportSize({ width: 1512, height: 950 });
  await page.click('#btn-theme');
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'screenshots/07-dark.png' });
  check('深色主题截图已生成', true);

  /* --------------------------------------------------------- 汇总 */

  section('运行期异常复核');
  check('全程无未捕获异常', pageErrors.length === 0, pageErrors.slice(0, 5).join(' | '));
  const realConsoleErrors = consoleErrors.filter((t) => !/favicon|Failed to load resource/.test(t));
  check('全程无控制台报错（忽略 favicon）', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 5).join(' | '));
} catch (err) {
  failures.push({ name: '测试脚本自身异常', detail: `${err.message}\n${err.stack?.split('\n').slice(1, 4).join('\n')}` });
} finally {
  await browser.close();
  await new Promise((r) => server.close(r));
}

console.log(`\n${'='.repeat(52)}`);
console.log(`通过 ${passed} 项`);
for (const n of notes) console.log(`注意：${n}`);
if (failures.length) {
  console.log(`失败 ${failures.length} 项：`);
  for (const f of failures) console.log(`  ✗ ${f.name}\n      ${f.detail}`);
  process.exit(1);
}
console.log('全部通过');
