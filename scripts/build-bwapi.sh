#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jobs="${BRIDGE_BUILD_JOBS:-2}"

"$project_dir/scripts/check-dependencies.py"

# Verify patch contents so an older function with the same name is upgraded.
python3 "$project_dir/scripts/apply-bwapi-patches.py"

cmake -S "$project_dir/upstream/bwapi" -B "$project_dir/build/bwapi" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPENBW_DIR="$project_dir/upstream/openbw" \
  -DOPENBW_ENABLE_UI=OFF
cmake --build "$project_dir/build/bwapi" --parallel "$jobs"
