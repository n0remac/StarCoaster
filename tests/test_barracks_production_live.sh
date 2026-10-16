#!/usr/bin/env bash
# Licensed two-client test of genuine Barracks training and actor binding.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/barracks-production-live-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
cp scripts/live-barracks-build-probe.js scripts/live-barracks-training-probe.js \
  openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 110s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
start=$SECONDS
while ! grep -q 'WORLD_READY' "$run_dir/server.log" 2>/dev/null; do
  if (( SECONDS - start > 75 )); then echo "Timed out waiting for world.ready" >&2; exit 1; fi
  sleep 1
done
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
start=$SECONDS
while ! grep -q 'BARRACKS_TRAIN_PROBE_MARINE' "$run_dir/client.log" 2>/dev/null; do
  if (( SECONDS - start > 65 )); then echo "Timed out waiting for trained Marine" >&2; exit 1; fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
p = Path(sys.argv[1]); server = (p/'server.log').read_text(errors='replace'); client = (p/'client.log').read_text(errors='replace')
checks = {
  'constructed': 'BARRACKS_BUILD_PROBE_RESULT accepted=true' in client and 'WORLD_PATCH_SYNC revision=2' in server,
  'native_barracks': 'type=Terran_Barracks hp=1000' in server,
  'client_train_action': 'BARRACKS_TRAIN_PROBE_ACTION accepted=true' in client,
  'duplicate_did_not_train': 'BARRACKS_TRAIN_PROBE_DUPLICATE_ATTEMPT' in client
      and len(re.findall(r'\[world-control\] train command=', server)) == 1
      and len(re.findall(r'WORLD_COMMAND_ACTION id=\S+ request=101 ', server)) == 1,
  'native_train': bool(re.search(r'\[world-control\] train command=\S+ barracks=\d+ accepted=1 queue=1 minerals=450 supply=12/16', server)),
  'both_actor_bindings': 'actor binding id=openbw:3001 participant=publisher' in server and 'actor binding id=openbw:3001 participant=controller' in server,
  'completed_marine_visible': 'BARRACKS_TRAIN_PROBE_MARINE id=openbw:3001' in client,
  'movement_action': 'BARRACKS_TRAIN_PROBE_MOVE accepted=true' in client,
}
(p/'verification.json').write_text(json.dumps({'checks': checks}, indent=2)+'\n')
print(json.dumps({'checks': checks}, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Barracks production logs: %s\n' "$run_dir"
