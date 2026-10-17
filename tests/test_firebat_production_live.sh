#!/usr/bin/env bash
# Real park actions, native Academy dependency, production, and mixed control.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-production-live-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
cp scripts/live-firebat-gameplay-probe.js openrct2-plugin/rts-bridge.js \
  "$run_dir/client/plugin/"
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
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 BRIDGE_TEST_FIREBAT_GAMEPLAY=1 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 180s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
start=$SECONDS
until grep -q 'WORLD_READY' "$run_dir/server.log" 2>/dev/null; do
  if (( SECONDS - start > 75 )); then echo "Timed out waiting for world.ready: $run_dir" >&2; exit 1; fi
  sleep 1
done
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
start=$SECONDS
until grep -q 'FIREBAT_PROBE_AFTER_REMOVE' "$run_dir/client.log" 2>/dev/null; do
  if (( SECONDS - start > 145 )); then echo "Timed out waiting for Firebat gameplay: $run_dir" >&2; exit 1; fi
  sleep 1
done
sleep 3
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); server = (run / 'server.log').read_text(errors='replace'); client = (run / 'client.log').read_text(errors='replace')
train = re.findall(r'\[world-control\] train command=\S+ barracks=\d+ accepted=(\d).*?unit_type=terran_firebat gas=(\d+)', server)
actor_ids = re.search(r'FIREBAT_PROBE_ACTORS ids=((?:openbw:\d+,){4}openbw:\d+)', client)
lines = client.splitlines()
move_line = next((i for i, line in enumerate(lines) if 'FIREBAT_PROBE_MIXED_MOVE accepted=true' in line), -1)
snapshots_before = [line for line in lines[:move_line] if 'RTS Bridge apply tick=' in line] if move_line >= 0 else []
snapshots_after = [line for line in lines[move_line + 1:] if 'RTS Bridge apply tick=' in line] if move_line >= 0 else []
def position(line, actor_id):
    match = re.search(re.escape(actor_id) + r',(\d+),(\d+),', line)
    return tuple(map(int, match.groups())) if match else None
mixed_moved = bool(actor_ids and snapshots_before and snapshots_after) and all(
    (origin := position(snapshots_before[-1], actor_id)) is not None
    and any((later := position(line, actor_id)) is not None
            and abs(later[0] - origin[0]) + abs(later[1] - origin[1]) > 8
            for line in snapshots_after[:120])
    for actor_id in actor_ids.group(1).split(','))
checks = {
    'barracks_and_academy_park_actions': 'FIREBAT_PROBE_BARRACKS accepted=true' in client
        and 'FIREBAT_PROBE_ACADEMY accepted=true' in client,
    'native_academy': server.count('type=Terran_Academy hp=600') == 1,
    'native_prerequisite_changes': '"reason":"requires_building"' in server
        and '"reason":"ready"' in server,
    'native_train_before_and_after': len(train) >= 4 and train[0][0] == '0'
        and train[1] == ('1', '225') and train[2] == ('1', '200') and train[-1][0] == '0',
    'duplicate_request_no_extra_charge': 'FIREBAT_PROBE_DUPLICATE_ATTEMPT' in client
        and sum(accepted == '1' for accepted, _gas in train) == 2,
    'two_firebat_bindings': all('actor binding id=openbw:'+str(actor)
        +' participant='+role in server for actor in (3001, 3002)
        for role in ('publisher', 'controller')),
    'mixed_orders': 'FIREBAT_PROBE_MIXED_MOVE accepted=true' in client
        and 'FIREBAT_PROBE_REDIRECT accepted=true' in client
        and bool(re.search(r'FIREBAT_PROBE_ACTORS ids=openbw:\d+(,openbw:\d+){4}', client)),
    'all_five_moved_in_native_snapshots': mixed_moved,
    'academy_demolition': 'FIREBAT_PROBE_REMOVE accepted=true' in client
        and 'WORLD_PATCH_SYNC revision=4' in server,
}
(run / 'verification.json').write_text(json.dumps({'checks': checks, 'train': train}, indent=2) + '\n')
print(json.dumps(checks, indent=2)); print(f'Firebat gameplay evidence: {run}')
if not all(checks.values()): raise SystemExit(1)
PY
