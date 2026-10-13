#!/usr/bin/env bash
# Shared developer entry points; specialized scripts remain the implementation.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
command="${1:-help}"
if (( $# )); then shift; fi

case "$command" in
    start)
        exec scripts/start.sh "$@"
        ;;
    build)
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        scripts/build-bwapi.sh
        scripts/build-openrct2.sh
        scripts/build-bridge-module.sh
        "$go_bin" build -o build/world-bridge ./cmd/world-bridge
        ;;
    park)
        python3 scripts/create-park-assault.py --playable "$@"
        ;;
    run)
        exec scripts/run-frontier-outpost.sh "$@"
        ;;
    record)
        exec python3 scripts/record-frontier-outpost.py "$@"
        ;;
    test)
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        "$go_bin" test ./...
        ctest --test-dir build/bridge-module --output-on-failure
        python3 -m unittest discover -s tests -p 'test_*.py'
        for file in tests/test_*plugin.js tests/test_plugin_snapshots.js; do node "$file"; done
        ;;
    test-live)
        tests/test_frontier_native_navigation_live.sh
        tests/test_world_live.sh
        python3 scripts/verify-frontier-lifecycle.py
        tests/test_actor_lifecycle_live.sh
        tests/test_unit_spawn_live.sh
        tests/test_unit_spawn_zerg_live.sh
        ;;
    help|-h|--help)
        cat <<'EOF'
Usage: scripts/project.sh {start|build|park|run|record|test|test-live} [options]

Set RCT2_DATA_DIR and STARCRAFT_DATA_DIR for build, park, run, record, and live tests.
Run `start` to fetch sources, build, stage assets, and launch the playable session.
Use `start --help` for launch options. Individual steps remain available.
EOF
        ;;
    *)
        printf 'Unknown command: %s\n' "$command" >&2
        exit 2
        ;;
esac
