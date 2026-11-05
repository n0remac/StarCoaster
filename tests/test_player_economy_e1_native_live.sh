#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/player-economy-e1-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/native" "$run_dir/park"
cp tests/economy_e1_client_probe.js "$run_dir/client/plugin/economy_e1_client_probe.js"
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
session_pid=""; restarted_pid=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$restarted_pid" ]]; then kill "$restarted_pid" 2>/dev/null || true; wait "$restarted_pid" 2>/dev/null || true; fi
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
timeout 270s python3 scripts/play-scenario.py economy-e1 > "$run_dir/session.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" start=$SECONDS
  until grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - start >= limit )); then echo "timeout: $pattern; evidence $run_dir" >&2; return 1; fi
    if ! kill -0 "$session_pid" 2>/dev/null; then echo "session exited: $pattern; evidence $run_dir" >&2; return 1; fi
    sleep 1
  done
}
wait_for 'ECONOMY_E1_TRAIN_COMPLETE workers=5' "$run_dir/client.log" 180
scrot -z "$run_dir/native-client.png" 2> "$run_dir/scrot.log"
original_pid="$(cat "$run_dir/bridge.pid")"
kill "$original_pid"
sleep 3
build/world-bridge --park "127.0.0.1:$STARCOASTER_BRIDGE_PORT" \
  --openbw "127.0.0.1:$BRIDGE_OPENBW_PORT" \
  --controller "127.0.0.1:$BRIDGE_CONTROLLER_PORT" \
  --scenario scenarios/economy-e1/scenario.json --rules scenarios/economy-e1/mapping.json \
  --spawn-journal "$run_dir/spawn-queue.json" > "$run_dir/restarted-bridge.log" 2>&1 &
restarted_pid=$!
printf 'original_pid=%s restarted_pid=%s\n' "$original_pid" "$restarted_pid" > "$run_dir/bridge-restart.txt"
start=$SECONDS
until grep -q 'resource site=geyser ' "$run_dir/restarted-bridge.log" 2>/dev/null; do
  if ! kill -0 "$restarted_pid" 2>/dev/null; then
    echo "restarted bridge exited; evidence $run_dir/restarted-bridge.log" >&2; exit 1
  fi
  if (( SECONDS - start >= 90 )); then echo "timeout: resource reconnect; evidence $run_dir" >&2; exit 1; fi
  sleep 1
done
python3 tests/verify_player_economy_e1_native.py "$run_dir"
echo "E1 native evidence: $run_dir"
