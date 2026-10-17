#!/usr/bin/env bash
# Same-session Academy reconciliation without restarting either native game.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/academy-bridge-restart-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
cp scripts/live-academy-build-probe.js openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
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
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then echo "Timed out waiting for $pattern" >&2; exit 1; fi
    sleep 1
  done
}
BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_TEST_ACADEMY_HP=372 \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 125s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for 'WORLD_READY' "$run_dir/server.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'WORLD_PATCH_SYNC revision=2' "$run_dir/server.log" 50
old_pid="$(ps -eo pid,args | awk -v binary="$project_dir/build/world-bridge" '$2 == binary { print $1; exit }')"
test -n "$old_pid"
kill "$old_pid"
build/world-bridge --scenario "$project_dir/scenarios/mt-zergling/scenario.json" \
  --rules "$project_dir/scenarios/mt-zergling/mapping.json" \
  --spawn-journal "$run_dir/spawn-queue.json" > "$run_dir/restart.log" 2>&1 &
bridge_pid=$!
wait_for 'park snapshot session=' "$run_dir/restart.log" 55
wait_for 'OpenBW ready targets=3' "$run_dir/restart.log" 55
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
p=Path(sys.argv[1]); first=(p/'server.log').read_text(errors='replace'); restart=(p/'restart.log').read_text(errors='replace')
target=r'openrct2:large_scenery:249:3360:3328:1216:0#1'
linked_before=re.findall(r'native target state id='+target+r' proxy=(openbw:\d+) hp=(\d+)', first)
linked_after=re.findall(r'native target state id='+target+r' proxy=(openbw:\d+) hp=(\d+)', restart)
first_session=re.search(r'park snapshot session=([0-9a-f]{32}) revision=1',first)
restarted_session=re.search(r'park snapshot session=([0-9a-f]{32}) revision=2',restart)
checks={
  'constructed': 'ACADEMY_BUILD_PROBE_RESULT accepted=true' in (p/'client.log').read_text(errors='replace'),
  'confirmed_patch': 'WORLD_PATCH_SYNC revision=2' in first,
  'same_session_reconciled': bool(first_session and restarted_session)
      and first_session.group(1)==restarted_session.group(1),
  'same_native_identity_and_health': bool(linked_before and linked_after)
      and linked_before[-1]==linked_after[-1] and linked_after[-1][1]=='372',
  'no_duplicate_native_academy': len(re.findall(r'\[world\] target id='+target+r' proxy=', first+restart))==1,
  'both_participants_ready': 'OpenBW ready targets=3' in restart,
}
(p/'verification.json').write_text(json.dumps({'checks':checks,'before':linked_before,
    'after':linked_after},indent=2)+'\n')
print(json.dumps({'checks':checks,'before':linked_before,'after':linked_after},indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Academy bridge restart logs: %s\n' "$run_dir"
