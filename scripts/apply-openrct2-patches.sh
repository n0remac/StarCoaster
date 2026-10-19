#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$project_dir/upstream/openrct2"
python3 "$project_dir/scripts/apply-openrct2-patches.py"

source_name="${BRIDGE_SPRITE_SOURCE:-starcraft-local}"
case "$source_name" in
  alien-scout) sprite_dir="$project_dir/assets/alien-scout/sprites" ;;
  starcraft-local) sprite_dir="$project_dir/run-data/generated-assets/starcraft/zergling" ;;
  *) printf 'Unknown BRIDGE_SPRITE_SOURCE: %s\n' "$source_name" >&2; exit 1 ;;
esac
python3 "$project_dir/scripts/install-bridge-sprites.py" "$sprite_dir" "$source_dir" "$source_name"
