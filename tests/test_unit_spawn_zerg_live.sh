#!/usr/bin/env bash
# Opt-in native scenario Zergling wave through the shared spawn queue.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="${PARK_FILE:-$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park}"
test -f "$park_file"
run_dir="$project_dir/run-data/zerg-spawn-live-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin"
python3 scripts/create-world-base-map.py --output "$run_dir/world-live.scm" --scenario scenarios/frontier-outpost/scenario.json
for client in client-a client-b; do
  cp scripts/world-zerg-spawn-observer.js "$run_dir/$client/plugin/"
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
BRIDGE_SCENARIO_CONFIG=tests/fixtures/frontier-outpost-zerg-wave.json \
  BRIDGE_MAX_TARGETS=32 BRIDGE_MAP_FILE="$run_dir/world-live.scm" \
  timeout 180s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
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
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
for name in client-a client-b; do
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$run_dir/$name" > "$run_dir/$name.log" 2>&1 &
  if [[ "$name" == client-a ]]; then client_a_pid=$!; else client_b_pid=$!; fi
done
wait_for 'scenario spawn request=.*state=ready' "$run_dir/session.log" 90
wait_for 'WORLD_ZERG_ROSTER count=17' "$run_dir/client-a.log" 90
wait_for 'WORLD_ZERG_ROSTER count=17' "$run_dir/client-b.log" 90
wait_for 'WORLD_ZERG_MOVED id=openbw:300' "$run_dir/client-a.log" 120
wait_for 'openbw:3001,[0-9]+,[0-9]+,[0-9]+,attack' "$run_dir/client-a.log" 120
python3 - "$run_dir" <<'PY'
import re
import sys
from pathlib import Path
root = Path(sys.argv[1])
server = (root / 'session.log').read_text(errors='replace')
expected = {f'openbw:{i}' for i in range(3001, 3006)}
for client in ('client-a', 'client-b'):
    log = (root / (client + '.log')).read_text(errors='replace')
    rosters = [set(ids.split(',')) for count, ids in re.findall(
        r'WORLD_ZERG_ROSTER count=(\d+) ids=([a-z0-9:,]+)', log) if int(count) == 17]
    if not any(expected <= roster and len(roster) == 17 for roster in rosters):
        raise SystemExit(f'{client} did not display seventeen unique native Zerglings')
for actor in expected:
    if server.count('actor-spawn id=' + actor) != 1 or not re.search(
            r'actor binding id=' + actor + r' participant=controller native=\d+ active=true', server):
        raise SystemExit(f'missing unique native Zergling binding for {actor}')
# OpenRCT2 and OpenBW share this log stream; their writes can interleave in
# the request prefix. The native index/type suffix remains the evidence here.
if len(re.findall(r'index=[0-4] type=zerg_zergling x=\d+', server)) != 5:
    raise SystemExit('five sequential native Zergling creations were not issued')
combat = (root / 'client-a.log').read_text(errors='replace')
if not re.search(r'openbw:3001,\d+,\d+,\d+,attack,\d+,zerg_zergling,\d+,35,0,[1-9]\d*', combat):
    raise SystemExit('spawned Zergling did not enter native attack frames')
print('ZERG_SPAWN_LIVE_PASS five native Zerglings, two clients, native movement and attack')
PY
printf 'Logs: %s\n' "$run_dir"
