#!/usr/bin/env bash
# Opt-in native integration test. Requires licensed RCT2 and StarCraft data.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="${PARK_FILE:-$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park}"
test -f "$park_file"
run_dir="$project_dir/run-data/world-live-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin"
python3 scripts/create-world-base-map.py --output "$run_dir/world-live.scm" \
  --scenario scenarios/frontier-outpost/scenario.json
cp scripts/world-target-probe.js scripts/world-client-probe.js "$run_dir/client-a/plugin/"
cp scripts/world-client-probe.js "$run_dir/client-b/plugin/"
for client in client-a client-b; do
  cp openrct2-plugin/rts-bridge.js "$run_dir/$client/plugin/rts-bridge.js"
done

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

BRIDGE_MAX_TARGETS=32 BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_MAP_FILE="$run_dir/world-live.scm" \
  timeout 300s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!

wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then
      printf 'World session stopped before %s\n' "$pattern" >&2
      return 1
    fi
    sleep 1
  done
}

wait_for 'WORLD_READY' "$run_dir/session.log" 75
wait_for 'WORLD_TARGET_CATALOG.*targets=32' "$run_dir/session.log" 20
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
for name in client-a client-b; do
  RCT2_DATA_DIR="$RCT2_DATA_DIR" build/openrct2/openrct2-cli join 127.0.0.1 \
    --headless --port=11753 --rct2-data-path="$RCT2_DATA_DIR" \
    --openrct2-data-path="$openrct2_data" --user-data-path="$run_dir/$name" \
    > "$run_dir/$name.log" 2>&1 &
  if [[ "$name" == client-a ]]; then client_a_pid=$!; else client_b_pid=$!; fi
  if [[ "$name" == client-a ]]; then
    wait_for 'WORLD_TARGET_PROBE actors=' "$run_dir/client-a.log" 60
  fi
done

wait_for 'WORLD_TARGET_ATTACK_QUERY accepted=true' "$run_dir/client-a.log" 90
wait_for 'WORLD_REMOVAL id=openrct2:ride:0#1 state=confirmed' "$run_dir/session.log" 180
wait_for 'WORLD_CLIENT_RIDES' "$run_dir/client-a.log" 20
wait_for 'WORLD_CLIENT_RIDES' "$run_dir/client-b.log" 20
python3 - "$run_dir/client-a.log" "$run_dir/client-b.log" <<'PY'
import json
import re
import sys
import time
from pathlib import Path

deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    states = []
    for name in sys.argv[1:]:
        matches = re.findall(r"WORLD_CLIENT_RIDES (\[[0-9, ]+\])", Path(name).read_text(errors="replace"))
        states.append(json.loads(matches[-1]) if matches else None)
    if states[0] is not None and states[0] == states[1] and 0 not in states[0]:
        print("WORLD_LIVE_PASS clients agree after native carousel removal")
        break
    time.sleep(1)
else:
    raise SystemExit(f"client states did not converge after ride removal: {states}")
PY
printf 'Logs: %s\n' "$run_dir"
