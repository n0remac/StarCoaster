#!/usr/bin/env bash
# Publish a validated local release to the DEV Pi only.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
release_root=/media/pi/media1/starcoaster-dev-releases
case "${1:-}" in
 --status) exec python3 scripts/activate-dev-pi.py --status ;;
 --rollback|--resume|--check|"") ;;
 *) echo 'Usage: deploy-dev-pi.sh [--check|--status|--rollback|--resume]' >&2; exit 2 ;;
esac
[[ "$(hostname -s)" == raspberrypi ]] || { echo 'Refusing non-DEV host' >&2; exit 1; }
ip -4 addr show | grep -F '100.109.28.107/' >/dev/null || { echo 'DEV Tailscale address is absent' >&2; exit 1; }
systemctl --user show starcoaster-game.service --property=LoadState --value | grep -Fxq loaded
test -d /home/pi/games/rct2
test -d /home/pi/games/starcraft
test -d /media/pi/media1/starcoaster-production-build/run-data/pi-park-library
mkdir -p "$release_root/releases" "$release_root/building"
if [[ "${1:-}" == --rollback ]]; then exec python3 scripts/activate-dev-pi.py --rollback; fi
if [[ "${1:-}" == --resume ]]; then exec python3 scripts/activate-dev-pi.py --resume; fi
if [[ "${1:-}" == --check ]]; then exit 0; fi
[[ $# == 0 ]] || exit 2
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo 'Refusing dirty release checkout' >&2; exit 1; }
revision="$(git rev-parse HEAD)"
stage="$(mktemp -d "$release_root/building/$revision.XXXXXXXX")"
trap 'if [[ -d "$stage" ]]; then rm -rf "$stage"; fi' EXIT
paths=(scripts tests deploy scenarios bridge-protocol openrct2-plugin assets dependencies.lock.json
 build/wasm-server build/world-bridge build/openrct2/openrct2-cli build/openrct2-stage
 build/bwapi/bin build/bwapi/lib build/bridge-module/BridgeAIModule.so
 upstream/bwapi/bwapi/TestAIModule/maps/TestModule/testmap1.scm upstream/openbw/bwenums.h
 upstream/openrct2/src/openrct2/drawing/ImageImporter.h)
for path in "${paths[@]}"; do
 test -e "$path" || { echo "Missing DEV release input: $path" >&2; exit 1; }
 mkdir -p "$stage/$(dirname "$path")"
 cp -aL "$path" "$stage/$path"
done
mkdir -p "$stage/build/compat" "$stage/run-data/wasm-deploy/current"
for lib in libzip.so.4 libicuuc.so.72 libicudata.so.72; do
 cp -L "/lib/aarch64-linux-gnu/$lib" "$stage/build/compat/$lib"
done
cp -aL build/wasm-client/. "$stage/run-data/wasm-deploy/current/"
python3 scripts/verify-wasm-bundle.py "$stage/run-data/wasm-deploy/current"
printf '%s\n' "$revision" > "$stage/REVISION"
(
 cd "$stage"
 find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 sha256sum > SHA256SUMS
)
candidate="$release_root/releases/$revision"
if [[ -e "$candidate" ]]; then
 python3 scripts/activate-dev-pi.py "$revision"
 exit 0
fi
mv "$stage" "$candidate"
python3 scripts/activate-dev-pi.py "$revision"
