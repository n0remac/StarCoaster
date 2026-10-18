#!/usr/bin/env bash
# Three isolated native fixtures exercise OpenBW prerequisite, mineral, and supply rejection.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/zerg-production-rejection-$(date +%s)"
mkdir -p "$run_dir"
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
for variant in absent_pool insufficient_minerals supply_cap; do
  case_dir="$run_dir/$variant"
  mkdir -p "$case_dir"
  python3 - "$case_dir/scenario.json" "$variant" <<'PY'
import json, sys
from pathlib import Path
scenario = json.loads(Path('scenarios/mt-zergling/scenario.json').read_text())
variant = sys.argv[2]
fixture = scenario['production_fixture']
fixture['zerg_minerals'] = 1 if variant == 'insufficient_minerals' else 100
fixture['native_overlord'] = [7, 7]
Path(sys.argv[1]).write_text(json.dumps(scenario, indent=2) + '\n')
PY
  scripts/project.sh validate-scenario "$case_dir/scenario.json" >/dev/null
  python3 scripts/create-world-base-map.py --scenario "$case_dir/scenario.json" \
    --output "$case_dir/mt-zergling.scm" >/dev/null
  BRIDGE_TEST_ZERG_PRODUCTION=1 BRIDGE_TEST_ZERG_PRODUCTION_REJECTION=1 \
    BRIDGE_TEST_ZERG_PRODUCTION_REMOVE_POOL="$([[ "$variant" == absent_pool ]] && echo 1 || true)" \
    BRIDGE_TEST_ZERG_PRODUCTION_FILL_SUPPLY="$([[ "$variant" == supply_cap ]] && echo 1 || true)" \
    BRIDGE_MAP_FILE="$case_dir/mt-zergling.scm" \
    BRIDGE_SCENARIO_CONFIG="$case_dir/scenario.json" \
    BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
    BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
    BRIDGE_SERVER_DATA_DIR="$case_dir/server" \
    timeout 120s scripts/run-world-session.sh "$park_file" > "$case_dir/session.log" 2>&1 &
  session_pid=$!
  started=$SECONDS
  until grep -q 'role=publisher stage=rejected ' "$case_dir/session.log" 2>/dev/null; do
    if (( SECONDS - started > 105 )); then
      echo "Timed out waiting for native rejection: $case_dir" >&2
      exit 1
    fi
    sleep 1
  done
  cleanup
  session_pid=""
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); checks = {}
for variant in ('absent_pool', 'insufficient_minerals', 'supply_cap'):
    log = (run / variant / 'session.log').read_text(errors='replace')
    scenario = json.loads((run / variant / 'scenario.json').read_text())
    rows = re.findall(r'^\[zerg-production\] role=publisher stage=train .+$', log, re.M)
    train = rows[-1] if rows else ''
    match = re.search(r'can_train=0 accepted=0 minerals=(\d+)->(\d+) '
                      r'supply=(\d+)->(\d+) supply_total=(\d+)', train)
    checks[variant + '_native_rejected_without_charging'] = bool(match
        and match[1] == match[2] and match[3] == match[4])
    checks[variant + '_larvae_without_eggs'] = (all(
        re.search(r'role=' + role + r' stage=larva ', log) for role in ('publisher', 'controller'))
        and 'role=publisher stage=rejected egg_count=0' in log
        and 'stage=egg ' not in log)
    if variant == 'absent_pool':
        checks['absent_pool_fixture'] = all(re.search(
            r'role=' + role + r' stage=pool_removed count=[1-9]\d*', log)
            for role in ('publisher', 'controller')) and 'pool_count=0' in train
    elif variant == 'insufficient_minerals':
        checks['insufficient_minerals_fixture'] = scenario['production_fixture']['zerg_minerals'] < 50
    else:
        checks['supply_cap_fixture'] = (bool(match) and int(match[3]) >= int(match[5])
            and all(re.search(r'role=' + role + r' stage=supply_filled units=5 ', log)
                    for role in ('publisher', 'controller')))
(run / 'verification.json').write_text(json.dumps({'checks': checks}, indent=2) + '\n')
print(json.dumps(checks, indent=2)); print('Native rejection evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
