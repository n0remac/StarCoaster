#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
park_file="${1:?Pass a saved OpenRCT2 park}"
test -f "$park_file" || { printf 'Missing park: %s\n' "$park_file" >&2; exit 1; }
test -x "$project_dir/build/world-bridge" || { printf 'Build the bridge with: go build -o build/world-bridge ./cmd/world-bridge\n' >&2; exit 1; }
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR to your RCT2 installation}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR to your StarCraft installation}"

export BRIDGE_SCENARIO=world
"$project_dir/build/world-bridge" &
bridge_pid=$!
"$project_dir/scripts/run-bwapi.sh" &
bw_pid=$!
"$project_dir/scripts/run-openrct2-host.sh" "$park_file" &
park_pid=$!

cleanup() {
    kill "$park_pid" "$bw_pid" "$bridge_pid" 2>/dev/null || true
    wait "$park_pid" "$bw_pid" "$bridge_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait -n "$park_pid" "$bw_pid" "$bridge_pid"
