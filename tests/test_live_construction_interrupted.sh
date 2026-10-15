#!/usr/bin/env bash
# Restart only the Go bridge after a construction mask is scheduled.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"
test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-interrupted-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-a/plugin/"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-b/plugin/"
cp scripts/live-construction-probe.js "$run_dir/client-a/plugin/"
cp scripts/live-construction-observer.js "$run_dir/client-b/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost/mapping.json" \
  BRIDGE_SPAWN_JOURNAL="$run_dir/spawn.json" BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 150s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
    sleep 0.1
  done
}
wait_for 'WORLD_READY' "$run_dir/server.log" 70
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
for name in client-a client-b; do
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$run_dir/$name" > "$run_dir/$name.log" 2>&1 &
  if [[ "$name" == client-a ]]; then client_a_pid=$!; else client_b_pid=$!; fi
done
wait_for 'LIVE_CONSTRUCTION_ACTORS initial=' "$run_dir/client-a.log" 45
wait_for 'park patch scheduled id=.*:patch:1' "$run_dir/server.log" 35
original_bridge_pid="$(ps -eo pid,args | awk '$2 ~ /\/build\/world-bridge$/ { print $1; exit }')"
test -n "$original_bridge_pid"
kill "$original_bridge_pid"
for attempt in $(seq 1 50); do
  if ! kill -0 "$original_bridge_pid" 2>/dev/null; then break; fi
  sleep 0.1
done
build/world-bridge --rules "$project_dir/scenarios/frontier-outpost/mapping.json" \
  --spawn-journal "$run_dir/spawn.json" > "$run_dir/bridge-restart.log" 2>&1 &
bridge_restart_pid=$!
wait_for 'park snapshot session=' "$run_dir/bridge-restart.log" 60
wait_for 'OpenBW ready targets=' "$run_dir/bridge-restart.log" 60
wait_for 'LIVE_CONSTRUCTION_COMPLETE|LIVE_CONSTRUCTION_ERROR' "$run_dir/client-a.log" 110
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
before = (directory / 'server.log').read_text(errors='replace')
after = (directory / 'bridge-restart.log').read_text(errors='replace')
driver = (directory / 'client-a.log').read_text(errors='replace')
observer = (directory / 'client-b.log').read_text(errors='replace')
identities = re.findall(r'LIVE_CONSTRUCTION_ACTORS (?:initial|final)=([^\'\r\n]+)', driver)
native = before + '\n' + after
publisher = re.findall(r'\[world\] navigation-mask hash=([0-9a-f]{16}).*accepted=1', native)
controller = re.findall(r'\[world-control\] navigation-mask hash=([0-9a-f]{16}).*accepted=1', native)
confirmed = re.findall(r'park patch synchronized id=\S+ revision=\d+ hash=([0-9a-f]{16})', after)
checks = {
    'scheduled_patch_interrupted': 'park patch scheduled id=' in before
        and 'park patch synchronized id=' not in before,
    'authoritative_snapshot_recovered': 'park snapshot session=' in after
        and 'OpenBW ready targets=' in after,
    'ordinary_wall_lifecycle_continued': 'LIVE_CONSTRUCTION_BUILD accepted=true' in driver
        and 'LIVE_CONSTRUCTION_REMOVE accepted=true' in driver,
    'later_revision_synchronized': 'park patch synchronized id=' in after,
    'both_native_masks_agree': bool(publisher) and bool(controller) and bool(confirmed)
        and publisher[-1] == controller[-1] == confirmed[-1],
    'actors_preserved': len(identities) >= 2 and identities[0] == identities[-1],
    'second_client_observed': 'LIVE_OBSERVER_WALL present=true' in observer
        and 'LIVE_OBSERVER_WALL present=false' in observer,
    'native_movement_completed': 'LIVE_CONSTRUCTION_COMPLETE' in driver,
}
result = {'checks': checks, 'initial_and_final_actors': identities}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Interrupted update logs: %s\n' "$run_dir"
