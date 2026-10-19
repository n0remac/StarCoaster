#!/usr/bin/env bash
# Keep private browser hosting available before a game is selected.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
park_dir="${BRIDGE_PARK_LIBRARY:-$project_dir/run-data/pi-park-library}"
mkdir -p "$park_dir"
exec python3 scripts/park_session_supervisor.py --parks "$park_dir" \
    --runtime "$project_dir/run-data/park-supervisor"
