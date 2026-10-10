#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$project_dir/upstream/openrct2"
patch="$project_dir/openrct2-patches/0001-m1-paint-probe.patch"

if git -C "$source_dir" apply --reverse --check "$patch" 2>/dev/null; then
  printf 'OpenRCT2 M1 paint patch already applied\n'
else
  git -C "$source_dir" apply --check "$patch"
  git -C "$source_dir" apply "$patch"
  printf 'Applied OpenRCT2 M1 paint patch\n'
fi

mkdir -p "$source_dir/resources/g2/bridge"
cp "$project_dir"/assets/alien-scout/sprites/*.png "$source_dir/resources/g2/bridge/"
