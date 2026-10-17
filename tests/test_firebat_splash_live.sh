#!/usr/bin/env bash
# Verify native Firebat flame splash on both synchronized OpenBW participants.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/firebat-splash-$(date +%s)"
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
BRIDGE_TEST_FIREBAT_TECH=1 BRIDGE_TEST_FIREBAT_SPLASH=1 \
  BRIDGE_MAP_FILE="$run_dir/mt-zergling.scm" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until [[ $(grep -c '\[firebat-splash\].*stage=splash' "$run_dir/session.log" 2>/dev/null || true) -ge 2 ]]; do
  if (( SECONDS - start > 195 )); then
    echo "Timed out waiting for two native splash reports: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1]); log = (run / 'session.log').read_text(errors='replace')
hits = re.findall(r'^\[firebat-splash\] role=(controller|publisher) stage=splash frame=(\d+) damaged=(\d+) hp=(\d+),(\d+)$', log, re.M)
checks = {
    'native_attack_accepted': bool(re.search(r'^\[firebat-splash\] role=controller stage=attack accepted=1', log, re.M)),
    'both_participants_saw_same_frame_splash': len(hits) == 2
        and {hit[0] for hit in hits} == {'controller', 'publisher'}
        and all(int(hit[2]) >= 2 and int(hit[3]) < 35 and int(hit[4]) < 35 for hit in hits),
    'native_firebat_completed': 'stage=unit_created' in log and 'stage=completed firebats=1' in log,
}
(run / 'verification.json').write_text(json.dumps({'checks':checks,'hits':hits},indent=2)+'\n')
print(json.dumps({'checks':checks,'hits':hits},indent=2))
print('Native splash evidence:', run)
if not all(checks.values()): raise SystemExit(1)
PY
