#!/usr/bin/env bash
# Opt-in live OpenBW movement test. Requires installed licensed game data.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/frontier-native-nav-$(date +%s)"
mkdir -p "$run_dir/client/plugin"
sed '1i var STARCOASTER_WORLD_BRIDGE = true;' openrct2-plugin/rts-bridge.js \
  > "$run_dir/client/plugin/rts-bridge.js"
cp scripts/frontier-native-navigation-probe.js "$run_dir/client/plugin/"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"
test -s "$park_file"

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

BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost-mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 260s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
session_pid=$!

wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! rg -q "$pattern" "$file" 2>/dev/null; do
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

wait_for 'WORLD_READY' "$run_dir/server.log" 60
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" \
  --openrct2-data-path="$project_dir/build/openrct2-stage/usr/local/share/openrct2" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
if ! wait_for 'NATIVE_NAV_SEQUENCE_COMPLETE' "$run_dir/client.log" 210; then
  printf 'Navigation sequence did not complete; checking observed positions\n' >&2
fi
python3 scripts/verify-frontier-native-navigation.py "$run_dir"
printf 'Native navigation logs: %s\n' "$run_dir"
