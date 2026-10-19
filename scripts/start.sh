#!/usr/bin/env bash
# Build and launch the playable stack using the existing engine workflows.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

usage() {
    cat <<'EOF'
Usage: scripts/project.sh start [--scenario ID|--park FILE] [--headless|--client] [--browser|--browser-bundle DIR] [--prepare-only]
       scripts/start.sh [--scenario ID|--park FILE] [--headless|--client] [--browser|--browser-bundle DIR]

Fetch pinned sources, build both engines and the bridge, stage OpenRCT2 assets,
and play the selected scenario (default: frontier-outpost) or existing park.
Ctrl+C stops it.

Game data defaults to ~/games/rct2 and ~/games/starcraft.
Override with RCT2_DATA_DIR and STARCRAFT_DATA_DIR for other installations.
Registered StarCraft sprites and building objects are extracted from those local archives.
BRIDGE_SPRITE_SOURCE defaults to starcraft-local; set it to alien-scout to use
the original placeholder art.
BRIDGE_BUILD_JOBS defaults to 2. A graphical client opens when DISPLAY is set;
use --headless to disable it or --client to require it.
Install system build dependencies first; see docs/bootstrap.md.
--browser builds and deploys the private WASM bundle and serves it on localhost
alongside the ordinary scenario. Configure Tailscale Serve separately.
--browser-bundle DIR deploys an amd64 workstation bundle on the Pi and serves it.
--prepare-only builds native and browser artifacts without deploying or launching.
EOF
}

scenario=frontier-outpost
park_path=""
client_mode=""
browser_mode=0
browser_bundle=""
prepare_only=0
while (( $# )); do
    case "$1" in
        --scenario)
            if (( $# < 2 )) || [[ "$2" == --* ]]; then
                printf 'Missing value for --scenario\n' >&2; usage >&2; exit 2
            fi
            scenario="$2"
            shift 2
            ;;
        --park)
            if (( $# < 2 )) || [[ "$2" == --* ]]; then
                printf 'Missing value for --park\n' >&2; usage >&2; exit 2
            fi
            park_path="$2"
            shift 2
            ;;
        --headless|--client)
            if [[ -n "$client_mode" && "$client_mode" != "$1" ]]; then
                printf '%s and %s cannot be combined\n' "$client_mode" "$1" >&2; exit 2
            fi
            client_mode="$1"
            shift
            ;;
        --browser)
            if [[ -n "$browser_bundle" ]]; then printf '%s and --browser-bundle cannot be combined\n' "$1" >&2; exit 2; fi
            browser_mode=1
            shift
            ;;
        --browser-bundle)
            if (( $# < 2 )) || [[ "$2" == --* ]] || [[ "$browser_mode" == 1 ]]; then
                printf 'Pass a bundle directory to --browser-bundle and do not combine it with --browser\n' >&2; exit 2
            fi
            browser_bundle="$2"
            shift 2
            ;;
        --prepare-only) prepare_only=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done
if [[ "$client_mode" == --headless ]]; then export BRIDGE_LAUNCH_CLIENT=0; fi
if [[ "$client_mode" == --client ]]; then export BRIDGE_LAUNCH_CLIENT=1; fi
# The plan uses the same resolver as play and has no build or gameplay side effects.
play_args=("$scenario")
if [[ -n "$park_path" ]]; then play_args=(--park "$park_path"); fi
python3 scripts/play-scenario.py "${play_args[@]}" --plan >/dev/null

export RCT2_DATA_DIR="${RCT2_DATA_DIR:-$HOME/games/rct2}"
export STARCRAFT_DATA_DIR="${STARCRAFT_DATA_DIR:-$HOME/games/starcraft}"
export BRIDGE_SPRITE_SOURCE="${BRIDGE_SPRITE_SOURCE:-starcraft-local}"
case "$BRIDGE_SPRITE_SOURCE" in
    starcraft-local|alien-scout) ;;
    *) printf 'Unknown BRIDGE_SPRITE_SOURCE: %s\n' "$BRIDGE_SPRITE_SOURCE" >&2; exit 1 ;;
esac
for variable in RCT2_DATA_DIR STARCRAFT_DATA_DIR; do
    data_dir="${!variable}"
    if [[ ! -d "$data_dir" ]]; then
        printf 'Missing game data directory: %s\nSet %s to your installed game data directory.\n' "$data_dir" "$variable" >&2
        exit 1
    fi
done
printf 'RCT2 data: %s\nStarCraft data: %s\n' "$RCT2_DATA_DIR" "$STARCRAFT_DATA_DIR"
printf 'Unit sprites: %s\n' "$BRIDGE_SPRITE_SOURCE"
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
for tool in git python3 cmake ninja c++ smpq; do
    command -v "$tool" >/dev/null || { printf 'Missing build tool: %s; see docs/bootstrap.md\n' "$tool" >&2; exit 1; }
done
if ! command -v go >/dev/null && [[ ! -x /usr/local/go/bin/go ]]; then
    printf 'Missing Go compiler; install Go and add it to PATH.\n' >&2
    exit 1
fi

printf 'Fetching pinned upstream sources...\n'
python3 scripts/fetch-upstream.py
python3 scripts/generate-starcraft-types.py
python3 scripts/generate-starcraft-types.py --check
if [[ "$BRIDGE_SPRITE_SOURCE" == starcraft-local ]]; then
    printf 'Preparing registered local StarCraft sprites...\n'
    mapfile -t required_assets < <(python3 - <<'PY'
import json
from pathlib import Path
root = Path('bridge-protocol')
catalog = json.loads((root / 'starcraft-types.json').read_text())
visuals = json.loads((root / 'starcraft-visuals.json').read_text())
assets = [visuals['units'][item['visual']]['asset'] for item in catalog['units']]
assets += [visuals['effects'][key]['asset'] for key in visuals['effects']
           if key in {visuals['units'][item['visual']].get('effect') for item in catalog['units']}]
print('\n'.join(dict.fromkeys(assets)))
PY
)
    for unit in "${required_assets[@]}"; do
        python3 scripts/prepare-starcraft-sprites.py --game-dir "$STARCRAFT_DATA_DIR" --unit "$unit"
    done
    python3 scripts/prepare-starcraft-command-icons.py --game-dir "$STARCRAFT_DATA_DIR"
fi
printf 'Building engines and world bridge...\n'
scripts/project.sh build
printf 'Staging OpenRCT2 assets locally...\n'
scripts/install-openrct2-local.sh
if [[ "$BRIDGE_SPRITE_SOURCE" == starcraft-local ]]; then
    python3 scripts/install-starcraft-construction-object.py \
        build/openrct2-stage/usr/local/share/openrct2 --game-dir "$STARCRAFT_DATA_DIR" --all
fi
if [[ "$BRIDGE_SPRITE_SOURCE" == starcraft-local ]]; then
    python3 scripts/verify-starcraft-visuals.py --record
fi
if [[ "$browser_mode" == 1 ]]; then
    scripts/project.sh build-wasm
    if [[ "$prepare_only" == 0 ]]; then scripts/project.sh deploy-wasm; fi
    export BRIDGE_SERVE_WASM=1
elif [[ -n "$browser_bundle" ]]; then
    if [[ "$prepare_only" == 0 ]]; then scripts/project.sh deploy-wasm "$browser_bundle"; fi
    export BRIDGE_SERVE_WASM=1
fi
if [[ "$prepare_only" == 1 ]]; then
    printf 'Native and browser artifacts prepared; game not started.\n'
    exit 0
fi
printf 'Starting %s (Ctrl+C to stop)...\n' "$scenario"
exec scripts/project.sh play "${play_args[@]}"
