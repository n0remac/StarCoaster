#!/usr/bin/env bash
# Verify a pushed main revision, then restart the managed game.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
force=0
from_push=0
for arg in "$@"; do
    case "$arg" in
        --force) force=1 ;;
        --from-push) from_push=1 ;;
        *) printf 'Usage: scripts/update-pi-game.sh [--force] [--from-push]\n' >&2; exit 2 ;;
    esac
done
mkdir -p run-data
exec 9>run-data/pi-update.lock
flock 9
log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
[[ "$(git branch --show-current)" == main ]] || { log 'Expected the main branch'; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { log 'Checkout has local changes; update refused'; exit 1; }
if [[ "$from_push" == 1 ]]; then
    push_repo="${STARCOASTER_PUSH_REPO:-$project_dir/run-data/pi-push.git}"
    test -d "$push_repo" || { log "Push repository missing: $push_repo"; exit 1; }
    log 'Fetching Pi push/main'
    git fetch "$push_repo" refs/heads/main
    target=FETCH_HEAD
else
    log 'Fetching origin/main'
    git fetch origin main:refs/remotes/origin/main
    target=origin/main
fi
if git merge-base --is-ancestor HEAD "$target"; then
    git merge --ff-only "$target"
elif git merge-base --is-ancestor "$target" HEAD; then
    log 'Local main already includes the pushed revision'
else
    log 'main diverged from pushed main'
    exit 1
fi
revision="$(git rev-parse HEAD)"
marker=run-data/prod-deployed-revision
if [[ "$force" == 0 && -f "$marker" && "$(cat "$marker")" == "$revision" ]]; then
    log "Already running $revision"
    exit 0
fi
log "Building $revision"
BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-1}" scripts/project.sh build
scripts/install-openrct2-local.sh
OPENRCT2_WASM_LOCAL=1 BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-1}" \
    scripts/project.sh build-wasm
log 'Running offline and browser checks'
scripts/project.sh test
scripts/project.sh test-wasm
"${GO_BIN:-/usr/local/go/bin/go}" build -o build/wasm-server ./cmd/wasm-server
log 'Deploying verified build to production Pi'
scripts/deploy-production.sh
log "Production deployment finished for $revision"
