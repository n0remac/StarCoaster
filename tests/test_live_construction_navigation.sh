#!/usr/bin/env bash
# Opt-in two-client native wall construction and demolition check.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
park_file="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
test -s "$map_file"
test -s "$park_file"
run_dir="$project_dir/run-data/live-construction-nav-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-a/plugin/"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-b/plugin/"
cp scripts/live-construction-probe.js "$run_dir/client-a/plugin/"
cp scripts/live-construction-observer.js "$run_dir/client-b/plugin/"
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
  timeout 190s scripts/run-world-session.sh "$park_file" > "$run_dir/server.log" 2>&1 &
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
    wait_for 'LIVE_CONSTRUCTION_ACTORS initial' "$run_dir/client-a.log" 40
  fi
done
wait_for 'LIVE_CONSTRUCTION_COMPLETE|LIVE_CONSTRUCTION_ERROR' "$run_dir/client-a.log" 145
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / "server.log").read_text(errors="replace")
driver = (directory / "client-a.log").read_text(errors="replace")
observer = (directory / "client-b.log").read_text(errors="replace")
patches = [(h, int(frame)) for h, frame in re.findall(
    r"park patch synchronized id=\S+ revision=\d+ hash=([0-9a-f]{16}) frame=(\d+)", server)]
publisher = {(h, int(frame)) for h, frame in re.findall(
    r"\[world\] navigation-mask hash=([0-9a-f]{16}) frame=(\d+) accepted=1", server)}
controller = {(h, int(frame)) for h, frame in re.findall(
    r"\[world-control\] navigation-mask hash=([0-9a-f]{16}) frame=(\d+) accepted=1", server)}
positions = [(int(phase), int(x), int(y)) for phase, x, y in re.findall(
    r"LIVE_CONSTRUCTION_POSITION phase=(\d+) x=(\d+) y=(\d+)", driver)]

def crossing(phase):
    rows = [(x, y) for p, x, y in positions if p == phase]
    for (ax, ay), (bx, by) in zip(rows, rows[1:]):
        if (ax - 640) * (bx - 640) <= 0 and ax != bx:
            fraction = (640 - ax) / (bx - ax)
            if 0 <= fraction <= 1:
                return round(ay + fraction * (by - ay))
    return None

identities = re.findall(r"LIVE_CONSTRUCTION_ACTORS (?:initial|final)=([^'\r\n]+)", driver)
checks = {
    "ordinary_wall_actions": "LIVE_CONSTRUCTION_BUILD accepted=true" in driver
        and "LIVE_CONSTRUCTION_REMOVE accepted=true" in driver,
    "two_confirmed_revisions": len(patches) >= 2,
    "both_native_participants_applied": len(patches) >= 2
        and all(item in publisher and item in controller for item in patches[:2]),
    "second_client_saw_wall_and_removal": "LIVE_OBSERVER_WALL present=true" in observer
        and observer.count("LIVE_OBSERVER_WALL present=false") >= 2,
    "same_actor_identities": len(identities) >= 2 and identities[0] == identities[-1],
    "native_movement_rerouted_and_reopened": crossing(2) is not None and crossing(4) is not None
        and not 992 <= crossing(2) < 1024 and 992 <= crossing(4) < 1024,
}
result = {"checks": checks, "patches": patches, "crossing_wall_present_y": crossing(2),
          "crossing_wall_removed_y": crossing(4), "position_samples": len(positions)}
(directory / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Live construction logs: %s\n' "$run_dir"
