#!/usr/bin/env bash
# Create a private SSH Git receive endpoint for push-triggered deployments.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
repo="$project_dir/run-data/pi-push.git"
mkdir -p run-data
if [[ ! -d "$repo" ]]; then
    git init --bare --initial-branch=main "$repo"
    git -C "$repo" config receive.denyNonFastForwards true
    git -C "$repo" config receive.denyDeletes true
    git push "$repo" HEAD:refs/heads/main
fi
cp scripts/pi-post-receive "$repo/hooks/post-receive"
chmod 700 "$repo/hooks/post-receive"
printf 'Push to ssh://%s@%s%s with: git push pi main\n' "$(id -un)" "$(hostname)" "$repo"
