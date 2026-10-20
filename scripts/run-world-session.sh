#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
park_file="${1:?Pass a saved OpenRCT2 park}"
test -f "$park_file" || { printf 'Missing park: %s\n' "$park_file" >&2; exit 1; }
test -x "$project_dir/build/world-bridge" || { printf 'Build the bridge with: go build -o build/world-bridge ./cmd/world-bridge\n' >&2; exit 1; }
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR to your RCT2 installation}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR to your StarCraft installation}"
wasm_bundle="${BRIDGE_WASM_BUNDLE:-${WASM_DEPLOY_DIR:-$project_dir/run-data/wasm-deploy}/current}"
if [[ "${BRIDGE_SERVE_WASM:-0}" == 1 ]]; then
    test -s "$wasm_bundle/manifest.json" || { printf 'Missing deployed WASM bundle: %s\n' "$wasm_bundle" >&2; exit 1; }
fi
python3 - "${OPENRCT2_PORT:-11753}" "${STARCOASTER_BRIDGE_PORT:-40010}" "${BRIDGE_OPENBW_PORT:-40011}" "${BRIDGE_CONTROLLER_PORT:-40012}" <<'PY'
import socket
import sys

for port in (int(value) for value in sys.argv[1:]):
    with socket.socket() as probe:
        # Go listeners set SO_REUSEADDR. Allow their recently closed sockets
        # to leave TIME_WAIT while still rejecting an active listener.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"StarCoaster session port {port} is already in use; stop the other session before launching a new park")
PY

export BRIDGE_SCENARIO=world
export OPENBW_LAN_MODE=LOCAL
runtime_root="${BRIDGE_RUNTIME_DIR:-$project_dir/run-data/world-base}"
if [[ -n "${BRIDGE_SPAWN_JOURNAL:-}" ]]; then runtime_root="${BRIDGE_RUNTIME_DIR:-$(dirname "$BRIDGE_SPAWN_JOURNAL")}"; fi
mkdir -p "$runtime_root"
export OPENBW_LOCAL_PATH="${OPENBW_LOCAL_PATH:-$runtime_root/openbw-local.socket}"
mkdir -p "$(dirname "$OPENBW_LOCAL_PATH")"
rm -f "$OPENBW_LOCAL_PATH"
if [[ ! -f "$project_dir/run-data/world-base/world-base-v5-256.scm" ]]; then
  python3 "$project_dir/scripts/create-world-base-map.py" \
    --output "$project_dir/run-data/world-base/world-base-v5-256.scm"
fi
bridge_args=()
bridge_args+=(--park "127.0.0.1:${STARCOASTER_BRIDGE_PORT:-40010}")
bridge_args+=(--openbw "127.0.0.1:${BRIDGE_OPENBW_PORT:-40011}")
bridge_args+=(--controller "127.0.0.1:${BRIDGE_CONTROLLER_PORT:-40012}")
if [[ -n "${BRIDGE_SCENARIO_CONFIG:-}" ]]; then bridge_args+=(--scenario "$BRIDGE_SCENARIO_CONFIG"); fi
if [[ -n "${BRIDGE_SCENARIO_CONFIG:-}" ]]; then
  export BRIDGE_UNLIMITED_TERRAN_RESOURCES="$(python3 - "$BRIDGE_SCENARIO_CONFIG" <<'PY'
import json, sys
print('1' if json.load(open(sys.argv[1], encoding='utf-8')).get('unlimited_resources') else '0')
PY
)"
  export BRIDGE_TERRAN_STARTING_MINERALS="$(python3 - "$BRIDGE_SCENARIO_CONFIG" <<'PY'
import json, sys
scenario = json.load(open(sys.argv[1], encoding="utf-8"))
print(scenario.get("production_fixture", {}).get("terran_minerals", 0))
PY
)"
  export BRIDGE_TERRAN_STARTING_GAS="$(python3 - "$BRIDGE_SCENARIO_CONFIG" <<'PY'
import json, sys
fixture = json.load(open(sys.argv[1], encoding="utf-8")).get("production_fixture", {})
print(fixture["terran_gas"] if "terran_gas" in fixture else "")
PY
)"
  export BRIDGE_ZERG_STARTING_MINERALS="$(python3 - "$BRIDGE_SCENARIO_CONFIG" <<'PY'
import json, sys
fixture = json.load(open(sys.argv[1], encoding="utf-8")).get("production_fixture", {})
print(fixture["zerg_minerals"] if "zerg_minerals" in fixture else "")
PY
)"
  export BRIDGE_ZERG_STARTING_GAS="$(python3 - "$BRIDGE_SCENARIO_CONFIG" <<'PY'
import json, sys
fixture = json.load(open(sys.argv[1], encoding="utf-8")).get("production_fixture", {})
print(fixture["zerg_gas"] if "zerg_gas" in fixture else "")
PY
)"
fi
if [[ -n "${BRIDGE_RULES_CONFIG:-}" ]]; then bridge_args+=(--rules "$BRIDGE_RULES_CONFIG"); fi
if [[ -n "${BRIDGE_SPAWN_JOURNAL:-}" ]]; then bridge_args+=(--spawn-journal "$BRIDGE_SPAWN_JOURNAL"); fi
"$project_dir/build/world-bridge" "${bridge_args[@]}" &
bridge_pid=$!
(
  export BRIDGE_BWAPI_MENU=MULTI_PLAYER BRIDGE_BWAPI_SLOT=0 BRIDGE_BWAPI_RACE=Zerg
  export BRIDGE_WORLD_ROLE=publisher
  export BRIDGE_BWAPI_RUNTIME_DIR="$runtime_root/openbw-zerg"
  exec "$project_dir/scripts/run-bwapi.sh"
) &
bw_pid=$!
(
  export BRIDGE_BWAPI_MENU=MULTI_PLAYER BRIDGE_BWAPI_SLOT=1 BRIDGE_BWAPI_RACE=Terran
  export BRIDGE_WORLD_ROLE=controller
  export BRIDGE_BWAPI_RUNTIME_DIR="$runtime_root/openbw-terran"
  exec "$project_dir/scripts/run-bwapi.sh"
) &
controller_pid=$!
"$project_dir/scripts/run-openrct2-host.sh" "$park_file" &
park_pid=$!
wasm_pid=""
if [[ "${BRIDGE_SERVE_WASM:-0}" == 1 ]]; then
    wasm_log="${BRIDGE_WASM_LOG_FILE:-$runtime_root/wasm-server.log}"
    mkdir -p "$(dirname "$wasm_log")"
    "$project_dir/scripts/serve-wasm.sh" --bundle "$wasm_bundle" \
        --listen "${WASM_LISTEN_ADDRESS:-127.0.0.1:8091}" \
        --native "127.0.0.1:${OPENRCT2_PORT:-11753}" \
        --rct2-data-path "$(realpath "$RCT2_DATA_DIR")" >> "$wasm_log" 2>&1 &
    wasm_pid=$!
fi
client_pid=""
if [[ "${BRIDGE_LAUNCH_CLIENT:-0}" == 1 ]]; then
    : "${DISPLAY:?A graphical DISPLAY is required for BRIDGE_LAUNCH_CLIENT=1}"
    port="${OPENRCT2_PORT:-11753}"
    for attempt in $(seq 1 100); do
        if (: > "/dev/tcp/127.0.0.1/$port") 2>/dev/null; then break; fi
        sleep 0.2
    done
    client_data="${BRIDGE_CLIENT_DATA_DIR:-$project_dir/run-data/world-base/openrct2-client}"
    mkdir -p "$client_data/plugin" "$client_data/object"
    for object in "$project_dir"/build/openrct2-stage/usr/local/share/openrct2/object/starcoaster/scenery_large/*.parkobj; do
        test -f "$object" || continue
        cp "$object" "$client_data/object/$(basename "$object")"
    done
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
    trap - EXIT INT TERM
    local pids=("$park_pid" "$bw_pid" "$controller_pid" "$bridge_pid")
    if [[ -n "$client_pid" ]]; then pids+=("$client_pid"); fi
    if [[ -n "$wasm_pid" ]]; then pids+=("$wasm_pid"); fi
    kill "${pids[@]}" 2>/dev/null || true
    for (( attempt = 0; attempt < 50; attempt++ )); do
        local active=0
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then active=1; break; fi
        done
        if (( !active )); then break; fi
        sleep 0.1
    done
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; fi
    done
    wait "${pids[@]}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
# A bridge restart must not tear down either authoritative engine.
wait_pids=("$park_pid" "$bw_pid" "$controller_pid")
if [[ -n "$client_pid" ]]; then wait_pids+=("$client_pid"); fi
if [[ -n "$wasm_pid" ]]; then wait_pids+=("$wasm_pid"); fi
wait -n "${wait_pids[@]}"
