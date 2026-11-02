#!/usr/bin/env node
// 复现报告里的行数：node tools/count-lines.mjs（在 spikes/workbench 下跑）
// 口径：index.html + src/*.js + styles/*.css（tools/ 是测试脚手架，不计）
// 「代码行」= 去掉空行、以及以 //  /*  *  <!-- 开头的行
import { readFileSync } from 'node:fs';

const files = ['index.html', 'src/audio.js', 'src/export.js', 'src/main.js', 'src/palette.js',
  'src/stats.js', 'src/store.js', 'src/transcript.js', 'src/ui.js', 'src/util.js',
  'src/waveform.js', 'styles/app.css', 'styles/tokens.css'];
const lines = (p) => readFileSync(p, 'utf8').split('\n').length - 1;
const code = (p) => readFileSync(p, 'utf8').split('\n')
  .filter((l) => l.trim() && !/^\s*(\/\/|\/\*|\*|<!--)/.test(l)).length;

let tb = 0, tn = 0, cb = 0, cn = 0;
console.log('文件'.padEnd(22), '基线'.padStart(7), '现版'.padStart(7), '差'.padStart(8));
for (const f of files) {
  const b = lines(`.baseline/${f}`), n = lines(f);
  tb += b; tn += n; cb += code(`.baseline/${f}`); cn += code(f);
  console.log(f.padEnd(22), String(b).padStart(7), String(n).padStart(7), String(n - b).padStart(8));
}
console.log('合计'.padEnd(22), String(tb).padStart(7), String(tn).padStart(7), String(tn - tb).padStart(8));
const pct = (a, b) => `${((b - a) / a * 100).toFixed(1)}%`;
console.log(`\n总行数 ${tb} -> ${tn}  ${pct(tb, tn)}`);
console.log(`代码行 ${cb} -> ${cn}  ${pct(cb, cn)}`);
console.log(`50% 目标 ${Math.floor(tb / 2)} 行，还差 ${tn - Math.floor(tb / 2)} 行`);
