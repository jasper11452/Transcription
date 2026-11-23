// 本地静态服务：只绑 127.0.0.1，只服务本目录，用于让 ES module + fetch 走 http 协议。
//
// 用 Node 内置模块写，不引入任何依赖。三个硬约束：
//   1. 只监听回环地址，不对外暴露；
//   2. 路径解析后必须仍在根目录内（挡掉 ../ 与编码绕过）；
//   3. 不发任何 CORS 头——它没有跨源的使用场景。

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT || 8899);
const HOST = '127.0.0.1';

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.map': 'application/json; charset=utf-8',
};

/** 路径安全解析：任何解析后不在 ROOT 内的请求都拒绝 */
export function resolveSafe(urlPath, root = ROOT) {
  let decoded;
  try {
    decoded = decodeURIComponent(urlPath.split('?')[0].split('#')[0]);
  } catch {
    return { ok: false, code: 400, reason: '百分号编码有问题' };
  }
  if (decoded.includes('\0')) return { ok: false, code: 400, reason: '路径含空字节' };
  const rel = decoded === '/' ? 'index.html' : decoded.replace(/^\/+/, '');
  const abs = path.resolve(root, rel);
  const rootWithSep = root.endsWith(path.sep) ? root : root + path.sep;
  if (abs !== root && !abs.startsWith(rootWithSep)) return { ok: false, code: 403, reason: '越出服务根目录' };
  return { ok: true, abs };
}

export function createServer({ root = ROOT, quiet = false } = {}) {
  return http.createServer((req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('只支持 GET');
      return;
    }
    const r = resolveSafe(req.url || '/', root);
    if (!r.ok) {
      res.writeHead(r.code, { 'content-type': 'text/plain; charset=utf-8' });
      res.end(r.reason);
      return;
    }
    fs.stat(r.abs, (err, st) => {
      if (err || !st.isFile()) {
        res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
        res.end('没有这个文件');
        return;
      }
      const type = TYPES[path.extname(r.abs).toLowerCase()] || 'application/octet-stream';
      res.writeHead(200, {
        'content-type': type,
        'content-length': st.size,
        // 开发用：永远拿最新的源码，别让浏览器缓存骗人
        'cache-control': 'no-store',
        // 这一页不需要被任何地方嵌入，也不该被跨源读
        'x-content-type-options': 'nosniff',
        'cross-origin-resource-policy': 'same-origin',
      });
      if (req.method === 'HEAD') {
        res.end();
        return;
      }
      fs.createReadStream(r.abs)
        .on('error', () => {
          res.destroy();
        })
        .pipe(res);
    });
    if (!quiet) {
      const t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      console.log(`${t}  ${req.method} ${req.url}`);
    }
  });
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const server = createServer();
  server.listen(PORT, HOST, () => {
    console.log(`转录工作台：http://${HOST}:${PORT}/`);
    console.log('（只绑本机回环地址；Ctrl+C 停止）');
  });
  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      console.error(`端口 ${PORT} 已被占用。换一个：PORT=8900 node tools/serve.js`);
    } else {
      console.error('启动失败：', err.message);
    }
    process.exit(1);
  });
  for (const sig of ['SIGINT', 'SIGTERM']) {
    process.on(sig, () => {
      server.close(() => process.exit(0));
    });
  }
}
