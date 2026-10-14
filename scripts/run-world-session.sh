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
if [[ ! -f "$project_dir/run-data/world-base/world-base-v5-256.scm" ]]; then
  python3 "$project_dir/scripts/create-world-base-map.py" \
    --output "$project_dir/run-data/world-base/world-base-v5-256.scm"
fi
bridge_args=()
if [[ -n "${BRIDGE_SCENARIO_CONFIG:-}" ]]; then bridge_args+=(--scenario "$BRIDGE_SCENARIO_CONFIG"); fi
if [[ -n "${BRIDGE_RULES_CONFIG:-}" ]]; then bridge_args+=(--rules "$BRIDGE_RULES_CONFIG"); fi
if [[ -n "${BRIDGE_SPAWN_JOURNAL:-}" ]]; then bridge_args+=(--spawn-journal "$BRIDGE_SPAWN_JOURNAL"); fi
"$project_dir/build/world-bridge" "${bridge_args[@]}" &
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
client_pid=""
if [[ "${BRIDGE_LAUNCH_CLIENT:-0}" == 1 ]]; then
    : "${DISPLAY:?A graphical DISPLAY is required for BRIDGE_LAUNCH_CLIENT=1}"
    port="${OPENRCT2_PORT:-11753}"
    for attempt in $(seq 1 100); do
        if (: > "/dev/tcp/127.0.0.1/$port") 2>/dev/null; then break; fi
        sleep 0.2
    done
    client_data="${BRIDGE_CLIENT_DATA_DIR:-$project_dir/run-data/world-base/openrct2-client}"
    mkdir -p "$client_data/plugin"
    cp "$project_dir/openrct2-plugin/rts-bridge.js" "$client_data/plugin/rts-bridge.js"
    client_command=("$project_dir/build/openrct2/openrct2" join 127.0.0.1 --port="$port"
      --rct2-data-path="$(realpath "$RCT2_DATA_DIR")"
      --openrct2-data-path="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
      --user-data-path="$client_data")
    if [[ -n "${BRIDGE_CLIENT_LOG_FILE:-}" ]]; then
        "${client_command[@]}" > "$BRIDGE_CLIENT_LOG_FILE" 2>&1 &
    else
        "${client_command[@]}" &
    fi
    client_pid=$!
fi

cleanup() {
    if [[ -n "$client_pid" ]]; then kill "$client_pid" 2>/dev/null || true; fi
    kill "$park_pid" "$bw_pid" "$controller_pid" "$bridge_pid" 2>/dev/null || true
    if [[ -n "$client_pid" ]]; then wait "$client_pid" 2>/dev/null || true; fi
    wait "$park_pid" "$bw_pid" "$controller_pid" "$bridge_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
# A bridge restart must not tear down either authoritative engine.
if [[ -n "$client_pid" ]]; then
    wait -n "$park_pid" "$bw_pid" "$controller_pid" "$client_pid"
else
    wait -n "$park_pid" "$bw_pid" "$controller_pid"
fi
