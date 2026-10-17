#!/usr/bin/env bash
# Both new building footprints must roll back when a native Marine occupies them.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for building in terran_supply_depot terran_factory; do
  OVERLAP_BUILDING="$building" bash "$project_dir/tests/test_barracks_overlap_live.sh"
done
