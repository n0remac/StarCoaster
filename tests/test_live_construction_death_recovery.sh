#!/usr/bin/env bash
# A target killed while the Go bridge is down must be retired once on reconnect.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"
test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-death-recovery-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-a/plugin/"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-b/plugin/"
{ printf 'var STARCOASTER_TEST_DEATH_RECOVERY = true;\n'; cat scripts/live-target-probe.js; } \
  > "$run_dir/client-a/plugin/live-target-probe.js"
cp scripts/live-target-observer.js "$run_dir/client-b/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
session_pid=""; client_a_pid=""; client_b_pid=""; bridge_restart_pid=""
cleanup() {
  for pid in "$client_a_pid" "$client_b_pid" "$bridge_restart_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_a_pid" "$client_b_pid" "$bridge_restart_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 150s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then
      printf 'Session stopped before %s\n' "$pattern" >&2
      return 1
    fi
    sleep 0.1
  done
}
wait_for 'WORLD_READY' "$run_dir/server.log" 70
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
for name in client-a client-b; do
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$run_dir/$name" > "$run_dir/$name.log" 2>&1 &
  if [[ "$name" == client-a ]]; then client_a_pid=$!; else client_b_pid=$!; fi
  if [[ "$name" == client-a ]]; then
    # The first joined client owns Terran commands in this test session.
    wait_for 'LIVE_TARGET_RIDECREATE accepted=true' "$run_dir/client-a.log" 40
  fi
done
wait_for 'LIVE_TARGET_ATTACK accepted=true' "$run_dir/client-a.log" 50
wait_for 'native target state id=openrct2:ride:4#1 .* hp=([1-2][0-9]|3[0-5]) revision=2' \
  "$run_dir/server.log" 25
original_bridge_pid="$(ps -eo pid,args | awk '$2 ~ /\/build\/world-bridge$/ { print $1; exit }')"
test -n "$original_bridge_pid"
kill "$original_bridge_pid"
for attempt in $(seq 1 50); do
  if ! kill -0 "$original_bridge_pid" 2>/dev/null; then break; fi
  sleep 0.1
done
# Existing Marine attack orders continue in OpenBW during the bridge outage.
sleep 8
build/world-bridge --rules "$project_dir/scenarios/frontier-outpost/mapping.json" \
  > "$run_dir/bridge-restart.log" 2>&1 &
bridge_restart_pid=$!
wait_for 'park snapshot session=' "$run_dir/bridge-restart.log" 60
wait_for 'combat demolition synchronized id=openrct2:ride:4#1' "$run_dir/bridge-restart.log" 70
wait_for 'LIVE_TARGET_OBSERVER_SHOP present=false' "$run_dir/client-b.log" 30
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
before = (directory / 'server.log').read_text(errors='replace')
after = (directory / 'bridge-restart.log').read_text(errors='replace')
driver = (directory / 'client-a.log').read_text(errors='replace')
observer = (directory / 'client-b.log').read_text(errors='replace')
target = re.search(r'LIVE_TARGET_TRACKPLACE accepted=true .*target=(openrct2:ride:\d+#\d+)', driver)
target_id = target.group(1) if target else ''
native = before + '\n' + after
checks = {
    'new_shop_attacked': bool(target_id) and 'LIVE_TARGET_ATTACK accepted=true' in driver,
    'same_session_snapshot_recovered': 'park snapshot session=' in after,
    'zero_hp_replayed': f'combat demolition synchronized id={target_id}' in after,
    'one_park_removal': bool(target_id)
        and native.count(f'WORLD_REMOVAL id={target_id} state=confirmed') == 1,
    'two_native_masks': bool(re.search(r'\[world\] navigation-mask hash=', native))
        and bool(re.search(r'\[world-control\] navigation-mask hash=', native)),
    'second_client_retired_target': 'LIVE_TARGET_OBSERVER_SHOP present=true' in observer
        and 'LIVE_TARGET_OBSERVER_SHOP present=false' in observer,
    'no_false_patch_sync': 'WORLD_PATCH_ERROR' not in native,
}
result = {'checks': checks, 'target_id': target_id}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Death recovery logs: %s\n' "$run_dir"
