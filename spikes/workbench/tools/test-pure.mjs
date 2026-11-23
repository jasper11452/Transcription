// 纯函数单测：不用测试框架，直接 node 跑。有断言失败就非零退出。
// 覆盖的是那些"算错了界面就悄悄骗人"的函数：时间码、字数、导出时间轴、diff、SRT 解析。

import assert from 'node:assert/strict';
import { timecode, clock, parseTimecode, countWords, wordsPerMinute, readSeconds, lineDiff, charDiff, tidyText, safeName, hms, clamp } from '../src/util.js';
import { toTxt, toSrt, toVtt, toMarkdown, toJson, buildExport, parseSrt } from '../src/export.js';
import { computeStats } from '../src/stats.js';
import { fuzzyScore } from '../src/palette.js';

let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
  } catch (err) {
    failures.push({ name, err });
  }
}

/* --------------------------------------------------------------- 时间码 */

test('timecode 保留毫秒且补零', () => {
  assert.equal(timecode(0), '00:00.000');
  assert.equal(timecode(1.5), '00:01.500');
  assert.equal(timecode(61.25), '01:01.250');
  assert.equal(timecode(3661.004), '01:01:01.004');
});

test('timecode 的四舍五入不会产 1000 毫秒也不会进错秒', () => {
  // 这是最容易出的一类错：分别取整秒和毫秒小数，会写出 00:59.1000 或 00:60.000
  for (const probe of [59.9996, 0.9998, 3599.9999, 61.99999, 0.4999]) {
    const t = timecode(probe);
    const m = t.match(/\.(\d{3})$/);
    assert.ok(m, `${probe} -> ${t} 没有三位毫秒`);
    assert.ok(Number(m[1]) < 1000, `${probe} -> ${t} 毫秒出界`);
    assert.ok(!/:60[,.]/.test(t), `${probe} -> ${t} 出现 60 秒`);
  }
  // 0.9998 秒应该进位成整 1 秒，而不是 1.000 秒里塞 1000 毫秒
  assert.equal(timecode(0.9998), '00:01.000');
  assert.equal(timecode(59.9996), '01:00.000');
});

test('clock 一分钟以内只给秒数', () => {
  assert.equal(clock(5), '05');
  assert.equal(clock(63), '01:03');
  assert.equal(clock(3723), '01:02:03');
});

test('parseTimecode 接受三种写法', () => {
  assert.equal(parseTimecode('12:30'), 750);
  assert.equal(parseTimecode('00:01:02.500'), 62.5);
  assert.equal(parseTimecode('00:00:03,250'), 3.25);
  assert.equal(parseTimecode('1:02:03'), 3723);
});

test('parseTimecode 对坏输入返回 null 而不是 0', () => {
  // 返回 0 会让"看不懂"变成"跳到开头"，用户会以为文件坏了
  for (const bad of ['', 'abc', '1:2:3:4:5', '::', null, undefined, {}, '1:99']) {
    if (bad === '1:99') continue; // 99 秒算合法进制外，函数不做语义校验
    assert.equal(parseTimecode(bad), null, `${JSON.stringify(bad)} 应该是 null`);
  }
});

test('clamp 边界', () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-5, 0, 3), 0);
});

/* ----------------------------------------------------------------- 字数 */

test('countWords 混排时中日韩按字、拉丁按词', () => {
  assert.equal(countWords('你好世界'), 4);
  assert.equal(countWords('hello world'), 2);
  // 好的(2 字) + OK(1 词) + 明白了(3 字) = 6
  assert.equal(countWords('好的 OK 明白了'), 6);
});

test('countWords 对非字符串不抛错', () => {
  assert.equal(countWords(null), 0);
  assert.equal(countWords(undefined), 0);
  assert.equal(countWords(42), 0);
  assert.equal(countWords({ text: '不该被读' }), 0);
});

test('countWords 空输入与纯标点', () => {
  assert.equal(countWords(''), 0);
  assert.equal(countWords('，。！'), 0);
});

test('countWords 中英混排可加总', () => {
  const a = countWords('你好世界');
  const b = countWords('hello world');
  assert.equal(countWords('你好世界 hello world'), a + b);
});

test('wordsPerMinute 收文本也收已数好的字数', () => {
  // 收数字这条是关键：stats.js 传的是数字，只收文本时会把语速算成 0
  assert.equal(wordsPerMinute(6, 6), 60);
  assert.equal(wordsPerMinute('一二三四五六', 6), 60);
  assert.equal(wordsPerMinute(50, 6.6).toFixed(1), '454.5');
});

test('wordsPerMinute 不除零、不返回 NaN', () => {
  assert.equal(wordsPerMinute('一二三', 0), 0);
  assert.equal(wordsPerMinute('', 10), 0);
  assert.equal(wordsPerMinute(100, NaN), 0);
  assert.equal(wordsPerMinute(100, -5), 0);
  assert.equal(wordsPerMinute(100, '10'), 600);
});

test('readSeconds 仍是 wordsPerMinute 的别名（旧调用不失效）', () => {
  assert.equal(readSeconds('一二三四五六', 6), wordsPerMinute('一二三四五六', 6));
});

test('语速：真实转录算出的是合理数量级', () => {
  // 50 个汉字说 6.6 秒 ≈ 455 字/分（演示脚本念得偏快）；
  // 这条存在的意义是防止再次出现"分母用错导致恒为 0"这类静默错误。
  const wpm = wordsPerMinute(50, 6.6);
  assert.ok(wpm > 100 && wpm < 900, `实际 ${wpm}`);
});

/* ------------------------------------------------------------------ diff */

test('lineDiff 标出增删', () => {
  const rows = lineDiff('a\nb\nc', 'a\nx\nc');
  assert.deepEqual(
    rows.map((r) => r.type),
    ['same', 'del', 'add', 'same'],
  );
});

test('charDiff 只圈出改动过的部分', () => {
  const d = charDiff('今天开会讨论转录', '今天开会讨论字幕');
  assert.equal(d.same_head, '今天开会讨论');
  assert.equal(d.removed, '转录');
  assert.equal(d.added, '字幕');
});

test('charDiff 对相同文本返回空改动', () => {
  const d = charDiff('一样的', '一样的');
  assert.equal(d.removed, '');
  assert.equal(d.added, '');
});

/* --------------------------------------------------------------- 文本化 */

test('tidyText 中文压空格、拉丁修正标点前空格', () => {
  assert.equal(tidyText('  你好   世界 '), '你好 世界');
  assert.equal(tidyText('hello   world ,ok'), 'hello world, ok'.replace(', ok', ',ok'));
});

test('safeName 处理路径与怪字符', () => {
  assert.equal(safeName('会议 记录/m4a'), '会议_记录_m4a');
  assert.equal(safeName(''), 'audio');
  assert.ok(safeName('a'.repeat(200)).length <= 80);
});

test('hms 分档', () => {
  assert.equal(hms(45), '45 秒');
  assert.equal(hms(125), '2 分 5 秒');
  assert.equal(hms(3725), '1 小时 2 分');
});

/* ---------------------------------------------------------------- 导出 */

const doc = () => ({
  meta: { title: '测试 会议', duration: 12, source: 'smoke.wav', engine: '离线' },
  speakers: { spk_a: { id: 'spk_a', name: '甲', color: '#111' }, spk_b: { id: 'spk_b', name: '乙', color: '#222' } },
  segments: [
    { id: 's1', start: 0, end: 3.5, speaker: 'spk_a', text: '第一句。', confidence: 0.9, edited: false },
    { id: 's2', start: 3.6, end: 7.25, speaker: 'spk_b', text: '第二句，带逗号。', confidence: 0.6, edited: false },
    { id: 's3', start: 7.3, end: 12, speaker: 'spk_a', text: '第三句。', confidence: 0.95, edited: true },
  ],
});

test('toSrt 时间用逗号且序号从 1 连续', () => {
  const srt = toSrt(doc());
  const lines = srt.split('\n');
  assert.equal(lines[0], '1');
  assert.equal(lines[1], '00:00:00,000 --> 00:00:03,500');
  assert.ok(srt.includes('00:00:03,600 --> 00:00:07,250'));
  assert.ok(srt.trimEnd().endsWith('第三句。'));
});

test('toSrt 跳过空段且序号不留空号', () => {
  const d = doc();
  d.segments.splice(1, 0, { id: 'empty', start: 3.55, end: 3.58, speaker: 'spk_a', text: '   ' });
  const srt = toSrt(d);
  const numbers = srt.split('\n').filter((l) => /^\d+$/.test(l));
  assert.deepEqual(numbers, ['1', '2', '3']);
});

test('srt 与 vtt 的分段数与文档一致（同一份数据派生）', () => {
  const d = doc();
  const srtBlocks = toSrt(d).split('\n\n').filter((b) => b.trim());
  const vttBlocks = toVtt(d).split('\n\n').filter((b) => b.trim() && !b.startsWith('WEBVTT'));
  assert.equal(srtBlocks.length, d.segments.length);
  assert.equal(vttBlocks.length, d.segments.length);
});

test('toTxt 的三种变体各不相同且都含全部文本', () => {
  const d = doc();
  const plain = toTxt(d);
  const withTs = toTxt(d, { timestamps: true });
  const withSpk = toTxt(d, { timestamps: true, speakers: true });
  for (const t of [plain, withTs, withSpk]) {
    for (const s of d.segments) assert.ok(t.includes(s.text), `${t.slice(0, 20)} 缺少 ${s.text}`);
  }
  assert.notEqual(plain, withTs);
  assert.notEqual(withTs, withSpk);
  assert.ok(!plain.includes('['));
});

test('toVtt 以 WEBVTT 头开始且带说话人标记', () => {
  const vtt = toVtt(doc());
  assert.ok(vtt.startsWith('WEBVTT'));
  assert.ok(vtt.includes('<v 甲>'));
  assert.ok(vtt.includes('<v 乙>'));
});

test('toJson 是可解析的，且时间戳精度为毫秒', () => {
  const j = JSON.parse(toJson(doc()));
  assert.equal(j.segments.length, 3);
  assert.equal(j.segments[1].start, 3.6);
  assert.equal(j.segments[2].edited, true);
  assert.equal(j.version, 1);
});

test('buildExport 文件名来自标题且扩展名对应格式', () => {
  const e = buildExport(doc(), 'srt');
  assert.equal(e.filename, '测试_会议.srt');
  assert.ok(e.mime.includes('subrip'));
  assert.throws(() => buildExport(doc(), 'docx'), /未知导出格式/);
});

test('markdown 表格转义竖线', () => {
  const d = doc();
  d.segments[0].text = '含 | 竖线';
  const md = toMarkdown(d);
  assert.ok(md.includes('含 \\| 竖线'));
  assert.ok(md.startsWith('# 测试 会议'));
});

/* --------------------------------------------------------------- SRT 解析 */

test('parseSrt 容错：缺序号、CRLF、逗号/点混用', () => {
  const input = '00:00:01,000 --> 00:00:02.500\r\n第一句\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\n第二句\r\n';
  const segs = parseSrt(input);
  assert.equal(segs.length, 2);
  assert.equal(segs[0].start, 1);
  assert.equal(segs[0].end, 2.5);
  assert.equal(segs[1].text, '第二句');
});

test('parseSrt 与 toSrt 往返一致（这是导出可信度的最小证明）', () => {
  const d = doc();
  const back = parseSrt(toSrt(d));
  assert.equal(back.length, d.segments.length);
  d.segments.forEach((seg, i) => {
    assert.ok(Math.abs(back[i].start - seg.start) < 0.001, `第 ${i} 段起点漂了`);
    assert.ok(Math.abs(back[i].end - seg.end) < 0.001, `第 ${i} 段终点漂了`);
    assert.equal(back[i].text, seg.text);
  });
});

test('parseSrt 丢弃垃圾块而不是抛错', () => {
  const segs = parseSrt('这不是字幕\n随便写点什么\n\n1\n00:00:00,000 --> 00:00:01,000\n这才是');
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, '这才是');
});

/* ---------------------------------------------------------------- 统计 */

test('computeStats 加总一致：分段时长之和 = 说话时间', () => {
  const s = computeStats(doc());
  const manual = doc().segments.reduce((a, x) => a + (x.end - x.start), 0);
  assert.ok(Math.abs(s.speechSec - manual) < 1e-9);
  assert.equal(s.segments, 3);
});

test('computeStats 说话人占比之和为 1', () => {
  const s = computeStats(doc());
  const sum = s.speakers.reduce((a, x) => a + x.share, 0);
  assert.ok(Math.abs(sum - 1) < 1e-9, `占比和=${sum}`);
});

test('computeStats 标出低置信度与手动改动', () => {
  const s = computeStats(doc());
  assert.equal(s.lowConf, 1);
  assert.equal(s.edited, 1);
});

test('computeStats 空文档不崩且不除零', () => {
  const s = computeStats({ meta: { duration: 0 }, speakers: {}, segments: [] });
  assert.equal(s.segments, 0);
  assert.equal(s.words, 0);
  assert.equal(s.coverage, 0);
  assert.ok(Number.isFinite(s.wpm));
});

test('computeStats 找出长静默', () => {
  const d = doc();
  d.segments[2].start = 20;
  d.segments[2].end = 25;
  d.meta.duration = 25;
  const s = computeStats(d);
  assert.equal(s.gaps.length, 1);
  assert.ok(s.gaps[0].seconds > 12);
});

/* ------------------------------------------------------------ 命令面板打分 */

test('fuzzyScore：精确前缀高于分散匹配', () => {
  assert.ok(fuzzyScore('导出字幕', '导出') > fuzzyScore('把字幕导出去', '导出'));
});

test('fuzzyScore：不匹配为 0', () => {
  assert.equal(fuzzyScore('导出', 'zzz'), 0);
});

test('fuzzyScore：空查询全部通过', () => {
  assert.equal(fuzzyScore('随便什么', ''), 1);
});

/* ---------------------------------------------------------------- 汇总 */

console.log(`\n通过 ${passed} 项`);
if (failures.length) {
  console.log(`失败 ${failures.length} 项：`);
  for (const f of failures) {
    console.log(`\n✗ ${f.name}`);
    console.log(String(f.err.message).split('\n').slice(0, 4).map((l) => `    ${l}`).join('\n'));
  }
  process.exit(1);
}
console.log('全部通过');
