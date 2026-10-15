#!/usr/bin/env bash
# Opt-in ordinary manual demolition after live shop construction.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"
test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-manual-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-a/plugin/"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-b/plugin/"
{ printf 'var STARCOASTER_TEST_MANUAL = true;\n'; cat scripts/live-target-probe.js; } \
  > "$run_dir/client-a/plugin/live-target-probe.js"
cp scripts/live-target-observer.js "$run_dir/client-b/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
session_pid=""; client_a_pid=""; client_b_pid=""
cleanup() {
  for pid in "$client_a_pid" "$client_b_pid" "$session_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$client_a_pid" "$client_b_pid" "$session_pid"; do
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
    sleep 1
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
    wait_for 'LIVE_TARGET_RIDECREATE accepted=true' "$run_dir/client-a.log" 40
  fi
done
wait_for 'LIVE_TARGET_COMPLETE|LIVE_TARGET_ERROR' "$run_dir/client-a.log" 100
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / 'server.log').read_text(errors='replace')
driver = (directory / 'client-a.log').read_text(errors='replace')
observer = (directory / 'client-b.log').read_text(errors='replace')
target = re.search(r'LIVE_TARGET_TRACKPLACE accepted=true .*target=(openrct2:ride:\d+#\d+)', driver)
target_id = target.group(1) if target else ''
catalogs = [int(x) for x in re.findall(r'WORLD_TARGET_CATALOG .* targets=(\d+)', server)]
checks = {
    'ordinary_shop_actions': 'LIVE_TARGET_RIDECREATE accepted=true' in driver
        and bool(target),
    'shop_discovered_and_synchronized': bool(target_id)
        and f'"{target_id}"' in server and 'park patch synchronized' in server,
    'proxy_created': bool(target_id) and f'[world] target id={target_id} proxy=' in server,
    'ordinary_manual_demolition': 'LIVE_TARGET_MANUAL_REMOVE accepted=true' in driver,
    'native_target_retired': len(re.findall(r'park patch synchronized id=', server)) >= 2
        and bool(target_id) and f'[world] target id={target_id} proxy=' in server
        and catalogs and max(catalogs) > catalogs[-1],
    'no_combat_destruction': bool(target_id)
        and f'[world] target destroyed id={target_id}' not in server
        and f'WORLD_REMOVAL id={target_id} state=confirmed' not in server,
    'second_client_current_catalog': 'LIVE_TARGET_OBSERVER_CATALOG' in observer,
    'second_client_saw_shop_lifecycle': 'LIVE_TARGET_OBSERVER_SHOP present=true' in observer
        and 'LIVE_TARGET_OBSERVER_SHOP present=false' in observer,
}
result = {'checks': checks, 'target_id': target_id, 'catalog_counts': catalogs}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Live manual logs: %s\n' "$run_dir"
