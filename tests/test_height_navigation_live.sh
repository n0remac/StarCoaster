#!/usr/bin/env bash
# Focused native Marine/Zergling traversal in the generated layered park.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
exec {layered_live_lock_fd}> "$project_dir/run-data/.layered-navigation-live.lock"
flock "$layered_live_lock_fd"
python3 scripts/create-layered-navigation-park.py
park_file="$project_dir/run-data/layered-navigation/layered-navigation.park"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"
test -s "$map_file"
run_dir="$project_dir/run-data/layered-nav-live-$(date +%s)"
mkdir -p "$run_dir/client-a/plugin" "$run_dir/client-b/plugin" "$run_dir/server-data/plugin"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-a/plugin/"
cp openrct2-plugin/rts-bridge.js "$run_dir/client-b/plugin/"
cp scripts/layered-navigation-probe.js "$run_dir/client-a/plugin/"
cp scripts/live-construction-permissions.js "$run_dir/server-data/plugin/"
cp run-data/layered-navigation/source-elements.json "$run_dir/source-elements.json"
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
  BRIDGE_SCENARIO_CONFIG="$project_dir/tests/fixtures/frontier-outpost-zerg-wave.json" \
  BRIDGE_NAV_DIAGNOSTICS_DIR="$run_dir/navigation" \
  BRIDGE_LAUNCH_CLIENT=0 BRIDGE_SERVER_DATA_DIR="$run_dir/server-data" \
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
done
wait_for 'LAYERED_LIVE_COMPLETE' "$run_dir/client-a.log" 65
# The probe's action callbacks report OpenRCT2 acceptance. Keep the session
# alive until the bridge confirms the overhead and height-change revisions.
wait_for 'park patch synchronized .*revision=4 ' "$run_dir/server.log" 90
python3 scripts/render-layered-navigation-diagnostic.py \
  "$run_dir/navigation/confirmed-revision-1.json" --output "$run_dir/initial-ground-mask.svg"
python3 scripts/render-layered-navigation-diagnostic.py \
  "$run_dir/navigation/candidate-revision-3.json" --output "$run_dir/after-overhead-edits.svg"
python3 scripts/render-layered-navigation-diagnostic.py \
  "$run_dir/navigation/candidate-revision-4.json" --output "$run_dir/after-height-change.svg"
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
server = (directory / "server.log").read_text(errors="replace")
driver = (directory / "client-a.log").read_text(errors="replace")
source = json.loads((directory / "source-elements.json").read_text())
trace = json.loads((directory / "navigation/confirmed-revision-1.json").read_text())
after = json.loads((directory / "navigation/candidate-revision-4.json").read_text())
def blocked(x, y, sx=2, sy=2, state=trace):
    ox = (state["native_width"] - state["park_width"]) // 2
    oy = (state["native_height"] - state["park_height"]) // 2
    index = ((y+oy)*4+sy)*state["native_width"]*4 + (x+ox)*4+sx
    bits = bytes.fromhex(state["mask_hex"])
    return bool(bits[index//8] & (1 << (index%8)))
def cause(x, y):
    ox = (trace["native_width"] - trace["park_width"]) // 2
    oy = (trace["native_height"] - trace["park_height"]) // 2
    index = ((y+oy)*4+2)*trace["native_width"]*4 + (x+ox)*4+2
    return trace["causes"].get(str(index), [])
start = re.search(r"LAYERED_LIVE_START marine=(\d+),(\d+) zerg=(\d+),(\d+)", driver)
end = re.search(r"LAYERED_LIVE_COMPLETE marine=(\d+),(\d+) zerg=(\d+),(\d+).*track=(true|false) path=(true|false) height=(true|false) ghost=(true|false)", driver)
samples = [(int(elapsed), int(mx), int(my), int(zx), int(zy)) for elapsed, mx, my, zx, zy in re.findall(
    r"LAYERED_LIVE_POSITION elapsed=(\d+) marine=(\d+),(\d+) zerg=(\d+),(\d+)", driver)]
initial = re.search(r"\[world\] navigation-mask hash=([0-9a-f]{16}).*?accepted=1", server)
patches = re.findall(r"park patch synchronized id=\S+ revision=(\d+) hash=([0-9a-f]{16}) frame=(\d+)", server)
checks = {
    "generated_high_track": any(e["type"] == "track" and e["x"] == 16 and e["y"] == 31
                                and e["base_z"] == 192 for e in source["elements"]),
    "generated_layered_path": sum(e["type"] == "footpath" and e["x"] == 47
                                  and e["y"] == 57 for e in source["elements"]) == 2,
    "high_track_clear": not any(blocked(16,31,sx,sy) for sx in range(4) for sy in range(4)),
    "low_track_blocked": blocked(27,30),
    "station_blocked": blocked(29,30),
    "loop_blocked": blocked(35,30),
    "low_path_blocked": blocked(46,57),
    "layered_path_clear": not any(blocked(47,57,sx,sy) for sx in range(4) for sy in range(4)),
    "water_blocked": blocked(44,55),
    "elevated_wall_clear": not any(blocked(45,52,sx,sy) for sx in range(4) for sy in range(4)),
    "water_exported": any(e["type"] == "surface" and e["x"] == 44 and e["y"] == 55
                          and e["water_z"] == 128 for e in source["elements"]),
    "elevated_wall_exported": any(e["type"] == "wall" and e["x"] == 45 and e["y"] == 52
                                and e["base_z"] == 160 for e in source["elements"]),
    "height_change_reopened_tile": all(not blocked(27,30,sx,sy,state=after)
                                        for sx in range(4) for sy in range(4)),
    "height_change_preserved_ride": any(e["id"] == "openrct2:ride:" + str(source["ride_id"]) + "#1"
                                        for e in after["entities"]),
    "height_change_retained_xy": any(v["rect"]["x"] == 27*32 and v["rect"]["y"] == 30*32
                                     and v["base_z"] == 192 for e in after["entities"]
                                     if e["id"] == "openrct2:ride:" + str(source["ride_id"]) + "#1"
                                     for v in e["collision"]["volumes"]),
    "low_track_cause": any("track:0" in item for item in cause(27,30)),
    "station_cause": any("track:1" in item for item in cause(29,30)),
    "loop_cause": any("track:40" in item for item in cause(35,30)),
    "low_path_cause": any(item.startswith("path:") for item in cause(46,57)),
    "start_under_overhead_geometry": bool(start and 512 <= int(start[1]) < 544
                                          and 992 <= int(start[2]) < 1024
                                          and 1504 <= int(start[3]) < 1536
                                          and 1824 <= int(start[4]) < 1856),
    "marine_reached_destination": any(abs(mx-768) < 24 and abs(my-1008) < 24
                                       for _, mx, my, _, _ in samples),
    "zergling_moved": bool(start and end and (abs(int(end[3])-int(start[3]))
                                       + abs(int(end[4])-int(start[4]))) > 24),
    "real_overhead_actions": bool(end and end[5] == "true" and end[6] == "true"),
    "real_track_height_change": bool(end and end[7] == "true"),
    "real_ghost_preview": bool(end and end[8] == "true"
        and "LAYERED_LIVE_GHOST accepted=true ghost=true" in driver),
    "ghost_absent_from_authoritative_world": not any(
        any(c["x"] == 50 and c["y"] == 55 for c in e.get("geometry", {}).get("cells", []))
        for e in after["entities"]),
    "all_revisions_synchronized": len(patches) >= 3 and len({p[1] for p in patches[:2]}) == 1
        and patches[2][1] != patches[1][1] and patches[2][1] == after["hash"],
    "unchanged_native_mask": "unchanged=1" in server,
}
result = {"checks": checks, "initial_hash": initial.group(1) if initial else None,
          "patches": patches, "start": start.groups() if start else None,
          "end": end.groups() if end else None,
          "source_ride_id": source["ride_id"], "position_samples": len(samples),
          "focus_causes": {f"{x},{y}": cause(x,y) for x,y in ((27,30),(29,30),(35,30),(46,57))}}
(directory / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Layered navigation logs: %s\n' "$run_dir"
