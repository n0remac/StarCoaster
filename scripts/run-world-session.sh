#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
park_file="${1:?Pass a saved OpenRCT2 park}"
test -f "$park_file" || { printf 'Missing park: %s\n' "$park_file" >&2; exit 1; }
test -x "$project_dir/build/world-bridge" || { printf 'Build the bridge with: go build -o build/world-bridge ./cmd/world-bridge\n' >&2; exit 1; }
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR to your RCT2 installation}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR to your StarCraft installation}"

export BRIDGE_SCENARIO=world
export OPENBW_LAN_MODE=LOCAL
export OPENBW_LOCAL_PATH="${OPENBW_LOCAL_PATH:-$project_dir/run-data/world-base/openbw-local.socket}"
mkdir -p "$(dirname "$OPENBW_LOCAL_PATH")"
rm -f "$OPENBW_LOCAL_PATH"
if [[ ! -f "$project_dir/run-data/world-base/world-base-v4.scm" ]]; then
  python3 "$project_dir/scripts/create-world-base-map.py" \
    --output "$project_dir/run-data/world-base/world-base-v4.scm"
fi
"$project_dir/build/world-bridge" &
bridge_pid=$!
(
  export BRIDGE_BWAPI_MENU=MULTI_PLAYER BRIDGE_BWAPI_SLOT=0 BRIDGE_BWAPI_RACE=Zerg
  export BRIDGE_WORLD_ROLE=publisher
  export BRIDGE_BWAPI_RUNTIME_DIR="$project_dir/run-data/world-base/openbw-zerg"
  exec "$project_dir/scripts/run-bwapi.sh"
) &
bw_pid=$!
(
  export BRIDGE_BWAPI_MENU=MULTI_PLAYER BRIDGE_BWAPI_SLOT=1 BRIDGE_BWAPI_RACE=Terran
  export BRIDGE_WORLD_ROLE=controller
  export BRIDGE_BWAPI_RUNTIME_DIR="$project_dir/run-data/world-base/openbw-terran"
  exec "$project_dir/scripts/run-bwapi.sh"
) &
controller_pid=$!
"$project_dir/scripts/run-openrct2-host.sh" "$park_file" &
park_pid=$!

cleanup() {
    kill "$park_pid" "$bw_pid" "$controller_pid" "$bridge_pid" 2>/dev/null || true
    wait "$park_pid" "$bw_pid" "$controller_pid" "$bridge_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
# A bridge restart must not tear down either authoritative engine.
wait -n "$park_pid" "$bw_pid" "$controller_pid"
