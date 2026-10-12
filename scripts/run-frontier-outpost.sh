#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scenario="$project_dir/scenarios/frontier-outpost.json"
park="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"

if [[ ! -s "$park" ]]; then
    python3 "$project_dir/scripts/create-park-assault.py" --playable >/dev/null
fi
mkdir -p "$(dirname "$map_file")"
python3 "$project_dir/scripts/create-world-base-map.py" --scenario "$scenario" --output "$map_file"
export BRIDGE_MAP_FILE="$map_file"
export BRIDGE_SCENARIO_CONFIG="$scenario"
export BRIDGE_RULES_CONFIG="$project_dir/scenarios/frontier-outpost-mapping.json"
export BRIDGE_SERVER_DATA_DIR="$project_dir/run-data/frontier-playable/server"
export BRIDGE_CLIENT_DATA_DIR="$project_dir/run-data/frontier-playable/client"
export BRIDGE_LAUNCH_CLIENT="${BRIDGE_LAUNCH_CLIENT:-$(if [[ -n "${DISPLAY:-}" ]]; then printf 1; else printf 0; fi)}"
exec "$project_dir/scripts/run-world-session.sh" "$park"
