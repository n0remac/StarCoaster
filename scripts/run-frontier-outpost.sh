#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scenario="$project_dir/scenarios/frontier-outpost.json"
park="$project_dir/run-data/frontier-playable/save/frontier-outpost-playable.park"
map_file="$project_dir/run-data/frontier-playable/map/frontier-outpost.scm"

refresh_park=0
if [[ ! -s "$park" || ! -s "$project_dir/run-data/frontier-playable/fixture.json" \
    || ! -s "$project_dir/run-data/frontier-playable/navigation-elements.json" ]]; then
    refresh_park=1
fi
for input in scripts/park-assault-generator.js scripts/create-park-assault.py scripts/park_navigation.py; do
    if [[ "$project_dir/$input" -nt "$park" ]]; then refresh_park=1; fi
done
if (( refresh_park )); then
    printf 'Generating Frontier Outpost: saved park is missing or older than its generator inputs.\n'
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
