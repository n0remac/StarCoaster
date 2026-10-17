#!/usr/bin/env bash
# Reuse the native occupied-geometry rollback check for Academy's 3x2 footprint.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAP_BUILDING=terran_academy exec "$project_dir/tests/test_barracks_overlap_live.sh"
