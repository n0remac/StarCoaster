#!/usr/bin/env bash
# Reuse the generalized same-session building reconciliation fixture.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STARCOASTER_BUILDING_TYPE=armory exec "$project_dir/tests/test_academy_bridge_restart_live.sh"
