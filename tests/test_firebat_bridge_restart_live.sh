#!/usr/bin/env bash
# Preserve active native Firebat training, gas, actors, and Academy tech on Go restart.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-bridge-restart-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
  --output "$run_dir/mt-zergling.scm" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
cp openrct2-plugin/rts-bridge.js scripts/live-firebat-gameplay-probe.js "$run_dir/client/plugin/"
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
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
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
  timeout 190s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for 'WORLD_READY' "$run_dir/server.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'train command=.*accepted=1.*unit_type=terran_firebat gas=225' "$run_dir/server.log" 80
old_pid="$(ps -eo pid,args | awk -v binary="$project_dir/build/world-bridge" '$2 == binary { print $1; exit }')"
test -n "$old_pid"
kill "$old_pid"
started=$SECONDS
while [[ -n "$(ss -ltnH 'sport = :40010')" ]]; do
  if (( SECONDS - started >= 10 )); then echo 'Old bridge did not release port 40010' >&2; exit 1; fi
  sleep 0.1
done
build/world-bridge --scenario "$project_dir/scenarios/mt-zergling/scenario.json" \
  --rules "$project_dir/scenarios/mt-zergling/mapping.json" \
  --spawn-journal "$run_dir/spawn-queue.json" > "$run_dir/restart.log" 2>&1 &
bridge_pid=$!
wait_for 'park snapshot session=' "$run_dir/restart.log" 55
wait_for 'OpenBW ready targets=6' "$run_dir/restart.log" 55
wait_for 'FIREBAT_PROBE_AFTER_REMOVE' "$run_dir/client.log" 100
sleep 2
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); first = (run/'server.log').read_text(errors='replace')
restart = (run/'restart.log').read_text(errors='replace')
client = (run/'client.log').read_text(errors='replace')
first_session = re.search(r'park snapshot session=([0-9a-f]{32}) revision=1', first)
next_session = re.search(r'park snapshot session=([0-9a-f]{32}) revision=3', restart)
trains = re.findall(r'train command=\S+ barracks=\d+ accepted=(\d).*?'
                    r'minerals=(\d+).*?unit_type=terran_firebat gas=(\d+)', first+restart)
checks = {
    'queue_active_at_restart': bool(re.search(
        r'train command=\S+ barracks=\d+ accepted=1 queue=1 minerals=450.*?'
        r'unit_type=terran_firebat gas=225', first)),
    'same_session_reconciled': bool(first_session and next_session)
        and first_session.group(1) == next_session.group(1),
    'native_academy_retained': 'type=Terran_Academy hp=600' in first
        and 'OpenBW ready targets=6' in restart,
    'first_firebat_completed_after_restart': 'FIREBAT_PROBE_SECOND accepted=true' in client
        and 'actor binding id=openbw:3001' in first+restart,
    'resources_and_second_firebat_retained': ('1', '450', '225') in trains
        and ('1', '400', '200') in trains
        and 'actor binding id=openbw:3002' in first+restart,
    'mixed_orders_after_restart': 'FIREBAT_PROBE_MIXED_MOVE accepted=true' in client
        and 'FIREBAT_PROBE_REDIRECT accepted=true' in client,
    'demolition_relocks': 'FIREBAT_PROBE_AFTER_REMOVE' in client
        and trains and trains[-1][0] == '0',
}
(run/'verification.json').write_text(json.dumps({'checks':checks,'trains':trains},indent=2)+'\n')
print(json.dumps({'checks':checks,'trains':trains},indent=2))
print('Firebat bridge restart evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
