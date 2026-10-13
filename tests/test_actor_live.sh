#!/usr/bin/env bash
# Opt-in native actor lifecycle test. Requires licensed RCT2 and StarCraft data.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="${PARK_FILE:-$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park}"
test -f "$park_file"
run_dir="$project_dir/run-data/actor-live-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin"
python3 scripts/create-world-base-map.py --output "$run_dir/world-live.scm" --scenario scenarios/frontier-outpost.json
if [[ "${BRIDGE_ACTOR_TEST_RESTART:-0}" == 1 ]]; then
  { printf 'var STARCOASTER_ACTOR_ATTACK_DELAY = 600;\n'; cat scripts/world-actor-probe.js; } \
    > "$run_dir/client-a/plugin/world-actor-probe.js"
else
  cp scripts/world-actor-probe.js "$run_dir/client-a/plugin/"
fi
cp scripts/world-actor-observer.js "$run_dir/client-b/plugin/"
for client in client-a client-b; do
  {
    printf 'var STARCOASTER_WORLD_BRIDGE = true;\n'
    cat openrct2-plugin/rts-bridge.js
  } > "$run_dir/$client/plugin/rts-bridge.js"
done
session_pid=""; client_a_pid=""; client_b_pid=""; bridge_restart_pid=""
cleanup() {
  for pid in "$client_a_pid" "$client_b_pid" "$bridge_restart_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_a_pid" "$client_b_pid" "$bridge_restart_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_SPAWN_MARINE_FRAME="${BRIDGE_ACTOR_SPAWN_FRAME:-180}" BRIDGE_TEST_KILL_MARINE_FRAME="${BRIDGE_ACTOR_KILL_FRAME:-1300}" \
  BRIDGE_MAX_TARGETS=32 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_MAP_FILE="$run_dir/world-live.scm" \
  timeout 180s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! rg -q "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then
      printf 'World session stopped before %s\n' "$pattern" >&2
      return 1
    fi
    sleep 1
  done
}
wait_for 'WORLD_READY' "$run_dir/session.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
for name in client-a client-b; do
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$run_dir/$name" > "$run_dir/$name.log" 2>&1 &
  if [[ "$name" == client-a ]]; then client_a_pid=$!; else client_b_pid=$!; fi
  if [[ "$name" == client-a ]]; then
    wait_for 'WORLD_ACTOR_PROBE state=' "$run_dir/client-a.log" 60
  fi
done
wait_for 'actor-spawn id=openbw:3001' "$run_dir/session.log" 75
wait_for 'actor-bound id=openbw:3001' "$run_dir/session.log" 75
wait_for 'WORLD_ACTOR_PROBE state=active' "$run_dir/client-a.log" 90
wait_for 'WORLD_ACTOR_PROBE state=active' "$run_dir/client-b.log" 90
wait_for 'WORLD_ACTOR_MOVE_QUERY accepted=true' "$run_dir/client-a.log" 60
if [[ "${BRIDGE_ACTOR_TEST_RESTART:-0}" == 1 ]]; then
  before_snapshots="$(rg -c 'RTS Bridge apply tick=' "$run_dir/client-a.log" || true)"
  original_bridge_pid="$(ps -eo pid,args | awk '$2 ~ /\/build\/world-bridge$/ { print $1; exit }')"
  test -n "$original_bridge_pid"
  kill "$original_bridge_pid"
  for attempt in $(seq 1 50); do
    if ! kill -0 "$original_bridge_pid" 2>/dev/null; then break; fi
    sleep 0.1
  done
  build/world-bridge --scenario scenarios/frontier-outpost.json \
    --rules scenarios/frontier-outpost-mapping.json > "$run_dir/bridge-restart.log" 2>&1 &
  bridge_restart_pid=$!
  wait_for 'actor reconcile living=1' "$run_dir/bridge-restart.log" 60
  wait_for 'actor binding id=openbw:3001 participant=controller.*active=true' \
    "$run_dir/bridge-restart.log" 60
  resumed=0
  for attempt in $(seq 1 60); do
    now="$(rg -c 'RTS Bridge apply tick=' "$run_dir/client-a.log" || true)"
    if (( now > before_snapshots )); then resumed=1; break; fi
    sleep 1
  done
  test "$resumed" == 1 || { printf 'Client A snapshots did not resume after bridge restart\n' >&2; exit 1; }
  kill "$client_b_pid"
  wait "$client_b_pid" 2>/dev/null || true
  mv "$run_dir/client-b.log" "$run_dir/client-b-before-reconnect.log"
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$run_dir/client-b" > "$run_dir/client-b.log" 2>&1 &
  client_b_pid=$!
  wait_for 'WORLD_ACTOR_PROBE state=active count=1' "$run_dir/client-b.log" 60
fi
wait_for 'WORLD_ACTOR_ATTACK_QUERY accepted=true' "$run_dir/client-a.log" 60
wait_for 'actor-despawn id=openbw:3001' "$run_dir/session.log" 120
python3 - "$run_dir" <<'PY'
import re
import sys
import time
from pathlib import Path
root = Path(sys.argv[1])
limit = time.monotonic() + 30
while time.monotonic() < limit:
    states = []
    for client in ('client-a', 'client-b'):
        log = (root / (client + '.log')).read_text(errors='replace')
        states.append(re.findall(r'WORLD_ACTOR_PROBE state=(active|absent)', log))
    if all('active' in state and state[-1] == 'absent' for state in states):
        break
    time.sleep(1)
else:
    raise SystemExit(f'actor removal did not converge in both clients: {states}')
server = (root / 'session.log').read_text(errors='replace')
orders = re.findall(r'\[world-control\] command=[^\s]+ unit=(\d+) verb=(unit\.move|unit\.attack) accepted=1', server)
if {verb for _, verb in orders} != {'unit.move', 'unit.attack'} or len({native for native, _ in orders}) != 1:
    raise SystemExit(f'native runtime Marine orders missing or inconsistent: {orders}')
print('ACTOR_LIVE_PASS both clients rendered and removed native openbw:3001; move and attack accepted')
PY
if [[ "${BRIDGE_ACTOR_TEST_RESTART:-0}" == 1 ]]; then
  printf 'ACTOR_RESTART_PASS bridge and client reconnected with one openbw:3001\n'
fi
printf 'Logs: %s\n' "$run_dir"
