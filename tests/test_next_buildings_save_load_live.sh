#!/usr/bin/env bash
# Real park save/load restores player-built Depot and Factory in both engines.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
run_dir="$project_dir/run-data/next-buildings-save-load-$(date +%s)"
mkdir -p "$run_dir"
for building in terran_supply_depot terran_factory; do
  case "$building" in
    terran_supply_depot) native=Terran_Supply_Depot; hp=500 ;;
    terran_factory) native=Terran_Factory; hp=1250 ;;
  esac
  stage="$run_dir/$building"
  mkdir -p "$stage/server/plugin" "$stage/client/plugin" "$stage/reload-server"
  cp scripts/live-next-building-save-probe.js "$stage/server/plugin/"
  sed "s/__BUILDING__/$building/g" scripts/live-next-building-probe.js \
    > "$stage/client/plugin/live-next-building-probe.js"
  cp openrct2-plugin/rts-bridge.js "$stage/client/plugin/"
  map_file="$stage/mt-zergling.scm"
  python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json \
    --output "$map_file" >/dev/null
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
    until grep -Eq "$pattern" "$file" 2>/dev/null; do
      if (( SECONDS - started > limit )); then
        echo "Timed out waiting for $pattern: $stage" >&2
        return 1
      fi
      sleep 1
    done
  }
  BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
    BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
    BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
    BRIDGE_SERVER_DATA_DIR="$stage/server" \
    timeout 130s scripts/run-world-session.sh "$park_file" > "$stage/build.log" 2>&1 &
  session_pid=$!
  wait_for 'WORLD_READY' "$stage/build.log" 75
  openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$stage/client" > "$stage/client.log" 2>&1 &
  client_pid=$!
  wait_for 'NEXT_BUILDING_SAVE_SAVED' "$stage/build.log" 75
  saved="$stage/server/save/next-building-recovery.park"
  test -s "$saved"
  cleanup
  session_pid=""; client_pid=""
  BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
    BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
    BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
    BRIDGE_SERVER_DATA_DIR="$stage/reload-server" \
    timeout 110s scripts/run-world-session.sh "$saved" > "$stage/reload.log" 2>&1 &
  session_pid=$!
  wait_for 'WORLD_READY.*targets=3' "$stage/reload.log" 80
  python3 - "$stage" "$building" "$native" "$hp" <<'PY'
import json, re, sys
from pathlib import Path
stage, building, native, hp = Path(sys.argv[1]), *sys.argv[2:]
build = (stage/'build.log').read_text(errors='replace')
reload = (stage/'reload.log').read_text(errors='replace')
client = (stage/'client.log').read_text(errors='replace')
pattern = r'\[world\] target id=(openrct2:large_scenery:\d+:\d+:\d+:\d+:0#\d+) proxy=\d+ type='+native+r' hp='+hp
before, after = re.findall(pattern, build), re.findall(pattern, reload)
checks = {
    'placed_through_park': f'NEXT_BUILD_PROBE_RESULT building={building} accepted=true' in client,
    'confirmed_revision': 'WORLD_PATCH_SYNC revision=2' in build,
    'saved_real_park': (stage/'server/save/next-building-recovery.park').stat().st_size > 0,
    'identity_and_native_hp_restored': len(before)==1 and len(after)==1 and before[0]==after[0],
    'two_native_participants_ready': bool(re.search(r'WORLD_READY entities=\d+ targets=3', reload)),
    'no_duplicate_native_building': len(after)==1,
}
(stage/'verification.json').write_text(json.dumps({'checks':checks,'before':before,'after':after},indent=2)+'\n')
print(building, json.dumps(checks))
if not all(checks.values()): raise SystemExit(1)
PY
  cleanup
  session_pid=""; client_pid=""
  trap - EXIT INT TERM
done
echo "Depot and Factory save/load evidence: $run_dir"
