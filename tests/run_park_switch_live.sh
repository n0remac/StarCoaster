#!/usr/bin/env bash
# Keep the live park-switch check isolated from the active Pi game listener.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ "${STARCOASTER_IN_NETNS:-0}" != 1 ]]; then
    exec env STARCOASTER_IN_NETNS=1 unshare -Urn "$0" "$@"
fi
ip link set lo up
exec python3 tests/park_switch_live.py "$@"
