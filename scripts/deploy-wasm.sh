#!/usr/bin/env bash
# Copy a verified private bundle into a versioned directory, then atomically
# select it. Running native game processes are left alone.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${1:-$project_dir/build/wasm-client}"
if (( $# > 1 )); then printf 'Usage: scripts/project.sh deploy-wasm [BUNDLE_DIR]\n' >&2; exit 2; fi
deploy_dir="${WASM_DEPLOY_DIR:-$project_dir/run-data/wasm-deploy}"
test -s "$source_dir/manifest.json" || { printf 'Missing WASM bundle: %s\n' "$source_dir" >&2; exit 1; }
python3 "$project_dir/scripts/verify-wasm-bundle.py" "$source_dir"
version="$(sha256sum "$source_dir/manifest.json" | cut -c 1-16)"
mkdir -p "$deploy_dir"
if [[ ! -d "$deploy_dir/$version" ]]; then
    temp_dir="$(mktemp -d "$deploy_dir/.staging.XXXXXXXX")"
    trap 'rm -rf "$temp_dir"' EXIT
    cp -a "$source_dir/." "$temp_dir/"
    mv "$temp_dir" "$deploy_dir/$version"
    trap - EXIT
fi
ln -sfn "$version" "$deploy_dir/.current-next"
mv -Tf "$deploy_dir/.current-next" "$deploy_dir/current"
printf 'Deployed private browser bundle: %s\n' "$deploy_dir/current"
