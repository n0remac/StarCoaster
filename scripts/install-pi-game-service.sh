#!/usr/bin/env bash
# Install the private game and SSH push hook for this Pi user.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if (( $# != 0 )); then
    printf 'Usage: scripts/install-pi-game-service.sh\n' >&2
    exit 2
fi
mkdir -p run-data/pi-park-library "$HOME/.config/systemd/user"
cp deploy/starcoaster-game.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable starcoaster-game.service
systemctl --user disable --now starcoaster-update.timer 2>/dev/null || true
scripts/install-pi-push-hook.sh
printf 'Installed private StarCoaster service; run scripts/update-pi-game.sh --force to deploy now.\n'
