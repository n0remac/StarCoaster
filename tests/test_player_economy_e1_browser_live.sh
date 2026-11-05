#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
test -s build/wasm-client/manifest.json || { echo 'build E1 WASM bundle first' >&2; exit 1; }
run_dir="$project_dir/run-data/player-economy-e1-browser-$(date +%s)"
mkdir -p "$run_dir/native" "$run_dir/park" "$run_dir/browser"
read -r OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT WASM_PORT < <(
  python3 - <<'PY'
import socket
socks=[]
for _ in range(5):
    sock=socket.socket(); sock.bind(('127.0.0.1', 0)); socks.append(sock)
print(*(sock.getsockname()[1] for sock in socks))
PY
)
export OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT
WASM_PORT="${WASM_E1_WASM_PORT:-$WASM_PORT}"
export BRIDGE_FRAME_MS=10 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0
export BRIDGE_RUNTIME_DIR="$run_dir/native" BRIDGE_SERVER_DATA_DIR="$run_dir/park"
export BRIDGE_SPAWN_JOURNAL="$run_dir/spawn-queue.json"
export BRIDGE_SERVE_WASM=0
session_pid=""; wasm_pid=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$wasm_pid" ]]; then kill "$wasm_pid" 2>/dev/null || true; wait "$wasm_pid" 2>/dev/null || true; fi
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
timeout 1200s python3 scripts/play-scenario.py economy-e1 > "$run_dir/session.log" 2>&1 &
session_pid=$!
build/wasm-server --bundle "$project_dir/build/wasm-client" \
  --listen "127.0.0.1:$WASM_PORT" --native "127.0.0.1:$OPENRCT2_PORT" \
  --rct2-data-path "$RCT2_DATA_DIR" > "$run_dir/wasm-server.log" 2>&1 &
wasm_pid=$!
start=$SECONDS
until curl --fail --silent "http://127.0.0.1:$WASM_PORT/" >/dev/null; do
  if ! kill -0 "$wasm_pid" 2>/dev/null; then echo "WASM server exited; evidence $run_dir" >&2; exit 1; fi
  if (( SECONDS - start >= 240 )); then echo "WASM server did not start; evidence $run_dir" >&2; exit 1; fi
  sleep 1
done
WASM_LIVE_URL="http://127.0.0.1:$WASM_PORT/" \
WASM_LIVE_PROFILE="${WASM_E1_PROFILE:-$run_dir/browser/profile}" \
WASM_PERF_ARTIFACTS="$run_dir/browser" \
WASM_ECONOMY_E1_PROBE=1 WASM_LIVE_DURATION_MS=120000 \
WASM_LIVE_BOOT_TIMEOUT_MS=600000 WASM_LIVE_CAMERA_TIMEOUT_MS=900000 \
node browser/live-test.mjs > "$run_dir/browser.log" 2>&1
python3 tests/verify_player_economy_e1_browser.py "$run_dir"
echo "E1 browser evidence: $run_dir"
