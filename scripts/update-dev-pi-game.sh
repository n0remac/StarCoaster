#!/usr/bin/env bash
# Build canonical GitHub main in an isolated checkout, then activate DEV Pi only.
set -Eeuo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p run-data
exec 9>run-data/dev-pi-update.lock
flock 9
stage=fetch
revision=""
status() {
 python3 - "$1" "$stage" "$revision" <<'PY'
import datetime,json,os,sys
from pathlib import Path
p=Path('run-data/dev-deployment-status.json')
tmp=p.with_suffix('.tmp')
tmp.write_text(json.dumps(dict(status=sys.argv[1],stage=sys.argv[2],revision=sys.argv[3],
 updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
os.replace(tmp,p)
PY
}
trap 'status failed' ERR
step() { stage="$1";status running;printf '[DEV %s] %s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$stage" "$revision"; }
[[ "$(git branch --show-current)" == main ]] || { echo 'Expected isolated main checkout' >&2; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo 'Dirty release checkout' >&2; exit 1; }
runner_before="$(sha256sum scripts/update-dev-pi-game.sh | cut -d ' ' -f 1)"
git fetch origin main:refs/remotes/origin/main
git merge-base --is-ancestor HEAD origin/main || { echo 'Release checkout diverged' >&2; exit 1; }
git merge --ff-only origin/main
if [[ "$runner_before" != "$(sha256sum scripts/update-dev-pi-game.sh | cut -d ' ' -f 1)" ]]; then
 exec /bin/bash "$project_dir/scripts/update-dev-pi-game.sh"
fi
revision="$(git rev-parse HEAD)"
deployed="$(scripts/deploy-dev-pi.sh --status || true)"
if [[ "$deployed" == "$revision" ]]; then
 stage=complete;status succeeded
 echo "DEV Pi already serves $revision"
 exit 0
fi
step preflight
scripts/deploy-dev-pi.sh --check
step dependencies
python3 scripts/fetch-upstream.py
BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-2}" scripts/project.sh prepare-wasm-arm64
step build
OPENRCT2_WASM_LOCAL=1 BRIDGE_BUILD_JOBS="${BRIDGE_BUILD_JOBS:-2}" \
 scripts/project.sh start --prepare-only --headless --browser
step tests
scripts/project.sh test
scripts/project.sh test-wasm
"${GO_BIN:-/usr/local/go/bin/go}" build -o build/wasm-server ./cmd/wasm-server
step browser-gameplay
python3 scripts/test-release-candidate.py
step deployment
scripts/deploy-dev-pi.sh
stage=complete;status succeeded
printf 'DEV Pi deployed %s\n' "$revision"
