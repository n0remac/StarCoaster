#!/usr/bin/env bash
# Licensed two-client Academy placement and native lifecycle check.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/academy-construction-live-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
cp scripts/live-academy-build-probe.js openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 110s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
until grep -q 'type=Terran_Academy hp=600' "$run_dir/server.log" 2>/dev/null; do
  if (( SECONDS - start > 70 )); then echo "Timed out waiting for native Academy: $run_dir" >&2; exit 1; fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json, re, sys
from pathlib import Path
run = Path(sys.argv[1])
server = (run / 'server.log').read_text(errors='replace')
client = (run / 'client.log').read_text(errors='replace')
native = re.findall(r'\[world\] target id=(\S+) proxy=(\d+) type=Terran_Academy hp=(\d+)', server)
checks = {
    'park_action': 'ACADEMY_BUILD_PROBE_RESULT accepted=true' in client,
    'confirmed_revision': 'WORLD_PATCH_SYNC revision=2' in server,
    'one_native_academy': len(native) == 1 and native[0][2] == '600',
    'persistent_identity': bool(native and re.search(
        r'native target state id=' + re.escape(native[0][0]) + r' proxy=openbw:' + native[0][1] + r' hp=600', server)),
    'both_native_navigation_updates': 'navigation-mask hash=' in server and
        server.count('navigation-mask hash=') >= 2,
}
(run / 'verification.json').write_text(json.dumps({'checks': checks, 'native': native}, indent=2) + '\n')
print(json.dumps(checks, indent=2))
print(f'Academy construction evidence: {run}')
if not all(checks.values()): raise SystemExit(1)
PY
