#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$project_dir/scripts/check-dependencies.py"

# OpenRCT2's download install rules use DESTDIR at configure time. Stage all
# downloaded open assets and binaries on the attached drive, never /usr/local.
DESTDIR="$project_dir/build/openrct2-stage" \
  cmake --install "$project_dir/build/openrct2"
