#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jobs="${BRIDGE_BUILD_JOBS:-2}"

"$project_dir/scripts/check-dependencies.py"

cmake -S "$project_dir/openbw-bwapi-module" -B "$project_dir/build/bridge-module" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBWAPI_SOURCE_DIR="$project_dir/upstream/bwapi" \
  -DBWAPI_BUILD_DIR="$project_dir/build/bwapi"
cmake --build "$project_dir/build/bridge-module" --parallel "$jobs"
