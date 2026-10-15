#!/usr/bin/env bash
# Opt-in unchanged navigation hash for a mapping-defined decorative wall.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"; test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-unchanged-$(date +%s)"
mkdir -p "$run_dir/client/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client/plugin/"
cp scripts/live-visual-probe.js "$run_dir/client/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
cat > "$run_dir/mapping.json" <<'JSON'
{"rules":[{"kind":"wall","destructible":false,"targetable":false,"blocks":false}]}
JSON
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
BRIDGE_MAP_FILE="$map_file" BRIDGE_RULES_CONFIG="$run_dir/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
  timeout 115s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
  --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
  --user-data-path="$run_dir/client" > "$run_dir/client.log" 2>&1 &
client_pid=$!
wait_for 'LIVE_VISUAL_COMPLETE|LIVE_VISUAL_ERROR' "$run_dir/client.log" 50
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / 'server.log').read_text(errors='replace')
client = (directory / 'client.log').read_text(errors='replace')
patches = re.findall(r'park patch synchronized id=', server)
metrics = re.findall(r'WORLD_PATCH_METRIC patch=([^ ]+) action_to_detection_ms=(-?\d+) detection_to_patch_ms=(\d+)(?: payload_bytes=\d+)? operations=(\d+)', server)
native = re.findall(r'\[world\] navigation-mask hash=([0-9a-f]{16}) frame=\d+ accepted=1[^\n]*unchanged=(\d)', server)
control = re.findall(r'\[world-control\] navigation-mask hash=([0-9a-f]{16}) frame=\d+ accepted=1[^\n]*unchanged=(\d)', server)
checks = {
    'ordinary_visual_actions': 'LIVE_VISUAL_BUILD accepted=true' in client
        and 'LIVE_VISUAL_REMOVE accepted=true' in client,
    'two_confirmed_revisions': len(patches) == 2,
    'performance_recorded': bool(metrics) and int(metrics[0][1]) >= 0,
    'native_rebuild_skipped': len(native) >= 3 and len(control) >= 3
        and len({hash for hash, _ in native}) == 1
        and native[-1][0] == control[-1][0]
        and all(flag == '1' for _, flag in native[1:] + control[1:]),
}
result = {'checks': checks, 'patches': len(patches),
          'metrics': metrics, 'publisher_masks': native, 'controller_masks': control}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not all(checks.values()): raise SystemExit(1)
PY
printf 'Live unchanged logs: %s\n' "$run_dir"
