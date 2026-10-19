#!/usr/bin/env bash
# Poll main, verify a complete private build, then restart the managed game.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
force=0
if [[ "${1:-}" == --force && $# == 1 ]]; then force=1
elif (( $# )); then printf 'Usage: scripts/update-pi-game.sh [--force]\n' >&2; exit 2
fi
mkdir -p run-data
exec 9>run-data/pi-update.lock
flock -n 9 || { printf 'Pi update already running.\n'; exit 0; }
log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
[[ "$(git branch --show-current)" == main ]] || { log 'Expected the main branch'; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { log 'Checkout has local changes; update refused'; exit 1; }
log 'Fetching origin/main'
git fetch origin main:refs/remotes/origin/main
if git merge-base --is-ancestor HEAD origin/main; then
    git merge --ff-only origin/main
elif git merge-base --is-ancestor origin/main HEAD; then
    log 'Local main is ahead of origin/main; deploying the local revision'
else
    log 'main diverged from origin/main'
    exit 1
fi
revision="$(git rev-parse HEAD)"
marker=run-data/pi-deployed-revision
if [[ "$force" == 0 && -f "$marker" && "$(cat "$marker")" == "$revision" ]]; then
    log "Already running $revision"
    exit 0
fi
park_file=run-data/pi-park-path
test -s "$park_file" || { log "Missing park selection: $park_file"; exit 1; }
IFS= read -r park_path < "$park_file"
test -f "$park_path" || { log "Park not found: $park_path"; exit 1; }
log "Building $revision for $park_path"
OPENRCT2_WASM_LOCAL=1 BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-1}" \
    scripts/project.sh start --park "$park_path" --browser --prepare-only
log 'Running offline and browser checks'
scripts/project.sh test
scripts/project.sh test-wasm
log 'Deploying private browser bundle'
scripts/project.sh deploy-wasm
log 'Restarting StarCoaster game'
systemctl --user restart starcoaster-game.service
ready=0
for attempt in $(seq 1 45); do
    if systemctl --user is-active --quiet starcoaster-game.service && \
        curl --fail --silent --show-error --max-time 2 http://127.0.0.1:8091/manifest.json \
            -o run-data/pi-served-manifest.json 2>/dev/null && \
        python3 - <<'PY'
import hashlib
import json
from pathlib import Path

served = json.loads(Path('run-data/pi-served-manifest.json').read_text())
local = json.loads(Path('build/wasm-client/manifest.json').read_text())
assert served == local
assert served['visual_source'] == 'starcraft-local'
assert served['plugin_sha256'] == hashlib.sha256(
    Path('openrct2-plugin/rts-bridge.js').read_bytes()).hexdigest()
PY
    then ready=1; break; fi
    sleep 2
done
if [[ "$ready" != 1 ]]; then
    log 'Game or private browser bundle failed health check'
    exit 1
fi
printf '%s\n' "$revision" > "$marker.tmp"
mv -f "$marker.tmp" "$marker"
log "Deployed and serving $revision"
