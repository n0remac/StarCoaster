#!/usr/bin/env bash
# Install the private game and SSH push hook for this Pi user.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ "${1:-}" != --park || $# != 2 ]]; then
    printf 'Usage: scripts/install-pi-game-service.sh --park /path/to/existing.park\n' >&2
    exit 2
fi
park_path="$(realpath "$2")"
test -f "$park_path" || { printf 'Park not found: %s\n' "$park_path" >&2; exit 1; }
[[ "${park_path,,}" == *.park ]] || { printf 'Expected a .park save: %s\n' "$park_path" >&2; exit 1; }
scripts/project.sh play --park "$park_path" --plan >/dev/null
mkdir -p run-data "$HOME/.config/systemd/user"
printf '%s\n' "$park_path" > run-data/pi-park-path
cp deploy/starcoaster-game.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable starcoaster-game.service
systemctl --user disable --now starcoaster-update.timer 2>/dev/null || true
scripts/install-pi-push-hook.sh
printf 'Installed private game for %s; run scripts/update-pi-game.sh --force to deploy now.\n' "$park_path"
