#!/usr/bin/env bash
# Licensed two-native-participant regression for occupied Barracks rollback.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
overlap_building="${OVERLAP_BUILDING:-terran_barracks}"
case "$overlap_building" in
  terran_barracks) overlap_label="BARRACKS" ;;
  terran_academy) overlap_label="ACADEMY" ;;
  terran_supply_depot) overlap_label="SUPPLY_DEPOT" ;;
  terran_factory) overlap_label="FACTORY" ;;
  *) printf 'Unsupported overlap building: %s\n' "$overlap_building" >&2; exit 2 ;;
esac
map_file="$project_dir/run-data/scenarios/mt-zergling/map/mt-zergling.scm"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$map_file"; test -s "$park_file"
run_dir="$project_dir/run-data/${overlap_building#terran_}-overlap-live-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
printf 'var STARCOASTER_OVERLAP_BUILDING = "%s";\n' "$overlap_building" \
  > "$run_dir/client/plugin/live-barracks-overlap-probe.js"
cat scripts/live-barracks-overlap-probe.js \
  >> "$run_dir/client/plugin/live-barracks-overlap-probe.js"
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 145s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then return 1; fi
    sleep 1
  done
}
wait_for 'WORLD_READY' "$run_dir/server.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'WORLD_BARRACKS_ROLLBACK_COMPLETE' "$run_dir/server.log" 70
recovery_started=$SECONDS
while (( $(grep -c 'WORLD_READY.*targets=2' "$run_dir/server.log") < 2 )); do
  if (( SECONDS - recovery_started >= 50 )); then
    printf 'Timed out waiting for native recovery\n' >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" "$overlap_label" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
label = sys.argv[2]
server = (directory / 'server.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
snapshots = re.findall(r'WORLD_SNAPSHOT session=\S+ entities=(\d+)', server)
ready = re.findall(r'WORLD_READY entities=(\d+) targets=(\d+)', server)
hashes = re.findall(r'navigation initialized hash=([0-9a-f]{16})', server)
rejected = re.search(r'park patch unsynchronized id=(\S+) revision=2 '
                     r'reason=(?:publisher|controller):occupied_construction_geometry', server)
checks = {
    'client_placed_over_marine': label + '_OVERLAP_BUILD accepted=true' in client,
    'native_rejected': bool(rejected),
    'park_rolled_back': 'WORLD_BARRACKS_ROLLBACK_COMPLETE' in server,
    'no_false_confirmation': bool(rejected) and
        not re.search(r'park patch synchronized id=' + re.escape(rejected.group(1)) + r'\b', server),
    'clean_resnapshot': len(snapshots) >= 2 and snapshots[-1] == snapshots[0],
    'both_native_participants_ready': len(ready) >= 2 and ready[-1] == ready[0],
    'navigation_restored': len(hashes) >= 2 and hashes[-1] == hashes[0],
}
result = {'checks': checks, 'snapshots': snapshots, 'ready': ready, 'hashes': hashes}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf '%s overlap logs: %s\n' "$overlap_building" "$run_dir"
