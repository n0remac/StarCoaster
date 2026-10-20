#!/usr/bin/env bash
# Start the patched OpenRCT2 application at its normal main menu.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
game_data="${RCT2_DATA_DIR:-$HOME/games/rct2}"
openrct2_data="$project_dir/build/openrct2-stage/usr/local/share/openrct2"
user_data="${STARCOASTER_USER_DATA_DIR:-$project_dir/run-data/native-player}"
test -x "$project_dir/build/openrct2/openrct2" || {
    printf 'Build OpenRCT2 first with scripts/project.sh build\n' >&2
    exit 1
}
test -f "$openrct2_data/g2.dat" || {
    printf 'Staged OpenRCT2 data is missing\n' >&2
    exit 1
}
test -d "$game_data" || {
    printf 'RCT2 data directory is missing: %s\n' "$game_data" >&2
    exit 1
}
mkdir -p "$user_data/plugin"
cp "$project_dir/openrct2-plugin/rts-bridge.js" "$user_data/plugin/rts-bridge.js"
owner_token_file="${STARCOASTER_OWNER_TOKEN_FILE:-$project_dir/run-data/park-supervisor/owner-token}"
if [[ -z "${STARCOASTER_CONTROL_URL:-}" && -r "$owner_token_file" ]]; then
    export STARCOASTER_CONTROL_URL="http://127.0.0.1:8091"
fi
if [[ -n "${STARCOASTER_CONTROL_URL:-}" && -z "${BRIDGE_SESSION_OWNER_TOKEN:-}" && -r "$owner_token_file" ]]; then
    export BRIDGE_SESSION_OWNER_TOKEN="$(cat "$owner_token_file")"
fi
exec "$project_dir/build/openrct2/openrct2" \
    --rct2-data-path="$(realpath "$game_data")" \
    --openrct2-data-path="$openrct2_data" \
    --user-data-path="$user_data" "$@"
