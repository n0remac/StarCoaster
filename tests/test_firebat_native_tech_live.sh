#!/usr/bin/env bash
# Focused two-participant OpenBW prerequisite and production experiment.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-native-tech-$(date +%s)"
mkdir -p "$run_dir"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
session_pid=""
cleanup() {
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_FIREBAT_TECH=1 BRIDGE_MAP_FILE="$map_file" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until grep -q '\[firebat-tech\] role=controller stage=removed' "$run_dir/session.log" 2>/dev/null; do
  if (( SECONDS - start > 195 )); then echo "Timed out waiting for Firebat tech probe: $run_dir" >&2; exit 1; fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1])
log = (run / 'session.log').read_text(errors='replace')
checks = {}
for role in ('controller', 'publisher'):
    def line(stage):
        matches = re.findall(r'^\[firebat-tech\] role=' + role + r' stage=' + stage + r' .*$', log, re.M)
        return matches[-1] if matches else ''
    before, academy, completed, removed = (line(stage) for stage in ('before', 'academy', 'completed', 'removed'))
    checks[f'{role}_prerequisite'] = ('requires_academy=1' in before and 'can_train=0' in before
                                      and 'minerals=500 gas=250' in before and 'queue=0' in before
                                      and re.search(r'supply=(\d+)/(\d+)', before) is not None)
    checks[f'{role}_academy_visible'] = 'academy_completed=1' in academy and 'academy_owner=1' in academy
    if role == 'controller':
        checks['controller_academy_unlock'] = 'can_train=1' in academy and 'can_train_unchecked=1' in academy
    else:
        checks['publisher_resource_and_queue_sync'] = bool(re.search(
            r'^\[firebat-tech\] role=publisher stage=queue minerals=450 gas=225 remaining=\d+', log, re.M))
    if role == 'controller':
        checks['controller_completion'] = 'firebats=1' in completed
        checks['controller_removal'] = 'can_train=0' in removed and 'firebats=1' in removed
created = re.findall(r'^\[firebat-tech\] role=(controller|publisher) stage=unit_created id=(\d+)', log, re.M)
checks['both_participants_created_firebat'] = (len(created) == 2 and
    {role for role, _ in created} == {'controller', 'publisher'} and created[0][1] == created[1][1])
train = re.search(r'^\[firebat-tech\] role=controller stage=train .*$', log, re.M)
checks['native_charge'] = bool(train and all(token in train.group() for token in
    ('accepted=1', 'minerals_before=500', 'gas_before=250', 'minerals_after=450', 'gas_after=225')))
(run / 'verification.json').write_text(json.dumps({'checks': checks}, indent=2) + '\n')
print(json.dumps(checks, indent=2))
print(f'Native tech evidence: {run}')
if not all(checks.values()): raise SystemExit(1)
PY
