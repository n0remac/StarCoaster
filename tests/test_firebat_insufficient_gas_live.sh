#!/usr/bin/env bash
# A completed Academy cannot bypass native OpenBW gas accounting.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-insufficient-gas-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
python3 - "$run_dir" <<'PY'
import json, sys
from pathlib import Path
source = Path('scenarios/mt-zergling/scenario.json')
scenario = json.loads(source.read_text())
scenario['production_fixture']['terran_gas'] = 0
(Path(sys.argv[1]) / 'scenario.json').write_text(json.dumps(scenario, indent=2) + '\n')
PY
python3 scripts/create-world-base-map.py --scenario "$run_dir/scenario.json" \
  --output "$run_dir/mt-zergling.scm" >/dev/null
cp scripts/live-firebat-gameplay-probe.js openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
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
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" BRIDGE_SCENARIO_CONFIG="$run_dir/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 120s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
until [[ $(grep -c 'unit_type=terran_firebat gas=0' "$run_dir/server.log" 2>/dev/null || true) -ge 2 ]] \
    && grep -q 'FIREBAT_PROBE_TRAIN' "$run_dir/client.log" 2>/dev/null; do
  if (( SECONDS - start > 95 )); then echo "Timed out waiting for native gas rejection: $run_dir" >&2; exit 1; fi
  sleep 1
done
sleep 2
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1])
server = (run / 'server.log').read_text(errors='replace')
client = (run / 'client.log').read_text(errors='replace')
train = re.findall(r'\[world-control\] train command=\S+ barracks=\d+ accepted=(\d).*?minerals=(\d+).*?unit_type=terran_firebat gas=(\d+)', server)
checks = {
    'academy_constructed': 'FIREBAT_PROBE_ACADEMY accepted=true' in client
        and 'type=Terran_Academy hp=600' in server,
    'native_gas_zero_reported': server.count('gas=0') >= 3,
    'availability_reports_insufficient_gas': '"reason":"insufficient_gas"' in server,
    'training_rejected_without_charge': len(train) >= 2 and train[0] == ('0', '500', '0')
        and train[-1] == ('0', '500', '0'),
    'no_firebat_created': '[world] actor-spawn id=openbw:3001' not in server,
}
(run / 'verification.json').write_text(json.dumps({'checks': checks, 'train': train}, indent=2) + '\n')
print(json.dumps(checks, indent=2))
print('Firebat insufficient gas evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
