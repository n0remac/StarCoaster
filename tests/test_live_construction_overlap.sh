#!/usr/bin/env bash
# Opt-in occupied construction and recovery check.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"; test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-overlap-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js scripts/live-overlap-probe.js "$run_dir/client/plugin/"
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 115s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
wait_for 'LIVE_OVERLAP_COMPLETE|LIVE_OVERLAP_ERROR' "$run_dir/client.log" 75
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / 'server.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
build = re.search(r'LIVE_OVERLAP_BUILD accepted=true marine_x=(\d+) marine_y=(\d+)', client)
final = re.search(r'LIVE_OVERLAP_COMPLETE x=(\d+) y=(\d+) actors=([^\n\r\']+)', client)
failed = re.search(r'park patch unsynchronized id=(\S+) revision=2 reason=(?:publisher|controller):occupied_construction_geometry', server)
checks = {
    'ordinary_wall_action_on_actor': bool(build) and abs(int(build.group(1)) - 640) <= 4,
    'native_occupancy_detected': 'occupied_construction_geometry' in server,
    'no_false_patch_confirmation': bool(failed) and
        not re.search(r'park patch synchronized id=' + re.escape(failed.group(1)) + r'\b', server),
    'wall_removed': 'LIVE_OVERLAP_REMOVE accepted=true' in client,
    'actor_not_teleported': bool(build) and bool(final)
        and abs(int(final.group(1)) - int(build.group(1))) < 32,
    'recovered_after_removal': server.count('WORLD_READY entities=') >= 2,
}
result = {'checks': checks, 'build_position': build.groups() if build else None,
          'final_position': final.groups()[:2] if final else None}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Live overlap logs: %s\n' "$run_dir"
