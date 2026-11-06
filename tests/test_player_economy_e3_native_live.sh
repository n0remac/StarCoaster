#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/player-economy-e3-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/native" "$run_dir/park"
cp "${E3_CLIENT_PROBE:-tests/economy_e3_client_probe.js}" "$run_dir/client/plugin/economy_e3_client_probe.js"
read -r OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT < <(
  python3 - <<'PY'
import socket
socks = []
for _ in range(4):
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); socks.append(sock)
print(*(sock.getsockname()[1] for sock in socks))
PY
)
export OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT
display=""
for display_number in {94..110}; do
  if [[ ! -e "/tmp/.X11-unix/X$display_number" ]]; then display=":$display_number"; break; fi
done
if [[ -z "$display" ]]; then echo "no isolated X display is available" >&2; exit 1; fi
Xvfb "$display" -screen 0 1280x800x24 > "$run_dir/xvfb.log" 2>&1 &
xvfb_pid=$!
session_pid=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
  kill "$xvfb_pid" 2>/dev/null || true; wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
export DISPLAY="$display"
export BRIDGE_FRAME_MS=10 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=1
export BRIDGE_RUNTIME_DIR="$run_dir/native" BRIDGE_SERVER_DATA_DIR="$run_dir/park"
export BRIDGE_CLIENT_DATA_DIR="$run_dir/client" BRIDGE_CLIENT_LOG_FILE="$run_dir/client.log"
export BRIDGE_TEST_BRIDGE_PID_FILE="$run_dir/bridge.pid"
export BRIDGE_SPAWN_JOURNAL="$run_dir/spawn-queue.json"
timeout 240s python3 scripts/play-scenario.py economy-e3 > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
wait_pattern="${E3_WAIT_PATTERN:-WORLD_PATCH_SYNC revision=2}"
until grep -qE "$wait_pattern" "$run_dir/session.log" 2>/dev/null; do
  if (( SECONDS - start >= 200 )); then echo "timeout: $wait_pattern; evidence $run_dir" >&2; exit 1; fi
  if ! kill -0 "$session_pid" 2>/dev/null; then echo "session exited; evidence $run_dir" >&2; exit 1; fi
  sleep 2
done
scrot -z "$run_dir/native-client.png" 2> "$run_dir/scrot.log"
echo "E3 native evidence: $run_dir"
