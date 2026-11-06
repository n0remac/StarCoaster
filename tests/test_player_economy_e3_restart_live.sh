#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/player-economy-e3-restart-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/native" "$run_dir/park"
cp tests/economy_e3_client_probe.js "$run_dir/client/plugin/probe.js"
read -r OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT < <(
  python3 - <<'PY'
import socket
socks=[]
for _ in range(4):
    sock=socket.socket(); sock.bind(('127.0.0.1', 0)); socks.append(sock)
print(*(sock.getsockname()[1] for sock in socks))
PY
)
export OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT
display=""
for display_number in {94..110}; do
  if [[ ! -e "/tmp/.X11-unix/X$display_number" ]]; then display=":$display_number"; break; fi
done
test -n "$display"
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
export DISPLAY="$display" BRIDGE_FRAME_MS=15 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=1
export BRIDGE_RUNTIME_DIR="$run_dir/native" BRIDGE_SERVER_DATA_DIR="$run_dir/park"
export BRIDGE_CLIENT_DATA_DIR="$run_dir/client" BRIDGE_CLIENT_LOG_FILE="$run_dir/client.log"
export BRIDGE_TEST_BRIDGE_PID_FILE="$run_dir/bridge.pid" BRIDGE_SPAWN_JOURNAL="$run_dir/spawn-queue.json"
timeout 300s python3 scripts/play-scenario.py economy-e3 > "$run_dir/session.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" start=$SECONDS
  until grep -qE "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - start >= limit )); then echo "timeout: $pattern; evidence $run_dir" >&2; return 1; fi
    if ! kill -0 "$session_pid" 2>/dev/null; then echo "session ended: $pattern; evidence $run_dir" >&2; return 1; fi
    sleep 0.2
  done
}
wait_for 'verb=unit\.build accepted=1' "$run_dir/session.log" 180
original_pid="$(cat "$run_dir/bridge.pid")"
kill "$original_pid"
sleep 1
build/world-bridge --park "127.0.0.1:$STARCOASTER_BRIDGE_PORT" \
  --openbw "127.0.0.1:$BRIDGE_OPENBW_PORT" --controller "127.0.0.1:$BRIDGE_CONTROLLER_PORT" \
  --scenario scenarios/economy-e3/scenario.json --rules scenarios/economy-e3/mapping.json \
  --spawn-journal "$run_dir/spawn-queue.json" > "$run_dir/restarted-bridge.log" 2>&1 &
restarted_pid=$!
printf 'original_pid=%s restarted_pid=%s\n' "$original_pid" "$restarted_pid" > "$run_dir/bridge-restart.txt"
wait_for 'construction completed intent=build:1:93100' "$run_dir/restarted-bridge.log" 110
python3 - "$run_dir" <<'PY'
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
first = (root / 'session.log').read_text(errors='replace')
restart = (root / 'restarted-bridge.log').read_text(errors='replace')
journals = list(root.glob('spawn-queue.json.construction-*.json'))
assert len(journals) == 1, journals
intents = json.loads(journals[0].read_text())['intents']
assert len(intents) == 1, intents
intent = intents['build:1:93100']
assert intent['state'] == 'completed' and intent['native_id'] and intent['projection_id'], intent
assert 'minerals=4900 gas=5000' in first + restart
assert 'minerals=4800 gas=5000' not in first + restart
assert (first + restart).count('construction bound intent=build:1:93100') <= 1
print('restart_in_flight: PASS')
print('single_native_build: PASS')
print('single_native_debit: PASS')
PY
scrot -z "$run_dir/native-client.png" 2> "$run_dir/scrot.log"
echo "E3 restart evidence: $run_dir"
