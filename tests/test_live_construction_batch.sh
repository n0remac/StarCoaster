#!/usr/bin/env bash
# Opt-in synchronized multi-action construction batch check.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"; test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-batch-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js scripts/live-batch-probe.js "$run_dir/client/plugin/"
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
wait_for 'LIVE_BATCH_COMPLETE|LIVE_BATCH_ERROR' "$run_dir/client.log" 60
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / 'server.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
actions = re.findall(r'LIVE_BATCH_ACTION index=(\d+) kind=(\w+) accepted=(\w+)', client)
changes = re.findall(r'WORLD_CHANGESET (\{[^\n]+\})', server)
patches = re.findall(r'park patch synchronized id=', server)
metrics = re.findall(r'WORLD_PATCH_METRIC patch=([^ ]+) action_to_detection_ms=(-?\d+) detection_to_patch_ms=(\d+)(?: payload_bytes=\d+)? operations=(\d+)', server)
checks = {
    'six_ordinary_actions': len(actions) == 6 and all(state == 'true' for _, _, state in actions),
    'path_wall_scenery_discovered': any(
        {'footpath', 'wall', 'small_scenery'} <= {
            item.split(':')[1] for item in json.loads(change)['additions']}
        for change in changes),
    'batched_native_update': len(patches) == 1,
    'performance_recorded': bool(metrics) and int(metrics[0][1]) >= 0,
}
result = {'checks': checks, 'actions': actions, 'patches': len(patches), 'metrics': metrics}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Live batch logs: %s\n' "$run_dir"
