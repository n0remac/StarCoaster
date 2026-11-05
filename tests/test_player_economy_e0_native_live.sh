#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/player-economy-e0-$(date +%s)"
mkdir -p "$run_dir"
python3 tests/create_player_economy_e0_map.py --output "$run_dir/economy-e0.scm"
read -r OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT < <(
    python3 - <<'PY'
import socket
sockets=[]
for _ in range(4):
    sock=socket.socket(); sock.bind(('127.0.0.1', 0)); sockets.append(sock)
print(*(sock.getsockname()[1] for sock in sockets))
PY
)
export OPENRCT2_PORT STARCOASTER_BRIDGE_PORT BRIDGE_OPENBW_PORT BRIDGE_CONTROLLER_PORT
session_pid=""; restarted_bridge_pid=""
cleanup() {
    trap - EXIT INT TERM
    if [[ -n "$restarted_bridge_pid" ]]; then
        kill "$restarted_bridge_pid" 2>/dev/null || true
        wait "$restarted_bridge_pid" 2>/dev/null || true
    fi
    if [[ -n "$session_pid" ]]; then
        kill "$session_pid" 2>/dev/null || true
        wait "$session_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_ECONOMY_E0=1 BRIDGE_MAP_FILE="$run_dir/economy-e0.scm" \
    BRIDGE_TERRAN_STARTING_MINERALS=400 BRIDGE_TERRAN_STARTING_GAS=0 \
    BRIDGE_UNLIMITED_TERRAN_RESOURCES=0 BRIDGE_DISABLE_ASSAULT_AI=1 \
    BRIDGE_FRAME_MS=10 BRIDGE_LAUNCH_CLIENT=0 \
    BRIDGE_RUNTIME_DIR="$run_dir/native" BRIDGE_SERVER_DATA_DIR="$run_dir/park" \
    BRIDGE_TEST_BRIDGE_PID_FILE="$run_dir/bridge.pid" \
    timeout 240s scripts/run-world-session.sh \
        "$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park" \
        > "$run_dir/session.log" 2>&1 &
session_pid=$!
wait_for() {
    local pattern="$1" limit="$2" start=$SECONDS
    until grep -Eq "$pattern" "$run_dir/session.log" 2>/dev/null; do
        if (( SECONDS - start >= limit )); then
            printf 'Timed out waiting for %s; evidence: %s\n' "$pattern" "$run_dir" >&2
            return 1
        fi
        if ! kill -0 "$session_pid" 2>/dev/null; then
            printf 'Session exited before %s; evidence: %s\n' "$pattern" "$run_dir" >&2
            return 1
        fi
        sleep 1
    done
}
wait_for 'stage=depot_complete ' 130
bridge_pid="$(cat "$run_dir/bridge.pid")"
kill "$bridge_pid"
sleep 1
build/world-bridge --park "127.0.0.1:$STARCOASTER_BRIDGE_PORT" \
    --openbw "127.0.0.1:$BRIDGE_OPENBW_PORT" \
    --controller "127.0.0.1:$BRIDGE_CONTROLLER_PORT" \
    >> "$run_dir/session.log" 2>&1 &
restarted_bridge_pid=$!
printf 'original_pid=%s restarted_pid=%s\n' "$bridge_pid" "$restarted_bridge_pid" \
    > "$run_dir/bridge-restart.txt"
wait_for 'stage=geyser_restored ' 90
python3 tests/verify_player_economy_e0_native.py "$run_dir"
printf 'E0 native evidence: %s\n' "$run_dir"
