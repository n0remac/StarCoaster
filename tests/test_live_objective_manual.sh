#!/usr/bin/env bash
# Ordinary objective demolition must produce a distinct durable defeat.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$park_file"
run_dir="$project_dir/run-data/live-objective-manual-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/server-data/plugin"
map_file="$run_dir/frontier-outpost.scm"
python3 scripts/create-world-base-map.py \
  --scenario "$project_dir/scenarios/frontier-outpost/scenario.json" --output "$map_file"
cp openrct2-plugin/rts-bridge.js scripts/live-objective-removal-probe.js "$run_dir/client/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
session_pid=""; client_pid=""
cleanup() {
  for pid in "$client_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/frontier-outpost/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost/mapping.json" \
  BRIDGE_SPAWN_JOURNAL="$run_dir/spawn.json" BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 90s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then
      printf 'Session stopped before %s\n' "$pattern" >&2
      return 1
    fi
    sleep 1
  done
}
wait_for 'WORLD_READY' "$run_dir/server.log" 70
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'LIVE_OBJECTIVE_COMPLETE|LIVE_OBJECTIVE_ERROR' "$run_dir/client.log" 45
python3 - "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / 'server.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
journal = json.loads((directory / 'spawn.json.scenario.json').read_text())
checks = {
    'ordinary_demolition': 'LIVE_OBJECTIVE_MANUAL_REMOVE accepted=true' in client
        and 'LIVE_OBJECTIVE_COMPLETE ride_present=false' in client,
    'manual_removal_synchronized': 'park patch synchronized id=' in server,
    'distinct_manual_history': journal.get('objective_removed') is True
        and not journal.get('objective_destroyed', False),
    'scenario_defeat': journal.get('outcome') == 'defeat'
        and 'scenario objective removed manually' in server,
    'no_combat_destruction': 'WORLD_REMOVAL id=openrct2:ride:0#1 state=confirmed' not in server,
}
result = {'checks': checks, 'journal': {key: journal.get(key) for key in
          ('objective_removed', 'objective_destroyed', 'outcome')}}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Manual objective logs: %s\n' "$run_dir"
