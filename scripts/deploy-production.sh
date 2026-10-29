#!/usr/bin/env bash
# Publish a verified build to the production Pi; never restart the dev service.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
[[ -z "$(git status --porcelain)" ]] || { echo 'Refusing to publish a dirty checkout' >&2; exit 1; }
revision="$(git rev-parse HEAD)"
target=cameron@100.119.114.99
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/home/pi/.ssh/starcoaster-prod-known-hosts -i /home/pi/.ssh/starcoaster_deploy_ed25519 -o IdentitiesOnly=yes)
case "${1:-}" in
 --status) ssh "${ssh_opts[@]}" "$target" 'systemctl is-active --quiet starcoaster.service && cat /opt/starcoaster/current/REVISION'; exit ;;
 --check|"") ;;
 *) echo 'Usage: deploy-production.sh [--check|--status]' >&2; exit 2 ;;
esac
ssh "${ssh_opts[@]}" "$target" 'sudo -n /usr/local/sbin/starcoaster-activate --check'
if [[ ${1:-} == --check ]]; then exit 0; fi
[[ $# == 0 ]] || exit 2
stage="$(mktemp -d "$root/run-data/prod-package.XXXXXXXX")"
trap 'rm -rf "$stage"' EXIT
paths=(scripts tests deploy scenarios bridge-protocol openrct2-plugin assets dependencies.lock.json
 build/wasm-server build/world-bridge build/openrct2/openrct2-cli build/openrct2-stage
 build/bwapi/bin build/bwapi/lib build/bridge-module/BridgeAIModule.so
 upstream/bwapi/bwapi/TestAIModule/maps/TestModule/testmap1.scm upstream/openbw/bwenums.h
 upstream/openrct2/src/openrct2/drawing/ImageImporter.h)
for p in "${paths[@]}"; do
  test -e "$p" || { echo "Missing release input: $p" >&2; exit 1; }
  mkdir -p "$stage/$(dirname "$p")"
  cp -aL "$p" "$stage/$p"
done
mkdir -p "$stage/build/compat" "$stage/wasm"
for lib in libzip.so.4 libicuuc.so.72 libicudata.so.72; do
 cp -L "/lib/aarch64-linux-gnu/$lib" "$stage/build/compat/$lib"
done
cp -aL build/wasm-client/. "$stage/wasm/"
python3 scripts/verify-wasm-bundle.py "$stage/wasm"
printf '%s\n' "$revision" > "$stage/REVISION"
(cd "$stage" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
archive="$root/run-data/production-$revision.tar"
scripts/package-production-archive.sh "$stage" "$archive"
ssh "${ssh_opts[@]}" "$target" 'mkdir -p /home/cameron/starcoaster-incoming'
scp "${ssh_opts[@]}" "$archive" "$target:/home/cameron/starcoaster-incoming/$revision.tar.uploading"
ssh "${ssh_opts[@]}" "$target" "mv /home/cameron/starcoaster-incoming/$revision.tar.uploading /home/cameron/starcoaster-incoming/$revision.tar"
ssh "${ssh_opts[@]}" "$target" "sudo -n /usr/local/sbin/starcoaster-activate $revision"
printf '%s\n' "$revision" > run-data/prod-deployed-revision
echo "Production deployed: $revision on 100.119.114.99"
