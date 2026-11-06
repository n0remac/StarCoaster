#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
test -s build/wasm-client/manifest.json || { echo 'build WASM bundle first' >&2; exit 1; }
run_dir="$project_dir/run-data/player-economy-e2-browser-$(date +%s)"
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
WASM_PORT="${WASM_E2_WASM_PORT:-$WASM_PORT}"
export BRIDGE_FRAME_MS=10 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0
export BRIDGE_RUNTIME_DIR="$run_dir/native" BRIDGE_SERVER_DATA_DIR="$run_dir/park"
export BRIDGE_SPAWN_JOURNAL="$run_dir/spawn-queue.json" BRIDGE_SERVE_WASM=0
session_pid=""; wasm_pid=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$wasm_pid" ]]; then kill "$wasm_pid" 2>/dev/null || true; wait "$wasm_pid" 2>/dev/null || true; fi
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
timeout 1800s python3 scripts/play-scenario.py economy-e3 > "$run_dir/session.log" 2>&1 &
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
WASM_LIVE_PROFILE="${WASM_E2_PROFILE:-$run_dir/browser/profile}" \
WASM_PERF_ARTIFACTS="$run_dir/browser" \
WASM_ECONOMY_E2_PROBE=1 WASM_LIVE_DURATION_MS=240000 \
WASM_LIVE_BOOT_TIMEOUT_MS=600000 WASM_LIVE_CAMERA_TIMEOUT_MS=900000 \
node browser/live-test.mjs > "$run_dir/browser.log" 2>&1
python3 - "$run_dir" <<'PY'
from pathlib import Path
import json, re, sys
root = Path(sys.argv[1])
host = (root / 'session.log').read_text(errors='replace')
browser = (root / 'browser.log').read_text(errors='replace')
runtime = json.loads((root / 'browser/runtime.json').read_text())
checks = {
    'browser_pass': runtime['outcome'] == 'passed',
    'browser_mineral_order': 'ECONOMY_E2_ORDER request=93501 verb=gather accepted=true' in browser,
    'browser_gas_order': 'ECONOMY_E2_ORDER request=93505 verb=gather accepted=true' in browser,
    'browser_trained': 'ECONOMY_E2_TRAINED workers=5' in browser,
    'browser_reconnect_capture': (root / 'browser/economy-e2-reconnect.png').is_file(),
    'native_mineral_and_gas_orders': len(re.findall(r'verb=unit\.gather accepted=1', host)) >= 3,
    'native_mineral_delivery': bool(re.search(r'player resources owner=1 minerals=50(08|16|24)', host)),
    'native_gas_delivery': bool(re.search(r'player resources owner=1 minerals=\d+ gas=50(08|16|24)', host)),
    'native_refinery': 'construction bound intent=build:' in host and 'type=terran_refinery' in host,
    'native_train': bool(re.search(r'train command=.*unit_type=terran_scv', host)),
    'confirmed_revision': "WORLD_PATCH_SYNC revision=2" in host,
}
for name, passed in checks.items():
    print(f'{name}: {"PASS" if passed else "FAIL"}')
if not all(checks.values()):
    raise SystemExit(1)
PY
echo "E2 browser evidence: $run_dir"
