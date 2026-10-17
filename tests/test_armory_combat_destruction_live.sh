#!/usr/bin/env bash
# Exercise native combat damage and ordered removal of a supported Armory.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STARCOASTER_TEST_ARMORY_COMBAT=1 exec "$project_dir/tests/test_armory_goliath_gameplay_live.sh"
