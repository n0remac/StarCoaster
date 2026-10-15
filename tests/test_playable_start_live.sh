#!/usr/bin/env bash
# Exercise the normal playable launcher with its own graphical client.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
for tool in Xvfb ffmpeg pkill; do
  command -v "$tool" >/dev/null || { printf 'Missing live graphical test tool: %s\n' "$tool" >&2; exit 1; }
done
run_dir="$project_dir/run-data/playable-start-$(date +%s)"
mkdir -p "$run_dir"
display_num=90
while [[ -e "/tmp/.X11-unix/X$display_num" ]]; do ((display_num += 1)); done
Xvfb ":$display_num" -screen 0 1280x800x24 -nolisten tcp > "$run_dir/display.log" 2>&1 &
display_pid=$!
session_pid=""
cleanup() {
  if [[ -n "$session_pid" ]]; then pkill -TERM -P "$session_pid" 2>/dev/null || true; fi
  sleep 1
  if [[ -n "$session_pid" ]]; then pkill -KILL -P "$session_pid" 2>/dev/null || true; fi
  if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; fi
  if [[ -n "$session_pid" ]]; then wait "$session_pid" 2>/dev/null || true; fi
  kill "$display_pid" 2>/dev/null || true
  wait "$display_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
export DISPLAY=":$display_num"
for attempt in $(seq 1 100); do
  if [[ -S "/tmp/.X11-unix/X$display_num" ]]; then break; fi
  kill -0 "$display_pid" 2>/dev/null || { cat "$run_dir/display.log" >&2; exit 1; }
  sleep 0.1
done
test -S "/tmp/.X11-unix/X$display_num"
# Xvfb can publish its socket before the screen is ready for OpenRCT2's
# graphical client on slower hosts.
sleep 2
launcher=(scripts/project.sh play frontier-outpost)
ready_limit=75
if [[ "${PLAYABLE_FULL_START:-0}" == 1 ]]; then
  launcher=(scripts/start.sh --client)
  ready_limit=300
fi
BRIDGE_LAUNCH_CLIENT=1 BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  BRIDGE_CLIENT_DATA_DIR="$run_dir/client" BRIDGE_CLIENT_LOG_FILE="$run_dir/client.log" \
  OPENBW_LOCAL_PATH="$run_dir/openbw-local.socket" \
  "${launcher[@]}" > "$run_dir/session.log" 2>&1 &
session_pid=$!
wait_for() {
  local pattern="$1" file="$2" limit="$3" started=$SECONDS
  while ! grep -Eq "$pattern" "$file" 2>/dev/null; do
    if (( SECONDS - started >= limit )); then
      printf 'Timed out waiting for %s in %s\n' "$pattern" "$file" >&2
      return 1
    fi
    if ! kill -0 "$session_pid" 2>/dev/null; then
      printf 'Playable session stopped before %s; see %s\n' "$pattern" "$run_dir/session.log" >&2
      return 1
    fi
    sleep 1
  done
}
wait_for 'WORLD_READY.*navigation=native' "$run_dir/session.log" "$ready_limit"
wait_for 'scenario spawn request=.*opening-zerg-wave state=ready' "$run_dir/session.log" 60
wait_for 'RTS Bridge apply tick=.*openbw:3005' "$run_dir/client.log" 60
ffmpeg -loglevel error -y -f x11grab -video_size 1280x800 -i "$DISPLAY" \
  -frames:v 1 "$run_dir/screen.png"
python3 - "$run_dir" <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path(sys.argv[1])
client = (root / "client.log").read_text(errors="replace")
server = (root / "session.log").read_text(errors="replace")
snapshots = re.findall(r"RTS Bridge apply tick=[^\n]*units=([^\n]+)", client)
expected = {f"openbw:{n}" for n in range(1000, 1006)}
expected |= {f"openbw:{n}" for n in range(2000, 2012)}
expected |= {f"openbw:{n}" for n in range(3001, 3006)}
seen = set()
for snapshot in snapshots:
    seen.update(re.findall(r"openbw:\d+", snapshot))
checks = {
    "graphical_client_bridge_installed": (root / "client/plugin/rts-bridge.js").read_text().startswith(
        "/* Passthrough RTS Bridge"),
    "native_world_ready": "WORLD_READY" in server and "navigation=native" in server,
    "six_starting_marines_visible": {f"openbw:{n}" for n in range(1000, 1006)} <= seen,
    "twelve_starting_zerglings_visible": {f"openbw:{n}" for n in range(2000, 2012)} <= seen,
    "automatic_wave_visible": {f"openbw:{n}" for n in range(3001, 3006)} <= seen,
    "graphical_capture": (root / "screen.png").stat().st_size > 0,
}
if os.environ.get("PLAYABLE_FULL_START") == "1":
    pack = os.environ.get("BRIDGE_SPRITE_SOURCE") or "starcraft-local"
    checks["selected_sprite_pack"] = "Unit sprites: " + pack in server
    if pack == "starcraft-local":
        from PIL import Image
        project = Path.cwd()
        staged = project / "upstream/openrct2/resources/g2/bridge"
        entries = json.loads((project / "upstream/openrct2/resources/g2/sprites.json").read_text())
        sprite_indices = {entry.get("path"): index for index, entry in enumerate(entries)}
        asset_pack = project / "build/openrct2-stage/usr/local/share/openrct2/g2.dat"
        for unit in ("marine", "zergling"):
            source = project / "run-data/generated-assets/starcraft" / unit
            frames = json.loads((source / "manifest.json").read_text())["frames"]
            checks[unit + "_starcraft_frames_staged"] = all(
                (source / name).read_bytes() == (staged / ("marine" if unit == "marine" else "") / name).read_bytes()
                for name in frames)
            name = "idle0_east.png" if unit == "marine" else "idle_east.png"
            resource = "bridge/" + ("marine/" if unit == "marine" else "") + name
            exported = root / ("compiled-" + unit + ".png")
            subprocess.run([str(project / "build/openrct2/openrct2-cli"), "sprite", "export",
                            str(asset_pack), str(sprite_indices[resource]), str(exported)],
                           check=True, stdout=subprocess.DEVNULL)
            with Image.open(source / name) as expected, Image.open(exported) as compiled:
                checks[unit + "_compiled_sprite_matches_source"] = (
                    expected.size == compiled.size
                    and expected.convert("RGBA").tobytes() == compiled.convert("RGBA").tobytes())
        checks["rebuilt_asset_pack_installed"] = (
            project / "build/openrct2/g2.dat").read_bytes() == asset_pack.read_bytes()
report = {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
          "observed_actor_ids": sorted(seen), "client_snapshot_count": len(snapshots)}
(root / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
printf 'Playable launcher logs: %s\n' "$run_dir"
