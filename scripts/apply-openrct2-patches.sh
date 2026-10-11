#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$project_dir/upstream/openrct2"
patch="$project_dir/openrct2-patches/0001-native-bridge.patch"

if grep -q 'SPR_BRIDGE_HEALTH_MARINE_0' "$source_dir/src/openrct2/SpriteIds.h" \
    && grep -q '"version", JS_NewInt32(ctx, 4)' "$source_dir/src/openrct2/scripting/ScriptEngine.cpp"; then
  printf 'OpenRCT2 native bridge patch already applied\n'
elif grep -q 'SPR_BRIDGE_SCOUT_IDLE_EAST' "$source_dir/src/openrct2/SpriteIds.h"; then
  printf 'Older native bridge patch found; restore the pinned OpenRCT2 checkout before applying the current patch\n' >&2
  exit 1
else
  git -C "$source_dir" apply --check "$patch"
  git -C "$source_dir" apply "$patch"
  printf 'Applied OpenRCT2 native bridge patch\n'
fi

source_name="${BRIDGE_SPRITE_SOURCE:-alien-scout}"
case "$source_name" in
  alien-scout) sprite_dir="$project_dir/assets/alien-scout/sprites" ;;
  starcraft-local) sprite_dir="$project_dir/run-data/generated-assets/starcraft/zergling" ;;
  *) printf 'Unknown BRIDGE_SPRITE_SOURCE: %s\n' "$source_name" >&2; exit 1 ;;
esac
python3 "$project_dir/scripts/install-bridge-sprites.py" "$sprite_dir" "$source_dir" "$source_name"
