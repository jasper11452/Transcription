#!/usr/bin/env bash
# 起一个只绑本机回环的静态服务。需要一个 http 源才能用 ES module。
set -euo pipefail
cd "$(dirname "$0")"
exec node tools/serve.js "$@"
