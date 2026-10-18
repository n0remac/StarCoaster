#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jobs="${BRIDGE_BUILD_JOBS:-2}"

"$project_dir/scripts/check-dependencies.py"
"$project_dir/scripts/apply-openrct2-patches.sh"

cmake -S "$project_dir/upstream/openrct2" -B "$project_dir/build/openrct2" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DENABLE_SCRIPTING=ON \
  -DDISABLE_NETWORK=OFF \
  -DDISABLE_GUI=OFF
cmake --build "$project_dir/build/openrct2" --parallel "$jobs"

# Launchers use the locally installed data, including g2.dat. Keep an existing
# installation in step with rebuilt sprite IDs and binaries.
if [[ -d "$project_dir/build/openrct2-stage/usr/local/share/openrct2" ]]; then
  "$project_dir/scripts/install-openrct2-local.sh"
fi
