#!/usr/bin/env bash
# Opt-in two-client native five-Marine spawn through the synchronized OpenRCT2 action.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="${PARK_FILE:-$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park}"
test -f "$park_file"
run_dir="$project_dir/run-data/unit-spawn-live-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin"
python3 scripts/create-world-base-map.py --output "$run_dir/world-live.scm" --scenario scenarios/frontier-outpost.json
cp scripts/world-spawn-probe.js "$run_dir/client-a/plugin/"
cp scripts/world-actor-observer.js "$run_dir/client-b/plugin/"
for client in client-a client-b; do
  { printf 'var STARCOASTER_WORLD_BRIDGE = true;\n'; cat openrct2-plugin/rts-bridge.js; } \
    > "$run_dir/$client/plugin/rts-bridge.js"
done
session_pid=""; client_a_pid=""; client_b_pid=""
cleanup() {
  for pid in "$client_a_pid" "$client_b_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_a_pid" "$client_b_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
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
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client-a" > "$run_dir/client-a.log" 2>&1 &
client_a_pid=$!
wait_for 'WORLD_SPAWN_ROSTER count=6' "$run_dir/client-a.log" 60
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client-b" > "$run_dir/client-b.log" 2>&1 &
client_b_pid=$!
wait_for 'WORLD_SPAWN_REQUEST accepted=true' "$run_dir/client-a.log" 60
wait_for 'WORLD_SPAWN_SQUAD ids=' "$run_dir/client-a.log" 90
wait_for 'WORLD_ACTOR_ROSTER count=11' "$run_dir/client-b.log" 90
wait_for 'WORLD_SPAWN_MOVE accepted=true' "$run_dir/client-a.log" 60
wait_for 'WORLD_SPAWN_ATTACK accepted=true' "$run_dir/client-a.log" 60
python3 - "$run_dir" <<'PY'
import re
import sys
from pathlib import Path
root = Path(sys.argv[1])
server = (root / 'session.log').read_text(errors='replace')
expected = {f'openbw:{i}' for i in range(3001, 3006)}
for name, prefix in (('client-a', 'WORLD_SPAWN_ROSTER'), ('client-b', 'WORLD_ACTOR_ROSTER')):
    log = (root / (name + '.log')).read_text(errors='replace')
    matches = re.findall(prefix + r' count=(\d+) ids=([a-z0-9:,]+)', log)
    rosters = [set(ids.split(',')) for count, ids in matches if int(count) == 11]
    if not any(expected <= roster and len(roster) == 11 for roster in rosters):
        raise SystemExit(f'{name} did not display eleven unique Marines')
for actor in expected:
    if server.count('actor-spawn id=' + actor) != 1 or not re.search(
            r'actor-bound id=' + actor + r' native=\d+', server):
        raise SystemExit(f'missing unique publisher/controller creation for {actor}')
if len(re.findall(r'native spawn issued request=[^ ]+ index=[0-4] type=terran_marine', server)) != 5:
    raise SystemExit('five sequential native Marine creations were not issued')
orders = re.findall(r'\[world-control\] command=[^ ]+ unit=(\d+) verb=(unit\.move|unit\.attack) accepted=1', server)
for verb in ('unit.move', 'unit.attack'):
    if len({native for native, order in orders if order == verb}) != 5:
        raise SystemExit(f'five native Marine {verb} commands were not accepted')
print('UNIT_SPAWN_LIVE_PASS five native Marines and two matching eleven-Marine clients')
PY
printf 'Logs: %s\n' "$run_dir"
