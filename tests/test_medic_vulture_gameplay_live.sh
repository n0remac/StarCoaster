#!/usr/bin/env bash
# Two-client construction, native production, and mixed-unit controls.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
run_dir="$project_dir/run-data/medic-vulture-gameplay-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
cp scripts/live-medic-vulture-probe.js openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
  --output "$map_file" >/dev/null
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
  timeout 200s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
started=$SECONDS
until grep -q 'WORLD_READY' "$run_dir/server.log" 2>/dev/null; do
  if (( SECONDS - started > 75 )); then echo "World not ready: $run_dir" >&2; exit 1; fi
  sleep 1
done
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
started=$SECONDS
until grep -q 'NEXT_PROBE_AFTER_DEPOT' "$run_dir/client.log" 2>/dev/null; do
  if (( SECONDS - started > 155 )); then echo "Gameplay probe timed out: $run_dir" >&2; exit 1; fi
  sleep 1
done
sleep 3
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1])
server = (run / 'server.log').read_text(errors='replace')
client = (run / 'client.log').read_text(errors='replace')
train = re.findall(r'\[world-control\] train command=\S+ barracks=\d+ accepted=(\d).*?'
                   r'minerals=(\d+).*?unit_type=(terran_medic|terran_vulture) gas=(\d+)', server)
ids = re.search(r'NEXT_PROBE_ACTORS ids=(openbw:\d+,openbw:\d+,openbw:\d+)', client)
checks = {
    'four_park_buildings': all(f'NEXT_PROBE_PLACE type={kind} accepted=true' in client
        for kind in ('terran_barracks', 'terran_factory', 'terran_supply_depot', 'terran_academy')),
    'four_native_buildings': all(f'type={kind} hp={hp}' in server
        for kind, hp in (('Terran_Barracks',1000), ('Terran_Factory',1250),
                         ('Terran_Supply_Depot',500), ('Terran_Academy',600))),
    'ordered_revisions': all(f'WORLD_PATCH_SYNC revision={revision}' in server
        for revision in range(2, 8)),
    'medic_prerequisite': any(row[0]=='0' and row[2]=='terran_medic' for row in train),
    'native_training': any(row[0]=='1' and row[2]=='terran_medic' for row in train)
        and any(row[0]=='1' and row[2]=='terran_vulture' for row in train),
    'native_charges': any(row[1:]==('450','terran_medic','225') for row in train)
        and any(row[1:]==('375','terran_vulture','225') for row in train),
    'player_depot_adds_native_supply': bool(re.search(
        r'train command=.*supply=\d+/32.*unit_type=terran_vulture', server)),
    'duplicate_no_charge': 'NEXT_PROBE_DUPLICATE' in client
        and sum(row[0]=='1' and row[2]=='terran_medic' for row in train)==1,
    'actor_bindings': bool(ids) and all(
        'actor binding id='+actor+' participant='+role in server
        for actor in ids.group(1).split(',')[:2] for role in ('publisher','controller')),
    'mixed_order': 'NEXT_PROBE_MIXED_MOVE accepted=true' in client,
    'academy_and_depot_retired': all(
        (match := re.search(r'NEXT_PROBE_PLACE type='+kind+
                            r' accepted=true id=(openrct2:[A-Za-z0-9:_-]+#[0-9]+)', client))
        and 'target retired id='+match[1] in server
        for kind in ('terran_academy','terran_supply_depot'))
        and 'NEXT_PROBE_ACADEMY_REMOVE accepted=true' in client
        and 'NEXT_PROBE_DEPOT_REMOVE accepted=true' in client,
    'medic_relocked_after_academy_loss': [row for row in train if row[2]=='terran_medic'][-1]
        == ('0','375','terran_medic','225'),
    'depot_loss_restores_native_supply_limit': bool(re.search(
        r'train command=.*accepted=0.*minerals=375 supply=16/16.*unit_type=terran_vulture gas=225', server)),
    'two_client_sync': 'WORLD_PATCH_SYNC revision=7' in server
        and not re.search(r'\b(shared-state mismatch|native.*diverge)\b', server, re.I),
}
(run / 'verification.json').write_text(json.dumps({'checks':checks,'train':train},indent=2)+'\n')
print(json.dumps(checks,indent=2)); print(f'Gameplay evidence: {run}')
if not all(checks.values()): raise SystemExit(1)
PY
