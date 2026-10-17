#!/usr/bin/env bash
# Both pinned OpenBW participants observe Factory, Armory, and Goliath production.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/goliath-native-$(date +%s)"
mkdir -p "$run_dir"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
  --output "$run_dir/mt-zergling.scm" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
session_pid=""
cleanup() {
  if [[ -n "$session_pid" ]]; then
    kill "$session_pid" 2>/dev/null || true
    wait "$session_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_GOLIATH_NATIVE=1 BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 180s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until [[ $(grep -c 'stage=removed ' "$run_dir/session.log" 2>/dev/null || true) -ge 2 ]]; do
  if (( SECONDS - start > 165 )); then
    echo "Timed out waiting for native Goliath probe: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); log = (run / 'session.log').read_text(errors='replace')
def stage(role, name):
    rows = re.findall(r'^\[goliath-tech\] role=' + role + r' stage=' + name + r' .+$', log, re.M)
    return rows[-1] if rows else ''
checks = {}
for role in ('controller', 'publisher'):
    before, after, completed, removed = (stage(role, s) for s in
                                         ('before', 'after', 'completed', 'removed'))
    checks[role + '_native_armory_requirement'] = 'required_armory=1' in before
    checks[role + '_factory_without_armory'] = 'can_train=0' in before
    checks[role + '_armory_completed'] = 'armory_hp=750' in after
    checks[role + '_goliath_completed'] = bool(re.search(r'native=\d+ hp=125', completed))
    checks[role + '_armory_removal'] = 'can_train=0' in removed and 'goliath_alive=1' in removed
checks['controller_unlocked'] = 'can_train=1' in stage('controller', 'after')
checks['publisher_cannot_order_for_other_player'] = 'can_train=0' in stage('publisher', 'after')
train = stage('controller', 'train')
match = re.search(r'accepted=1 minerals=(\d+)->(\d+) gas=(\d+)->(\d+) supply=(\d+)->(\d+)', train)
checks['native_resource_and_supply_charge'] = bool(match and int(match[1]) - int(match[2]) == 100
    and int(match[3]) - int(match[4]) == 50 and int(match[6]) - int(match[5]) == 4)
checks['native_attack_order'] = 'accepted=1' in stage('controller', 'attack')
(run / 'verification.json').write_text(json.dumps({'checks': checks}, indent=2) + '\n')
print(json.dumps(checks, indent=2)); print('Native Goliath evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
