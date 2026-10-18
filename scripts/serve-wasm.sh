#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
go_bin="$(command -v go || true)"
go_bin="${go_bin:-/usr/local/go/bin/go}"
export GOCACHE="${GOCACHE:-$project_dir/build/go-cache}"
"$go_bin" build -o build/wasm-server ./cmd/wasm-server
exec build/wasm-server "$@"
