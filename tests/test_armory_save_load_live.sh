#!/usr/bin/env bash
# Reuse the generalized building save/load fixture with the Armory catalog type.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STARCOASTER_BUILDING_TYPE=armory exec "$project_dir/tests/test_academy_save_load_live.sh"
