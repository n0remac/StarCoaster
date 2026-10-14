#!/usr/bin/env bash
# Compatibility entry point for the original playable session.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$project_dir/scripts/play-scenario.py" frontier-outpost "$@"
