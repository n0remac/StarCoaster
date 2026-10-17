#!/usr/bin/env bash
# Supply Depot and Factory placement through the existing two-client session.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
run_dir="$project_dir/run-data/next-buildings-live-$(date +%s)"
mkdir -p "$run_dir"
for building in terran_supply_depot terran_factory; do
  case "$building" in
    terran_supply_depot) native=Terran_Supply_Depot; hp=500 ;;
    terran_factory) native=Terran_Factory; hp=1250 ;;
  esac
  stage="$run_dir/$building"
  mkdir -p "$stage/server/plugin" "$stage/client/plugin"
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
  BRIDGE_MAP_FILE="$map_file" BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
    BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
    BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
    BRIDGE_SERVER_DATA_DIR="$stage/server" \
    timeout 110s scripts/run-world-session.sh "$park_file" > "$stage/server.log" 2>&1 &
  session_pid=$!
  started=$SECONDS
  until grep -q 'WORLD_READY' "$stage/server.log" 2>/dev/null; do
    if (( SECONDS - started > 75 )); then echo "World not ready: $stage" >&2; exit 1; fi
    sleep 1
  done
  openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
  build/openrct2/openrct2-cli join 127.0.0.1 --headless --port=11753 \
    --rct2-data-path="$RCT2_DATA_DIR" --openrct2-data-path="$openrct2_data" \
    --user-data-path="$stage/client" > "$stage/client.log" 2>&1 &
  client_pid=$!
  started=$SECONDS
  until grep -q "type=$native hp=$hp" "$stage/server.log" 2>/dev/null; do
    if (( SECONDS - started > 70 )); then echo "Native $native not created: $stage" >&2; exit 1; fi
    sleep 1
  done
  python3 - "$stage" "$building" "$native" "$hp" <<'PY'
import json, re, sys
from pathlib import Path
stage, building, native, hp = Path(sys.argv[1]), *sys.argv[2:]
server = (stage / "server.log").read_text(errors="replace")
client = (stage / "client.log").read_text(errors="replace")
matches = re.findall(r"\[world\] target id=(\S+) proxy=(\d+) type="
                     + re.escape(native) + r" hp=(\d+)", server)
checks = {
    "park_placement": f"NEXT_BUILD_PROBE_RESULT building={building} accepted=true" in client,
    "ordered_revision": "WORLD_PATCH_SYNC revision=2" in server,
    "one_native_building": len(matches) == 1 and matches[0][2] == hp,
    "persistent_identity": bool(matches and re.search(
        r"native target state id=" + re.escape(matches[0][0])
        + r" proxy=openbw:" + matches[0][1] + r" hp=" + hp, server)),
    "two_native_navigation_updates": server.count("navigation-mask hash=") >= 2,
}
(stage / "verification.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(building, json.dumps(checks))
if not all(checks.values()): raise SystemExit(1)
PY
  cleanup
  session_pid=""; client_pid=""
  trap - EXIT INT TERM
done
echo "Native construction evidence: $run_dir"
