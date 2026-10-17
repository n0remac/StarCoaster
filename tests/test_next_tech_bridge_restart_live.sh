#!/usr/bin/env bash
# Same-session Go restart retains four park buildings, native resources, and actors.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
run_dir="$project_dir/run-data/next-tech-bridge-restart-$(date +%s)"
mkdir -p "$run_dir/server" "$run_dir/client/plugin"
printf 'var STARCOASTER_KEEP_NEXT_BUILDINGS = true;\n' \
  > "$run_dir/client/plugin/live-medic-vulture-probe.js"
cat scripts/live-medic-vulture-probe.js >> "$run_dir/client/plugin/live-medic-vulture-probe.js"
cp scripts/live-next-tech-reconnect-probe.js openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
  --output "$run_dir/mt-zergling.scm" >/dev/null
session_pid=""; client_pid=""; bridge_pid=""
cleanup() {
  for pid in "$client_pid" "$bridge_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_pid" "$bridge_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  until grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started > limit )); then
      echo "Timed out waiting for $pattern: $run_dir" >&2
      return 1
    fi
    sleep 1
  done
}
BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for 'WORLD_READY' "$run_dir/server.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'NEXT_PROBE_MIXED_MOVE accepted=true' "$run_dir/client.log" 130
wait_for 'NEXT_RECONNECT_STATE .*actors=openbw:[0-9]+:terran_medic,openbw:[0-9]+:terran_vulture' \
  "$run_dir/client.log" 15
cp "$run_dir/client.log" "$run_dir/before-client.log"
old_count="$(grep -c 'NEXT_RECONNECT_STATE' "$run_dir/client.log")"
old_pid="$(ps -eo pid,args | awk -v binary="$project_dir/build/world-bridge" '$2 == binary { print $1; exit }')"
test -n "$old_pid"
kill "$old_pid"
build/world-bridge --scenario "$project_dir/scenarios/mt-zergling/scenario.json" \
  --rules "$project_dir/scenarios/mt-zergling/mapping.json" \
  --spawn-journal "$run_dir/spawn-queue.json" > "$run_dir/restart.log" 2>&1 &
bridge_pid=$!
wait_for 'OpenBW ready targets=6' "$run_dir/restart.log" 60
started=$SECONDS
while (( $(grep -c 'NEXT_RECONNECT_STATE' "$run_dir/client.log") <= old_count )); do
  if (( SECONDS - started > 35 )); then
    echo "Timed out waiting for post-restart client state: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
p=Path(sys.argv[1]); first=(p/'server.log').read_text(errors='replace')
restart=(p/'restart.log').read_text(errors='replace')
before=(p/'before-client.log').read_text(errors='replace')
after=(p/'client.log').read_text(errors='replace')
def states(text):
    return re.findall(r'NEXT_RECONNECT_STATE session=([0-9a-f]{32}) minerals=(\d+) '
                      r"gas=(\d+) supply=(\d+/\d+) actors=([^\r\n']*)", text)
old, new = states(before), states(after)
buildings = re.findall(r'\[world\] target id=(openrct2:large_scenery:\S+) '
                       r'proxy=\d+ type=(Terran_(?:Barracks|Factory|Supply_Depot|Academy)) '
                       r'hp=(\d+)', first)
linked = re.findall(r'native target state id=(openrct2:large_scenery:\S+) '
                    r'proxy=(openbw:\d+) hp=(\d+)', restart)
linked_ids={entry[0] for entry in linked}
retained_actor_ids = [entry.split(':terran_')[0] for entry in old[-1][4].split(',')] if old else []
old_session=re.search(r'park snapshot session=([0-9a-f]{32}) revision=1', first)
new_session=re.search(r'park snapshot session=([0-9a-f]{32}) revision=\d+', restart)
checks={
    'four_park_and_native_buildings': len(buildings)==4 and len({row[1] for row in buildings})==4,
    'native_building_identities_rebound': len(buildings)==4
        and all(row[0] in linked_ids for row in buildings),
    'no_duplicate_native_buildings': len(buildings)==4
        and not re.search(r'\[world\] target id=.*type=Terran_(Barracks|Factory|Supply_Depot|Academy)', restart),
    'same_park_session': bool(old_session and new_session)
        and old_session[1]==new_session[1],
    'same_resources_and_actors': bool(old and new) and old[-1]==new[-1]
        and old[-1][1:4]==('375','225','16/32')
        and 'terran_medic' in old[-1][4] and 'terran_vulture' in old[-1][4],
    'two_native_participants_reconnected': 'OpenBW ready targets=6' in restart,
    'medic_and_vulture_rebound': len(retained_actor_ids)==2 and all(
        'actor binding id='+actor+' participant='+role in restart
        for actor in retained_actor_ids for role in ('publisher','controller')),
}
(p/'verification.json').write_text(json.dumps({'checks':checks,'before':old[-1:] if old else [],
    'after':new[-1:] if new else [],'buildings':buildings,'linked':linked},indent=2)+'\n')
print(json.dumps(checks,indent=2))
print('Next technology bridge restart evidence:',p)
if not all(checks.values()): raise SystemExit(1)
PY
