#!/usr/bin/env bash
# Licensed OpenRCT2 save/load and two-participant Barracks recovery check.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/scenarios/mt-zergling/map/mt-zergling.scm"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$map_file"; test -s "$park_file"
run_dir="$project_dir/run-data/barracks-save-load-live-$(date +%s)"
mkdir -p "$run_dir/server/plugin" "$run_dir/client/plugin" "$run_dir/reload-server"
cp scripts/live-barracks-save-probe.js "$run_dir/server/plugin/"
cp openrct2-plugin/rts-bridge.js scripts/live-barracks-build-probe.js "$run_dir/client/plugin/"
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
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then return 1; fi
    sleep 1
  done
}
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 115s scripts/run-world-session.sh "$park_file" > "$run_dir/build.log" 2>&1 &
session_pid=$!
wait_for 'WORLD_READY' "$run_dir/build.log" 75
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'BARRACKS_SAVE_PROBE_SAVED' "$run_dir/build.log" 65
saved="$run_dir/server/save/barracks-recovery.park"
test -s "$saved"
cleanup
session_pid=""; client_pid=""
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/reload-server" \
  timeout 100s scripts/run-world-session.sh "$saved" > "$run_dir/reload.log" 2>&1 &
session_pid=$!
wait_for 'WORLD_READY.*targets=3' "$run_dir/reload.log" 80
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
build = (directory / 'build.log').read_text(errors='replace')
reload = (directory / 'reload.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
pattern = r'native target state id=(openrct2:large_scenery:\d+:3200:3328:1216:0#\d+) .* hp=(\d+)'
before = re.findall(pattern, build)
after = re.findall(pattern, reload)
hashes = (re.findall(r'navigation initialized hash=([0-9a-f]{16})', reload),
          re.findall(r'park patch synchronized id=\S+ revision=2 hash=([0-9a-f]{16})', build))
checks = {
    'placement': 'BARRACKS_BUILD_PROBE_RESULT accepted=true' in client,
    'confirmed_before_save': 'WORLD_PATCH_SYNC revision=2' in build,
    'real_park_saved': (directory / 'server/save/barracks-recovery.park').stat().st_size > 0,
    'identity_and_health_preserved': bool(before and after) and before[-1] == after[-1],
    'native_mask_preserved': bool(hashes[0] and hashes[1]) and hashes[0][-1] == hashes[1][-1],
    'two_native_participants_ready': 'WORLD_READY entities=4255 targets=3' in reload,
}
result = {'checks': checks, 'before': before, 'after': after, 'hashes': hashes}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Barracks save/load logs: %s\n' "$run_dir"
