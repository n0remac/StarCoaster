#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rct2_dir="${RCT2_DATA_DIR:?Set RCT2_DATA_DIR to your own RCT2 or RCT Classic installation directory}"
park_file="${1:?Pass an existing .park, .sv6, or scenario file to host}"
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
server_data="${BRIDGE_SERVER_DATA_DIR:-$project_dir/run-data/openrct2-server}"

test -d "$rct2_dir" || { printf 'Missing RCT2 data directory: %s\n' "$rct2_dir" >&2; exit 1; }
test -f "$park_file" || { printf 'Missing park file: %s\n' "$park_file" >&2; exit 1; }
test -f "$openrct2_data/g2.dat" || { printf 'Missing staged OpenRCT2 data; run scripts/install-openrct2-local.sh\n' >&2; exit 1; }
test -x "$project_dir/build/openrct2/openrct2-cli" || { printf 'Missing OpenRCT2 CLI; run scripts/build-openrct2.sh\n' >&2; exit 1; }

mkdir -p "$server_data/plugin"
cp "$project_dir/openrct2-plugin/rts-bridge.js" "$server_data/plugin/rts-bridge.js"
cp "$project_dir/openrct2-plugin/park-operator-permissions.js" "$server_data/plugin/park-operator-permissions.js"
if ! test -f "$server_data/config.ini"; then
  printf '[network]\nadvertise = false\n' > "$server_data/config.ini"
elif grep -q '^advertise = true$' "$server_data/config.ini"; then
  sed -i 's/^advertise = true$/advertise = false/' "$server_data/config.ini"
fi
extra_args=()
if test "${BRIDGE_VERBOSE:-0}" = 1; then extra_args+=(--verbose); fi
exec "$project_dir/build/openrct2/openrct2-cli" host "$(realpath "$park_file")" \
  --headless --address=127.0.0.1 --port="${OPENRCT2_PORT:-11753}" \
  --rct2-data-path="$(realpath "$rct2_dir")" \
  --openrct2-data-path="$openrct2_data" \
  --user-data-path="$server_data" "${extra_args[@]}"
