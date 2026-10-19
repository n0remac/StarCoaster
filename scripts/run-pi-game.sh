#!/usr/bin/env bash
# Start the selected private park from the systemd game service.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
park_file="$project_dir/run-data/pi-park-path"
test -s "$park_file" || { printf 'Missing Pi park selection: %s\n' "$park_file" >&2; exit 1; }
IFS= read -r park_path < "$park_file"
test -f "$park_path" || { printf 'Pi park not found: %s\n' "$park_path" >&2; exit 1; }
mkdir -p build
exec scripts/project.sh play --park "$park_path" >> build/wasm-playable-session.log 2>&1
