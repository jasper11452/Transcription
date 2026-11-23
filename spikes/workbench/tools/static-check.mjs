// 静态自查：把每个模块里"看起来像函数调用但没在任何地方声明"的名字揪出来。
// 这是补不上浏览器的替代品里最有用的一条：真正会在运行时炸的是拼错的名字，不是格式问题。
import fs from 'node:fs';
import path from 'node:path';

const dir = process.argv[2] || 'src';
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.js'));

const BUILTINS = new Set(`if for while switch catch return typeof function new await async of in do else
case delete void yield super require import export default class const let var try throw finally break
continue instanceof Number String Boolean Array Object JSON Math Date Set Map WeakMap WeakSet Promise
Error TypeError RegExp parseInt parseFloat isNaN isFinite setTimeout clearTimeout setInterval clearInterval
requestAnimationFrame cancelAnimationFrame structuredClone fetch URL URLSearchParams Blob File FileReader
localStorage sessionStorage performance document window navigator console globalThis getComputedStyle Option
Uint8Array Float32Array Int8Array Uint16Array Uint32Array Int16Array TextEncoder TextDecoder queueMicrotask
btoa atob decodeURIComponent encodeURIComponent Symbol FormData AbortController ResizeObserver
AudioContext webkitAudioContext OfflineAudioContext MediaRecorder HTMLElement Element Node NodeList
matchMedia alert confirm prompt eval arguments undefined NaN Infinity`.split(/\s+/));

let problems = 0;
for (const f of files) {
  const src = fs.readFileSync(path.join(dir, f), 'utf8');
  // 去掉注释和字符串，避免把说明文字里的词当成代码
  const code = src
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:\\])\/\/[^\n]*/g, '$1 ')
    .replace(/`(?:[^`\\]|\\.)*`/g, '``')
    .replace(/'(?:[^'\\\n]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\\n]|\\.)*"/g, '""');

  const declared = new Set();
  const addAll = (list) => list.split(',').forEach((p) => { const n = p.split(':').pop().split('=')[0].trim(); if (/^[A-Za-z_$][\w$]*$/.test(n)) declared.add(n); });
  for (const m of code.matchAll(/(?:function|class)\s+([A-Za-z_$][\w$]*)/g)) declared.add(m[1]);
  // 函数/方法的形参一律算已声明：形参名后面当然会被调用
  for (const m of code.matchAll(/(?:function\s*[\w$]*|^\s*(?:async\s+)?(?:get\s+|set\s+|static\s+)?[\w$]+)\s*\(([^()]*)\)\s*\{/gm)) addAll(m[1]);
  for (const m of code.matchAll(/(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?\(([^()]*)\)\s*=>/g)) addAll(m[1]);
  for (const m of code.matchAll(/(?:^|[^\w$.])(?:async\s+)?\(([^()]*)\)\s*=>/gm)) addAll(m[1]);
  // 对象字面量的方法定义：play() { ... } / async run() { ... } / get stats() { ... }
  for (const m of code.matchAll(/^\s*(?:async\s+)?(?:get\s+|set\s+|static\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/gm)) declared.add(m[1]);
  for (const m of code.matchAll(/(?:^|[,{])\s*(?:async\s+)?(?:get\s+|set\s+)?([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{/gm)) declared.add(m[1]);
  for (const m of code.matchAll(/^\s*get\s+([A-Za-z_$][\w$]*)\s*\(/gm)) declared.add(m[1]);
  for (const m of code.matchAll(/(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) declared.add(m[1]);
  // 解构参数里的回调：function a({ onTime, onState } = {}) —— 这些名字后面会以 onTime(...) 的形式被调用
  for (const m of code.matchAll(/\{\s*([^{}]*?)\s*\}\s*=\s*\{\s*\}/g)) addAll(m[1]);
  for (const m of code.matchAll(/\(\s*\{([^{}]*?)\}\s*(?:,\s*[\w$]+\s*)?\)\s*(?:=>|\{)/g)) addAll(m[1]);
  for (const m of code.matchAll(/(?:const|let|var)\s*\{([^}]*)\}/g)) addAll(m[1]);
  for (const m of code.matchAll(/\(([^()]*)\)\s*=>/g)) addAll(m[1]);
  for (const m of code.matchAll(/([\w$]+)\s*=>/g)) declared.add(m[1]);
  for (const m of code.matchAll(/for\s*\(\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) declared.add(m[1]);
  for (const m of code.matchAll(/import\s*\{([^}]*)\}/g)) addAll(m[1]);
  for (const m of code.matchAll(/import\s+([A-Za-z_$][\w$]*)\s+from/g)) declared.add(m[1]);

  const called = new Map(); // name -> 第一次出现的行号
  code.split('\n').forEach((line, i) => {
    const trimmed = line.trim();
    // 裸回调调用（xxx(...) 单独成行，或 obj.fn(xxx(...)) 里的 xxx）
    for (const m of line.matchAll(/(?<![.\w$])([a-z_$][\w$]*)\s*\(/g)) {
      if (!called.has(m[1])) called.set(m[1], i + 1);
    }
  });

  const missing = [...called].filter(([n]) => !declared.has(n) && !BUILTINS.has(n));
  if (missing.length) {
    problems += missing.length;
    console.log(`${f}:`);
    for (const [n, line] of missing) console.log(`  L${line}  ${n}()`);
  }
}

// 顺带检查 import 的符号是否真的被导出（跨模块拼错导出名是最常见的一类）
for (const f of files) {
  const src = fs.readFileSync(path.join(dir, f), 'utf8');
  for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]\.\/([\w.-]+)['"]/g)) {
    const key = m[2].replace(/\.js$/, '');
    const target = path.join(dir, `${key}.js`);
    if (!fs.existsSync(target)) {
      console.log(`${f}: 找不到模块 ./${m[2]}`);
      problems += 1;
      continue;
    }
    const tsrc = fs.readFileSync(target, 'utf8');
    for (const raw of m[1].split(',')) {
      const name = raw.split(' as ')[0].trim();
      if (!name) continue;
      const exported = new RegExp(`export\\s+(?:const|let|var|function|class|async function)\\s+${name.replace(/\$/g, '\\$')}\\b`).test(tsrc)
        || new RegExp(`export\\s*\\{[^}]*\\b${name.replace(/\$/g, '\\$')}\\b`).test(tsrc);
      if (!exported) {
        console.log(`${f}: 从 ./${m[2]} 导入了 ${name}，但那边没有导出`);
        problems += 1;
      }
    }
  }
}

console.log(problems ? `\n发现 ${problems} 处可疑` : '\n未发现未声明调用或错误的导入');
process.exit(problems ? 1 : 0);
