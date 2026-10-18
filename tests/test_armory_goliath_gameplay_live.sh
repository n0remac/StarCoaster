#!/usr/bin/env bash
# Two-client Armory construction, native Goliath production, and shared controls.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
combat_armory="${STARCOASTER_TEST_ARMORY_COMBAT:-0}"
test_building_hp=""
if [[ "$combat_armory" == 1 ]]; then
  test_building_hp="terran_armory=35"
  run_dir="$project_dir/run-data/armory-combat-destruction-$(date +%s)"
else
  run_dir="$project_dir/run-data/armory-goliath-gameplay-$(date +%s)"
fi
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
if [[ "$combat_armory" == 1 ]]; then
  { printf 'var STARCOASTER_TEST_ARMORY_COMBAT = true;\n';
    cat scripts/live-armory-goliath-probe.js; } > "$run_dir/client/plugin/live-armory-goliath-probe.js"
else
  cp scripts/live-armory-goliath-probe.js "$run_dir/client/plugin/"
fi
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
  BRIDGE_TEST_BUILDING_HP="$test_building_hp" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
until grep -q 'GOLIATH_PROBE_DONE' "$run_dir/client.log" 2>/dev/null; do
  if (( SECONDS - started > 175 )); then echo "Gameplay probe timed out: $run_dir" >&2; exit 1; fi
  sleep 1
done
sleep 3
python3 - "$run_dir" <<'PY'
import json, os, re, sys
from pathlib import Path
run = Path(sys.argv[1]); server = (run / 'server.log').read_text(errors='replace')
client = (run / 'client.log').read_text(errors='replace')
combat_armory = os.environ.get('STARCOASTER_TEST_ARMORY_COMBAT') == '1'
commands = dict(re.findall(r'GOLIATH_PROBE_COMMAND label=(\S+) accepted=(\w+)', client))
actor = re.search(r'GOLIATH_PROBE_ACTOR id=(openbw:\d+) hp=(\d+)', client)
trains = re.findall(r'\[world-control\] train command=\S+ barracks=\d+ accepted=(\d).*?'
                    r'minerals=(\d+).*?unit_type=terran_goliath gas=(\d+)', server)
availability = [json.loads(row)['terran_goliath'] for row in re.findall(
    r'\[world-control\] production id=.*? availability=(\{.*\}) minerals=', server)
    if 'terran_goliath' in json.loads(row)]
armory = re.search(r'\[world\] target id=(openrct2:large_scenery:\d+:\S+) '
                   r'proxy=\d+ type=Terran_Armory', server)
checks = {
    'factory_armory_and_supply_placed': all(f'GOLIATH_PROBE_PLACE type={kind} accepted=true' in client
        for kind in ('terran_factory', 'terran_armory', 'terran_supply_depot')),
    'native_armory_750_hp': 'type=Terran_Armory hp=750' in server,
    'native_prerequisite': 'without_armory' in commands and 'with_armory' in commands
        and len(trains) >= 2 and trains[0] == ('0', '500', '250')
        and any(row[0] == '1' for row in trains),
    'native_charge': any(row == ('1', '400', '200') for row in trains),
    'native_supply_capacity': bool(re.search(
        r'train command=.*accepted=1.*supply=14/32.*unit_type=terran_goliath', server)),
    'duplicate_no_extra_charge': 'GOLIATH_PROBE_DUPLICATE request=' in client
        and sum(row[0] == '1' for row in trains) == 1,
    'completed_actor': bool(actor and int(actor[2]) == 125),
    'both_native_bindings': bool(actor) and all(
        'actor binding id=' + actor[1] + ' participant=' + role in server
        for role in ('publisher', 'controller')),
    'mixed_move': commands.get('mixed_move') == 'true',
    ('goliath_attack_order' if combat_armory else 'goliath_native_combat'):
        'GOLIATH_PROBE_WAVE accepted=true' in client
        and commands.get('goliath_attack') == 'true'
        and (combat_armory or 'GOLIATH_PROBE_ATTACK id=' in client
             and 'GOLIATH_PROBE_HIT target=' in client),
    'armory_retired': (
        ('GOLIATH_PROBE_ARMORY_COMBAT_REMOVED' in client
         and (commands.get('armory_attack') in (None, 'true'))
         and bool(armory and re.search(r'native target state id=' + re.escape(armory[1])
                                       + r' proxy=openbw:\d+ hp=0', server))
         and bool(armory and 'combat demolition synchronized id=' + armory[1] in server))
        if combat_armory else
        ('GOLIATH_PROBE_REMOVE accepted=true' in client and 'target retired id=' in server)),
    'prerequisite_relocked': 'after_armory_removal' in commands
        and len(trains) >= 3 and trains[-1] == ('0', '400', '200')
        and bool(availability and availability[-1]['reason'] == 'requires_building'),
    'two_client_sync': 'WORLD_PATCH_SYNC' in server
        and not re.search(r'\b(shared-state mismatch|native.*diverge)\b', server, re.I),
}
(run / 'verification.json').write_text(json.dumps({'checks': checks, 'trains': trains,
    'availability': availability}, indent=2) + '\n')
print(json.dumps(checks, indent=2)); print('Gameplay evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
