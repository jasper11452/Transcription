// store 层的行为测试：撤销/重做、持久化、以及所有分段操作的一致性不变量。
//
// 为什么值得为它搭一个 DOM 桩：store 是"数据是否可信"的唯一来源，
// 而它只能在浏览器里跑得到——不测就等于这一层完全没有验证。
// 桩只实现 store 用到的东西：localStorage 与 structuredClone。

import assert from 'node:assert/strict';

/* ------------------------------------------------------ 最小环境桩 */

class MemoryStorage {
  constructor() {
    this.map = new Map();
    this.quota = Infinity;
  }
  getItem(k) {
    return this.map.has(String(k)) ? this.map.get(String(k)) : null;
  }
  setItem(k, v) {
    const s = String(v);
    if (s.length > this.quota) {
      const e = new Error('QuotaExceededError');
      e.name = 'QuotaExceededError';
      throw e;
    }
    this.map.set(String(k), s);
  }
  removeItem(k) {
    this.map.delete(String(k));
  }
  clear() {
    this.map.clear();
  }
}

const { createStore, NO_CHANGE } = await import('../src/store.js');
const { parseSrt } = await import('../src/export.js');

let passed = 0;
const failures = [];

/**
 * 每条用例一个全新的存储环境与 store 工厂。
 * 共享一个 localStorage 会让用例互相污染——"上一条刚存的值"会变成下一条的初始状态，
 * 于是同一份断言在不同执行顺序下给出不同结果。这类测试比没有测试更坏。
 */
function test(name, fn) {
  try {
    const env = makeEnv();
    fn(env);
    passed += 1;
  } catch (err) {
    failures.push({ name, err });
  }
}

function makeEnv() {
  const storage = new MemoryStorage();
  return {
    storage,
    /** 新建一个 store，用本用例私有的存储 */
    store() {
      const s = createStore({ storage });
      s.load();
      return s;
    },
    /** 预置一段"已保存"的文档 */
    seeded() {
      const s = createStore({ storage });
      s.load();
      s.replaceDoc(
        {
          meta: { title: '会话', duration: 30, source: 'x.wav', engine: '离线' },
          segments: [
            { id: 'a', start: 0, end: 5, speaker: 'spk_a', text: '第一段' },
            { id: 'b', start: 5.2, end: 10, speaker: 'spk_b', text: '第二段' },
            { id: 'c', start: 10.5, end: 16, speaker: 'spk_a', text: '第三段' },
          ],
        },
        { markDirty: false },
      );
      return s;
    },
  };
}

/** 时间轴不变量：不重叠、倒序不超过 0、每段长度 > 0 */
function assertTimelineSane(store, where) {
  const segs = store.doc.segments;
  for (let i = 0; i < segs.length; i += 1) {
    const s = segs[i];
    assert.ok(s.end > s.start, `${where}: 第 ${i + 1} 段长度非正 (${s.start}..${s.end})`);
    assert.ok(s.start >= -1e-9, `${where}: 第 ${i + 1} 段起点为负`);
    if (i > 0) {
      const prev = segs[i - 1];
      assert.ok(
        s.start >= prev.end - 1e-9,
        `${where}: 第 ${i} 段 (${prev.start}..${prev.end}) 与第 ${i + 1} 段 (${s.start}..${s.end}) 重叠`,
      );
    }
  }
}

/* --------------------------------------------------------- 基础行为 */

test('初始文档为空且有默认说话人', (env) => {
  const s = env.store();
  assert.equal(s.doc.segments.length, 0);
  assert.ok(Object.keys(s.doc.speakers).length >= 2);
});

test('commit 产生撤销点，undo 回到前一刻', (env) => {
  const s = env.seeded();
  s.updateText('a', '改过了');
  assert.equal(s.doc.segments[0].text, '改过了');
  assert.ok(s.canUndo);
  s.undo();
  assert.equal(s.doc.segments[0].text, '第一段');
  assert.ok(s.canRedo);
  s.redo();
  assert.equal(s.doc.segments[0].text, '改过了');
});

test('连续多步 undo 能一路回到最初', (env) => {
  const s = env.seeded();
  s.updateText('a', 'A1');
  s.updateText('b', 'B1');
  s.updateText('c', 'C1');
  s.undo();
  s.undo();
  s.undo();
  assert.deepEqual(s.doc.segments.map((x) => x.text), ['第一段', '第二段', '第三段']);
  assert.equal(s.canUndo, false);
});

test('新提交清空重做栈（这是最容易写错的一条）', (env) => {
  const s = env.seeded();
  s.updateText('a', 'X');
  s.undo();
  assert.ok(s.canRedo);
  s.updateText('b', 'Y');
  assert.equal(s.canRedo, false, '新操作之后不该还能重做旧的');
});

test('undo 不到底时不抛错', (env) => {
  const s = env.seeded();
  assert.equal(s.undo(), false);
  assert.equal(s.redo(), false);
});

test('undo 之后数据与重新持久化的一致（存档不能留下撤销掉的中间态）', (env) => {
  const s = env.seeded();
  s.deleteSegments(['b']);
  assert.equal(s.doc.segments.length, 2);
  s.undo();
  assert.equal(s.doc.segments.length, 3);
  const raw = JSON.parse(env.storage.getItem('workbench.transcript.v1'));
  assert.equal(raw.segments.length, 3, '存档里应该也是 3 段');
});

test('本地存档能还原（关掉页面再回来）', (env) => {
  const s = env.seeded();
  s.updateText('a', '持久化测试');
  const s2 = env.store();
  assert.equal(s2.doc.segments.length, 3);
  assert.equal(s2.doc.segments[0].text, '持久化测试');
});

test('存档被写坏时 load 不抛错，退回空文档', (env) => {
  env.storage.setItem('workbench.transcript.v1', '{这不是 json');
  const s = env.store();
  assert.equal(s.doc.segments.length, 0);
});

test('存档里 segments 不是数组时也不崩', (env) => {
  env.storage.setItem('workbench.transcript.v1', JSON.stringify({ segments: 'nope' }));
  const s = env.store();
  assert.equal(s.doc.segments.length, 0);
});

test('存储写满时报错但不影响内存里的数据', (env) => {
  const s = env.seeded();
  env.storage.quota = 10;
  let seen = null;
  s.on('error', (e) => {
    seen = e;
  });
  s.updateText('a', '很长的一段文字用来撑爆配额');
  assert.ok(seen, '应该抛出可见的错误事件，而不是静默吞掉');
  assert.ok(s.doc.segments[0].text.includes('很长'));
});

test('settings 变更也会持久化', (env) => {
  const s = env.store();
  s.setSetting('fontScale', 1.25);
  const s2 = env.store();
  assert.equal(s2.settings.fontScale, 1.25);
});

/* ------------------------------------------------------- 分段操作 */

test('拆分：时间与文字都被切开，总文本不变', (env) => {
  const s = env.seeded();
  const before = s.doc.segments.map((x) => x.text).join('');
  const res = s.splitSegment('c', 13);
  assert.ok(res, '应该拆成功');
  assertTimelineSane(s, '拆分后');
  const joined = s.doc.segments.map((x) => x.text).join('');
  assert.equal(joined.replace(/\s/g, ''), before.replace(/\s/g, ''), '拆分不该凭空产生或吞掉文字');
  assert.equal(s.doc.segments.length, 4);
});

test('段太短时拆分被拒绝，而不是造出零长度段', (env) => {
  const s = env.seeded();
  s.commit('造短段', (d) => {
    d.segments.push({ id: 'tiny', start: 20, end: 20.3, speaker: 'spk_a', text: '好' });
    return true;
  });
  const res = s.splitSegment('tiny', 20.15);
  assert.equal(res, NO_CHANGE);
  assert.equal(s.doc.segments.find((x) => x.id === 'tiny').end, 20.3, '被拒绝时不该改动原段');
  assertTimelineSane(s, '拒绝拆分后');
});

test('拆分点落在段外时被夹回段内（不会造出越界段）', (env) => {
  const s = env.seeded();
  const res = s.splitSegment('a', 999);
  assert.ok(res);
  assert.ok(res.head.end < 5 && res.head.end > 0, `切点应被夹在段内，实际 ${res.head.end}`);
  assertTimelineSane(s, '拆分点越界后');
  assert.equal(s.doc.segments.length, 4);
});

test('合并：时长接续、文字拼接、段数减一', (env) => {
  const s = env.seeded();
  s.mergeWithNext('a');
  assertTimelineSane(s, '合并后');
  assert.equal(s.doc.segments.length, 2);
  assert.equal(s.doc.segments[0].end, 10);
  assert.ok(s.doc.segments[0].text.includes('第一段'));
  assert.ok(s.doc.segments[0].text.includes('第二段'));
});

test('最后一段没有下一段可合并时返回哨兵', (env) => {
  const s = env.seeded();
  assert.equal(s.mergeWithNext('c'), NO_CHANGE);
  assert.equal(s.doc.segments.length, 3);
});

test('批量合并保持顺序且不重叠', (env) => {
  const s = env.seeded();
  s.mergeRange(['a', 'b', 'c']);
  assertTimelineSane(s, '批量合并后');
  assert.equal(s.doc.segments.length, 1);
  assert.equal(s.doc.segments[0].start, 0);
  assert.equal(s.doc.segments[0].end, 16);
});

test('删除多段后时间轴仍单调', (env) => {
  const s = env.seeded();
  s.deleteSegments(['b']);
  assertTimelineSane(s, '删除后');
  assert.deepEqual(s.doc.segments.map((x) => x.id), ['a', 'c']);
});

test('插入段落落在相邻两段之间的空隙里', (env) => {
  const s = env.seeded();
  const seg = s.insertAfter(0);
  assertTimelineSane(s, '插入后');
  assert.ok(seg.start >= s.doc.segments[0].end - 1e-9);
  assert.ok(seg.end <= s.doc.segments[2].start + 1e-9, '不该吃到第三段');
});

test('改时间不破坏顺序，且能撤销', (env) => {
  const s = env.seeded();
  s.retime('b', 5.5, 9.5);
  assertTimelineSane(s, '改时间后');
  s.undo();
  assert.equal(s.doc.segments[1].start, 5.2);
});

test('retime 不允许终点越过起点', (env) => {
  const s = env.seeded();
  s.retime('b', 9, 6);
  const seg = s.doc.segments[1];
  assert.ok(seg.end > seg.start, `终点应该被顶回起点之后：${seg.start}..${seg.end}`);
});

test('改说话人不影响文本与时间', (env) => {
  const s = env.seeded();
  s.setSpeaker('a', 'spk_b');
  assert.equal(s.doc.segments[0].speaker, 'spk_b');
  assert.equal(s.doc.segments[0].text, '第一段');
  assert.equal(s.doc.segments[0].end, 5);
});

test('待复核标记可反复切换且进撤销栈', (env) => {
  const s = env.seeded();
  s.toggleFlag('a');
  assert.equal(s.doc.segments[0].flag, true);
  s.toggleFlag('a');
  assert.equal(s.doc.segments[0].flag, false);
  s.toggleFlag('a');
  s.undo();
  assert.equal(s.doc.segments[0].flag, false);
});

test('合并过短分段只吃同说话人、且在时间上真正相邻的短段', (env) => {
  const s = env.seeded();
  // 第一段之后插一个同说话人的 0.45 秒小段（紧接第一段）；
  // 它后面那段（5.2-10）在时间上跟它重叠，不该参与合并
  s.commit('造短段', (d) => {
    d.segments.splice(1, 0, { id: 'tiny', start: 5.0, end: 5.45, speaker: 'spk_a', text: '嗯' });
    return true;
  });
  const n = s.mergeAdjacentShort(1.2);
  assert.equal(n, 1, '应该只合并那一个与第一段相邻的 0.45 秒同说话人段');
  assert.equal(s.doc.segments[0].end, 5.45, '第一段应该接管小段的终点');
  // 注意：这条用例的 fixture 本身就把 5.2-10 那段做成了与小段重叠，
  // 所以这里不能断言整条时间轴干净——被合并后它仍然与 5.45 重叠。
  assert.equal(s.doc.segments.length, 3, '第二段不该被吃掉');
});

test('时间上重叠的分段不会被误合并', (env) => {
  const s = env.seeded();
  s.commit('造重叠的短段', (d) => {
    d.segments.splice(1, 0, { id: 'tiny', start: 4.9, end: 5.3, speaker: 'spk_a', text: '嗯' });
    return true;
  });
  const beforeEnd = s.doc.segments[0].end;
  const n = s.mergeAdjacentShort(1.2);
  assert.equal(n, NO_CHANGE, '与上一段重叠就不该合');
  assert.equal(s.doc.segments[0].end, beforeEnd, '被拒绝时不该改动第一段的终点');
  assert.equal(s.doc.segments.length, 4, '段数不该变');
});

test('规整时间轴消除人为重叠', (env) => {
  const s = env.seeded();
  s.commit('造重叠', (d) => {
    d.segments[1].start = 3; // 与第一段重叠
    return true;
  });
  const fixed = s.normalizeTimeline();
  assert.ok(fixed >= 1);
  assertTimelineSane(s, '规整后');
});

test('批量替换按段计数并可正则', (env) => {
  const s = env.seeded();
  const n = s.replaceAllText('第(\\S+)段', '[$1]', { regex: true });
  assert.equal(n, 3);
  assertTimelineSane(s, '替换后');
  assert.equal(s.doc.segments[0].text, '[一]');
});

test('批量替换对无命中返回哨兵且不产生撤销点', (env) => {
  const s = env.seeded();
  const n = s.replaceAllText('不存在的东西', 'x');
  assert.equal(n, NO_CHANGE);
  assert.equal(s.canUndo, false, '没改东西就不该留撤销点');
});

test('replaceDoc 清空历史（导入新文件不该能撤销回上一个文件）', (env) => {
  const s = env.seeded();
  s.updateText('a', 'x');
  assert.ok(s.canUndo);
  s.replaceDoc({ meta: {}, segments: [{ id: 'z', start: 0, end: 1, text: '新的' }] });
  assert.equal(s.canUndo, false);
  assert.equal(s.doc.segments.length, 1);
});

test('replaceDoc 给缺 id 的分段补 id，并规范字段', (env) => {
  const s = env.seeded();
  s.replaceDoc({ meta: {}, segments: [{ start: '1.5', end: '3', text: 'x', confidence: '0.5' }] });
  const seg = s.doc.segments[0];
  assert.ok(seg.id);
  assert.equal(seg.start, 1.5);
  assert.equal(seg.end, 3);
  assert.equal(seg.speaker, 'spk_a', '缺说话人时要有默认值');
  assert.equal(seg.confidence, undefined, '非数字置信度应被丢掉而不是留成字符串');
});

test('replaceDoc 的 segments 缺字段时不崩', (env) => {
  const s = env.seeded();
  s.replaceDoc({ meta: {}, segments: [{ text: '只有文字' }, { start: 1 }] });
  assert.equal(s.doc.segments.length, 2);
  assert.ok(s.doc.segments.every((x) => x.id && typeof x.start === 'number' && typeof x.end === 'number'));
});

test('dirty 标志跟随改动与保存', (env) => {
  const s = env.seeded();
  assert.equal(s.dirty, false);
  s.updateText('a', '变了');
  assert.equal(s.dirty, true);
  s.markSaved();
  assert.equal(s.dirty, false);
});

test('unsavedWork 只认真有未落盘的转录改动', (env) => {
  const s = env.seeded();
  // 刚载入/刚预置：磁盘和内存一致，不该拦刷新
  assert.equal(s.unsavedWork, false, '刚载入就算拦，等于每次刷新都弹确认');
  s.updateText('a', '改了标题级的内容');
  assert.equal(s.dirty, true);
  assert.equal(s.unsavedWork, false, 'commit 已经自动落盘，内存与磁盘一致，不该拦');
});

test('unsavedWork 在写盘失败时为真（不能让用户以为存住了）', (env) => {
  const s = env.seeded();
  env.storage.quota = 10; // 后续写入必然失败
  const seen = [];
  s.on('error', (e) => seen.push(e));
  s.updateText('a', '这段写不进去了');
  assert.ok(seen.length > 0, '应该有可见的错误事件');
  assert.equal(s.unsavedWork, true, '写盘失败时必须拦刷新，否则改动静默丢失');
});

test('改设置不触发离开拦截', (env) => {
  const s = env.seeded();
  s.setSetting('theme', 'light');
  s.setSetting('fontScale', 1.3);
  assert.equal(s.unsavedWork, false, '主题/字号不该让用户看到离开确认');
});

test('改说话人名字算改动内容，会被拦住', (env) => {
  const s = env.seeded();
  env.storage.quota = 0;
  s.renameSpeaker('spk_a', '新名字');
  assert.equal(s.unsavedWork, true);
});

test('未改动的重复提交不留撤销点也不标脏', (env) => {
  const s = env.seeded();
  s.updateText('a', '第一段'); // 与原值相同
  assert.equal(s.canUndo, false);
  assert.equal(s.dirty, false);
});

test('replaceDoc 默认标脏（导入的内容还没被保存过）', (env) => {
  const s = env.seeded();
  assert.equal(s.dirty, false);
  s.replaceDoc({ meta: {}, segments: [{ id: 'z', start: 0, end: 1, text: '新的' }] });
  assert.equal(s.dirty, true);
  // 显式传 markDirty:false 时不该标脏（fixture / 恢复场景用）
  s.markSaved();
  s.replaceDoc({ meta: {}, segments: [{ id: 'z2', start: 0, end: 1, text: '又一份' }] }, { markDirty: false });
  assert.equal(s.dirty, false);
});

test('dirty 也能被持久化并在重启后恢复', (env) => {
  const s = env.seeded();
  s.updateText('a', 'x');
  assert.equal(s.dirty, true);
  const s2 = env.store();
  assert.equal(s2.dirty, true, '重启后仍应提示有未保存改动');
});

test('订阅者收到变更通知，能拿到 label', (env) => {
  const s = env.seeded();
  const seen = [];
  s.subscribe((doc, settings, info) => seen.push(info.reason));
  s.updateText('a', 'x');
  assert.equal(seen.at(-1), '修改文本');
});

test('统计随文档变化而失效重算', (env) => {
  const s = env.seeded();
  const w1 = s.stats.words;
  s.updateText('a', '第一段第一段第一段第一段');
  assert.ok(s.stats.words > w1, '字数统计没有跟着更新');
});

test('被删段落的统计不再计入', (env) => {
  const s = env.seeded();
  const before = s.stats.segments;
  s.deleteSegments(['a', 'b']);
  assert.equal(s.stats.segments, before - 2);
});

test('导入 SRT 后统计可用且时间轴干净', (env) => {
  const s = env.store();
  const segs = parseSrt('1\n00:00:00,000 --> 00:00:02,000\n甲\n\n2\n00:00:02,000 --> 00:00:04,000\n乙\n');
  s.replaceDoc({ meta: { duration: 4 }, segments: segs }, { markDirty: false });
  assert.equal(s.doc.segments.length, 2);
  assertTimelineSane(s, '导入字幕');
  assert.ok(s.stats.words >= 2);
});

test('撤销栈有上限且不会无限吃内存', (env) => {
  const s = env.seeded();
  for (let i = 0; i < 200; i += 1) s.updateText('a', `版本 ${i}`);
  assert.equal(s.doc.segments[0].text, '版本 199');
  // 60 步之后最早的状态应该已经丢掉
  let steps = 0;
  while (s.canUndo) {
    s.undo();
    steps += 1;
    if (steps > 500) break;
  }
  assert.ok(steps <= 60, `撤销步数 ${steps} 应该不超过 60`);
});

/* ---------------------------------------------------------- 汇总 */

console.log(`\n通过 ${passed} 项`);
if (failures.length) {
  console.log(`失败 ${failures.length} 项：`);
  for (const f of failures) {
    console.log(`\n✗ ${f.name}`);
    console.log(String(f.err.message).split('\n').slice(0, 5).map((l) => `    ${l}`).join('\n'));
  }
  process.exit(1);
}
console.log('全部通过');
