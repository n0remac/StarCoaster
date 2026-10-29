#!/usr/bin/env bash
# Build exactly GitHub main in the isolated checkout, then publish to production.
set -Eeuo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
force=0
for arg in "$@"; do
 case "$arg" in
  --force) force=1 ;;
  --from-push) : ;; # Compatibility: GitHub remains authoritative.
  *) echo 'Usage: update-pi-game.sh [--force] [--from-push]' >&2; exit 2 ;;
 esac
done
mkdir -p run-data
exec 9>run-data/pi-update.lock
flock 9
stage=fetch
revision=""
status() {
 python3 - "$1" "$stage" "$revision" <<'PY'
import datetime,json,os,sys
from pathlib import Path
p=Path('run-data/deployment-status.json')
tmp=p.with_suffix('.tmp')
tmp.write_text(json.dumps(dict(status=sys.argv[1],stage=sys.argv[2],revision=sys.argv[3],
 updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
os.replace(tmp,p)
PY
}
trap 'status failed' ERR
log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
step() { stage="$1";status running;log "$stage $revision"; }
[[ "$(git branch --show-current)" == main ]] || { log 'Expected isolated main branch'; status failed; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { log 'Checkout has local changes; refused'; status failed; exit 1; }
git fetch origin main:refs/remotes/origin/main
target=origin/main
if ! git merge-base --is-ancestor HEAD "$target"; then
 log 'Build checkout diverged or is ahead of GitHub main; refused'
 status failed;exit 1
fi
git merge --ff-only "$target"
revision="$(git rev-parse HEAD)"
# Production is the source of truth; do not trust a stale local marker.
deployed="$(scripts/deploy-production.sh --status || true)"
if [[ "$force" == 0 && "$deployed" == "$revision" ]]; then
 printf '%s\n' "$revision" > run-data/prod-deployed-revision
 stage=complete;status succeeded
 log "Already serving $revision";exit 0
fi
step preflight
scripts/deploy-production.sh --check
step dependencies
python3 scripts/fetch-upstream.py
BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-2}" scripts/project.sh prepare-wasm-arm64
step build
# The canonical prepare workflow also extracts sprites/icons and installs
# construction objects; a fresh checkout has none of the dev machine's assets.
OPENRCT2_WASM_LOCAL=1 BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-2}" \
 scripts/project.sh start --prepare-only --headless --browser
step tests
scripts/project.sh test
scripts/project.sh test-wasm
"${GO_BIN:-/usr/local/go/bin/go}" build -o build/wasm-server ./cmd/wasm-server
step browser-gameplay
python3 scripts/test-release-candidate.py
step deployment
scripts/deploy-production.sh
stage=complete;status succeeded
log "Production deployment finished for $revision"
