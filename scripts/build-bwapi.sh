#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jobs="${BRIDGE_BUILD_JOBS:-2}"

"$project_dir/scripts/check-dependencies.py"

auto_menu="$project_dir/upstream/bwapi/bwapi/BWAPI/Source/BWAPI/AutoMenuManager.cpp"
if ! grep -q 'player_slot' "$auto_menu"; then
  git -C "$project_dir/upstream/bwapi" apply --check "$project_dir/openbw-bwapi-module/0001-player-slot.patch"
  git -C "$project_dir/upstream/bwapi" apply "$project_dir/openbw-bwapi-module/0001-player-slot.patch"
fi

# Native park collision is patched into OpenBW's VF4 mini-tiles and BWAPI's
# narrow game interface. Both repositories are separate upstream checkouts.
if ! grep -q 'set_park_navigation' "$project_dir/upstream/openbw/bwgame.h"; then
  git -C "$project_dir/upstream/openbw" apply --check "$project_dir/openbw-bwapi-module/0002-native-navigation-openbw.patch"
  git -C "$project_dir/upstream/openbw" apply "$project_dir/openbw-bwapi-module/0002-native-navigation-openbw.patch"
fi
if ! grep -q 'setParkNavigation' "$project_dir/upstream/bwapi/bwapi/OpenBWData/BW/BWData.h"; then
  git -C "$project_dir/upstream/bwapi" apply --check "$project_dir/openbw-bwapi-module/0003-native-navigation-bwapi.patch"
  git -C "$project_dir/upstream/bwapi" apply "$project_dir/openbw-bwapi-module/0003-native-navigation-bwapi.patch"
fi

cmake -S "$project_dir/upstream/bwapi" -B "$project_dir/build/bwapi" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPENBW_DIR="$project_dir/upstream/openbw" \
  -DOPENBW_ENABLE_UI=OFF
cmake --build "$project_dir/build/bwapi" --parallel "$jobs"
