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
        if [[ "${1:-}" == --probe-demolition ]]; then
            python3 scripts/create-park-assault.py --playable "$@"
        else
            python3 scripts/park-scenario.py "$@"
        fi
        ;;
    validate-scenario)
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        "$go_bin" run ./cmd/scenario-validate "$@"
        ;;
    play)
        exec python3 scripts/play-scenario.py "$@"
        ;;
    record)
        exec python3 scripts/record-scenario.py "$@"
        ;;
    test)
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        "$go_bin" test ./...
        ctest --test-dir build/bridge-module --output-on-failure
        python3 -m unittest discover -s tests -p 'test_*.py'
        for file in tests/test_*plugin.js; do node "$file"; done
        ;;
    test-live)
        tests/test_frontier_ridge_live.sh
        tests/test_frontier_native_navigation_live.sh
        python3 tests/test_world_256_native_live.py
        python3 tests/test_marine_controls_live.py
        tests/test_world_live.sh
        python3 scripts/verify-frontier-lifecycle.py
        tests/test_actor_lifecycle_live.sh
        tests/test_unit_spawn_live.sh
        tests/test_unit_spawn_zerg_live.sh
        tests/test_playable_start_live.sh
        python3 tests/test_scenario_runtime_live.py
        scripts/project.sh test-live-construction
        ;;
    test-live-construction)
        tests/test_live_construction_navigation.sh
        tests/test_live_construction_batch.sh
        tests/test_live_construction_targets.sh
        tests/test_live_construction_modification.sh
        tests/test_live_construction_manual.sh
        tests/test_live_construction_concurrent.sh
        tests/test_live_construction_capacity.sh
        tests/test_live_construction_overlap.sh
        tests/test_live_construction_terrain.sh
        tests/test_live_construction_scenery_path.sh
        tests/test_live_construction_unchanged.sh
        tests/test_live_construction_recovery.sh
        tests/test_live_construction_interrupted.sh
        tests/test_live_construction_death_recovery.sh
        tests/test_live_objective_manual.sh
        ;;
    help|-h|--help)
        cat <<'EOF'
Usage: scripts/project.sh {start|build|park|play|record|test|test-live|test-live-construction|validate-scenario} [options]

start [--scenario ID] [--headless|--client]  Fetch, build, stage, and play (Frontier default).
play ID [--plan]                        Play an existing build; --plan only resolves paths.
park [ID]                               Force-generate a park (Frontier default).
record [--scenario ID] [capture flags]   Capture gameplay (Frontier default).
validate-scenario ID                    Validate scenario configuration.
build, test, test-live                   Build and run offline or licensed live tests.
test-live-construction                  Run licensed live construction regressions.

Set RCT2_DATA_DIR and STARCRAFT_DATA_DIR for native commands.
Use `start --help` and `record --help` for additional options.
EOF
        ;;
    *)
        printf 'Unknown command: %s\n' "$command" >&2
        exit 2
        ;;
esac
