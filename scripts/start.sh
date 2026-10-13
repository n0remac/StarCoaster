#!/usr/bin/env bash
# Build and launch the playable stack using the existing engine workflows.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

usage() {
    cat <<'EOF'
Usage: scripts/project.sh start [--headless|--client]
       scripts/start.sh [--headless|--client]

Fetch pinned sources, build both engines and the bridge, stage OpenRCT2 assets,
regenerate Frontier Outpost, and start the session. Ctrl+C stops it.

Game data defaults to ~/games/rct2 and ~/games/starcraft.
Override with RCT2_DATA_DIR and STARCRAFT_DATA_DIR for other installations.
BRIDGE_BUILD_JOBS defaults to 2. A graphical client opens when DISPLAY is set;
use --headless to disable it or --client to require it.
Install system build dependencies first; see docs/bootstrap.md.
EOF
}

for option in "$@"; do
    case "$option" in
        --headless) export BRIDGE_LAUNCH_CLIENT=0 ;;
        --client) export BRIDGE_LAUNCH_CLIENT=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$option" >&2; usage >&2; exit 2 ;;
    esac
done

export RCT2_DATA_DIR="${RCT2_DATA_DIR:-$HOME/games/rct2}"
export STARCRAFT_DATA_DIR="${STARCRAFT_DATA_DIR:-$HOME/games/starcraft}"
for variable in RCT2_DATA_DIR STARCRAFT_DATA_DIR; do
    data_dir="${!variable}"
    if [[ ! -d "$data_dir" ]]; then
        printf 'Missing game data directory: %s\nSet %s to your installed game data directory.\n' "$data_dir" "$variable" >&2
        exit 1
    fi
done
printf 'RCT2 data: %s\nStarCraft data: %s\n' "$RCT2_DATA_DIR" "$STARCRAFT_DATA_DIR"
# Keep alternate archive spellings aligned with run-bwapi.sh.
for archive in StarDat.mpq BrooDat.mpq Patch_rt.mpq; do
    alternate="$archive"
    case "$archive" in
        StarDat.mpq) alternate=Stardat.mpq ;;
        BrooDat.mpq) alternate=Broodat.mpq ;;
    esac
    if [[ ! -f "$STARCRAFT_DATA_DIR/$archive" && ! -f "$STARCRAFT_DATA_DIR/$alternate" ]]; then
        printf 'Missing %s in %s\n' "$archive" "$STARCRAFT_DATA_DIR" >&2
        exit 1
    fi
done
if [[ "${BRIDGE_LAUNCH_CLIENT:-0}" == 1 && -z "${DISPLAY:-}" ]]; then
    printf 'A graphical DISPLAY is required for --client or BRIDGE_LAUNCH_CLIENT=1.\n' >&2
    exit 1
fi
for tool in git python3 cmake ninja c++; do
    command -v "$tool" >/dev/null || { printf 'Missing build tool: %s; see docs/bootstrap.md\n' "$tool" >&2; exit 1; }
done
if ! command -v go >/dev/null && [[ ! -x /usr/local/go/bin/go ]]; then
    printf 'Missing Go compiler; install Go and add it to PATH.\n' >&2
    exit 1
fi

printf 'Fetching pinned upstream sources...\n'
python3 scripts/fetch-upstream.py
printf 'Building engines and world bridge...\n'
scripts/project.sh build
printf 'Staging OpenRCT2 assets locally...\n'
scripts/install-openrct2-local.sh
printf 'Generating Frontier Outpost from the current sources...\n'
scripts/project.sh park
printf 'Starting Frontier Outpost (Ctrl+C to stop)...\n'
exec scripts/project.sh run
