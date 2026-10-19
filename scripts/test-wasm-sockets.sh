#!/usr/bin/env bash
# Test Emscripten POSIX socket behavior in Chromium against the fixed gateway.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
export TMPDIR="${TMPDIR:-$project_dir/build/tmp}"
mkdir -p "$TMPDIR"
if [[ -f build/emsdk/emsdk_env.sh ]]; then
    # shellcheck disable=SC1091
    source build/emsdk/emsdk_env.sh >/dev/null
fi
command -v emcc >/dev/null || { printf 'SKIP: Emscripten socket probe requires emcc\n'; exit 0; }
command -v chromium >/dev/null || { printf 'SKIP: Emscripten socket probe requires Chromium\n'; exit 0; }
if [[ ! -d browser/node_modules/playwright-core ]]; then
    npm ci --prefix browser --ignore-scripts --no-audit --no-fund
fi
go_bin="$(command -v go || true)"
go_bin="${go_bin:-/usr/local/go/bin/go}"
export GOCACHE="${GOCACHE:-$project_dir/build/go-cache}"
"$go_bin" build -o build/wasm-server ./cmd/wasm-server
mkdir -p build/wasm-socket-test
emcc tests/wasm_socket_probe.c -O0 -pthread \
    -s PTHREAD_POOL_SIZE=1 -s ALLOW_MEMORY_GROWTH=1 \
    -s MODULARIZE=1 -s EXPORT_NAME=SOCKET_PROBE \
    -o build/wasm-socket-test/socket-probe.js
node browser/test-socket.mjs
