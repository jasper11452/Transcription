#!/usr/bin/env bash
# 用 Flow 宿主做真浏览器端到端（与 tools/e2e-smoke.mjs 是两条独立路径，互为交叉验证）。
#
# 为什么两条都要留：
#   e2e-smoke.mjs 是我自己写的 Playwright 脚本，方便快速迭代；
#   Flow 那两条是外部的驱动与断言引擎，不共享我的假设——
#   这轮它抓到的问题（toast 挡住点击、beforeunload 过宽）我自己那套全都没发现。
set -euo pipefail

WORKBENCH="$(cd "$(dirname "$0")/.." && pwd)"
FLOW_HOME_DIR="${FLOW_HOME_DIR:-$HOME/flow}"
PORT="${PORT:-8899}"

if [ ! -d "$FLOW_HOME_DIR" ]; then
  echo "找不到 Flow 仓库：$FLOW_HOME_DIR（用 FLOW_HOME_DIR=... 指定）" >&2
  exit 1
fi

# 起工作台（若未在跑）
started=0
if ! curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
  PORT="$PORT" node "$WORKBENCH/tools/serve.js" >/tmp/workbench-flow-serve.log 2>&1 &
  SERVE_PID=$!
  started=1
  for _ in $(seq 1 40); do
    curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null && break
    sleep 0.25
  done
fi

cleanup() { [ "$started" = "1" ] && kill "$SERVE_PID" 2>/dev/null || true; }
trap cleanup EXIT

URL="http://127.0.0.1:${PORT}/"
cd "$FLOW_HOME_DIR"

# 先 lint，再跑；两条流程都用生产 FLOW_HOME（默认 ~/.flow），让坑库与 recipe 能沉淀
for flow in flow-wb-e2e flow-wb-viewports; do
  spec="$WORKBENCH/tools/${flow}.json"
  echo "--- lint $flow ---"
  node bin/flow.mjs lint "$spec" --var "url=$URL" --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const j=JSON.parse(s);console.log("ok:",j.ok,"steps:",j.summary.steps,j.errors.length?"errors: "+j.errors.join("; "):"")})'
  echo "--- run  $flow ---"
  node bin/flow.mjs run "$spec" --var "url=$URL" --run-id "${flow}-$(date +%s)" --no-canary --json \
    | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const j=JSON.parse(s);const l=j.ledger||j;const f=(l.steps||[]).find(x=>x.status==="failed");console.log("outcome:",l.outcome,"| steps:",(l.steps||[]).length,"| ms:",l.durationMs,f?"\n  失败步: "+f.id+" "+f.class+"\n  "+String(f.message||"").split("\n")[0]:"");process.exit(l.outcome==="ok"?0:1)})'
done

echo
echo "两条 Flow 流程均通过。产物在 \$FLOW_HOME/runs/<run-id>/（product.json 是抽取到的真实 SRT）。"
