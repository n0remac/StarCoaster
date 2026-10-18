#!/usr/bin/env bash
# Isolated native fixture: the existing scenario Hatchery/Pool, map Overlord, and native resources.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/zerg-production-native-$(date +%s)"
mkdir -p "$run_dir"
python3 - "$run_dir/scenario.json" <<'PY'
import json, sys
from pathlib import Path
scenario = json.loads(Path('scenarios/mt-zergling/scenario.json').read_text())
scenario['production_fixture']['zerg_minerals'] = 100
scenario['production_fixture']['native_overlord'] = [7, 7]
Path(sys.argv[1]).write_text(json.dumps(scenario, indent=2) + '\n')
PY
python3 scripts/create-world-base-map.py --scenario "$run_dir/scenario.json" \
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
BRIDGE_TEST_ZERG_PRODUCTION=1 BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" \
  BRIDGE_SCENARIO_CONFIG="$run_dir/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 150s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until [[ $(grep -c 'stage=hatched ' "$run_dir/session.log" 2>/dev/null || true) -ge 2 ]]; do
  if (( SECONDS - start > 135 )); then
    echo "Timed out waiting for native Zerg production: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); log = (run / 'session.log').read_text(errors='replace')
def row(role, stage):
    values = re.findall(r'^\[zerg-production\] role=' + role + r' stage=' + stage + r' .+$', log, re.M)
    return values[-1] if values else ''
checks = {}
for role in ('publisher', 'controller'):
    larva, egg, hatched = (row(role, stage) for stage in ('larva', 'egg', 'hatched'))
    checks[role + '_completed_owned_hatchery_larva'] = bool(re.search(
        r'owner=0 completed=1 count=[1-3] native=\d+', larva))
    checks[role + '_observed_incomplete_egg'] = bool(re.search(
        r'native=\d+ completed=0 remaining=[1-9]\d*', egg))
    checks[role + '_two_distinct_zerglings'] = bool(re.search(
        r'first=(\d+) second=(\d+) egg_gone=1', hatched)
        and re.search(r'first=(\d+) second=(\d+)', hatched).group(1)
        != re.search(r'first=(\d+) second=(\d+)', hatched).group(2))
train = row('publisher', 'train')
match = re.search(r'can_train=1 accepted=1 minerals=(\d+)->(\d+) supply=(\d+)->(\d+) supply_total=(\d+)', train)
checks['native_command_resource_supply'] = bool(match and int(match[1]) - int(match[2]) == 50
    and int(match[4]) - int(match[3]) == 1 and int(match[5]) >= int(match[4]))
checks['same_morph_identity'] = bool(re.search(r'larva=(\d+)', train)
    and re.search(r'native=(\d+)', row('publisher', 'egg'))
    and re.search(r'larva=(\d+)', train).group(1)
    == re.search(r'native=(\d+)', row('publisher', 'egg')).group(1))
(run / 'verification.json').write_text(json.dumps({'checks': checks}, indent=2) + '\n')
print(json.dumps(checks, indent=2)); print('Native Zerg evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
