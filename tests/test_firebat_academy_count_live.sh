#!/usr/bin/env bash
# Native Firebat unlock follows the count of completed Terran Academies.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-academy-count-$(date +%s)"
mkdir -p "$run_dir"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
  --output "$run_dir/mt-zergling.scm" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
session_pid=""
cleanup() {
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_FIREBAT_TECH=1 BRIDGE_TEST_FIREBAT_ACADEMY_COUNT=1 \
  BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until [[ $(grep -c '\[firebat-count\].*academies=0' "$run_dir/session.log" 2>/dev/null || true) -ge 2 ]]; do
  if (( SECONDS - start > 195 )); then
    echo "Timed out waiting for Academy count reconciliation: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); log = (run / 'session.log').read_text(errors='replace')
states = re.findall(r'^\[firebat-count\] role=(controller|publisher) academies=(\d)'
                    r' can_train=(\d) requirement_met=(\d) minerals=(\d+) gas=(\d+)$', log, re.M)
checks = {}
for role in ('controller', 'publisher'):
    # The publisher is the Zerg-side observer, so BWAPI canTrain is false for
    # Terran units there even while its synchronized prerequisite is present.
    for count, requirement in (('2', '1'), ('1', '1'), ('0', '0')):
        checks[f'{role}_{count}_academies'] = any(
            item == (role, count, requirement if role == 'controller' else '0',
                     requirement, '450', '225') for item in states)
(run / 'verification.json').write_text(json.dumps({'checks':checks,'states':states},indent=2)+'\n')
print(json.dumps({'checks':checks,'states':states},indent=2))
print('Academy count evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
