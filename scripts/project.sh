#!/usr/bin/env bash
# Shared developer entry points; specialized scripts remain the implementation.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
command="${1:-help}"
if (( $# )); then shift; fi

case "$command" in
    generate)
        exec python3 scripts/generate-starcraft-types.py "$@"
        ;;
    start)
        exec scripts/start.sh "$@"
        ;;
    build)
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        python3 scripts/generate-starcraft-types.py
        python3 scripts/generate-starcraft-types.py --check
        scripts/build-bwapi.sh
        scripts/build-openrct2.sh
        scripts/build-bridge-module.sh
        "$go_bin" build -o build/world-bridge ./cmd/world-bridge
        ;;
    build-wasm)
        exec scripts/build-openrct2-wasm.sh "$@"
        ;;
    prepare-wasm-arm64)
        exec scripts/prepare-openrct2-wasm-arm64.sh "$@"
        ;;
    serve-wasm)
        exec scripts/serve-wasm.sh "$@"
        ;;
    deploy-wasm)
        exec scripts/deploy-wasm.sh "$@"
        ;;
    test-wasm)
        export TMPDIR="${TMPDIR:-$project_dir/build/tmp}"
        mkdir -p "$TMPDIR"
        go_bin="$(command -v go || true)"
        go_bin="${go_bin:-/usr/local/go/bin/go}"
        export GOCACHE="${GOCACHE:-$project_dir/build/go-cache}"
        "$go_bin" test ./cmd/wasm-server
        node --check browser/index.js
        node --check browser/test.mjs
        node --check browser/live-test.mjs
        node --check browser/test-socket.mjs
        scripts/test-wasm-sockets.sh
        if [[ -f build/wasm-client/manifest.json ]]; then
            python3 scripts/verify-wasm-bundle.py build/wasm-client
            if command -v chromium >/dev/null; then
                if [[ ! -d browser/node_modules/playwright-core ]]; then
                    npm ci --prefix browser --ignore-scripts --no-audit --no-fund
                fi
                "$go_bin" build -o build/wasm-server ./cmd/wasm-server
                node browser/test.mjs
            else
                printf 'SKIP: browser automation requires Chromium\n'
            fi
        else
            printf 'BLOCKED: WASM artifact validation requires scripts/project.sh build-wasm\n' >&2
            exit 3
        fi
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
        python3 scripts/generate-starcraft-types.py --check
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
        tests/test_zerg_production_native_live.sh
        tests/test_zerg_production_rejection_native_live.sh
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
Usage: scripts/project.sh {start|build|prepare-wasm-arm64|build-wasm|serve-wasm|deploy-wasm|test-wasm|generate|park|play|record|test|test-live|test-live-construction|validate-scenario} [options]

start [--scenario ID] [--headless|--client] [--browser|--browser-bundle DIR]
                                        Fetch, build, stage, and play.
play ID [--plan]                        Play an existing build; --plan only resolves paths.
park [ID]                               Force-generate a park (Frontier default).
record [--scenario ID] [capture flags]   Capture gameplay (Frontier default).
validate-scenario ID                    Validate scenario configuration.
build, test, test-live                   Build and run offline or licensed live tests.
build-wasm                               Build the patched graphical OpenRCT2 WASM client.
prepare-wasm-arm64                      Install the pinned Emscripten toolchain and dependencies on the build drive.
serve-wasm [server flags]                Serve the private bundle on localhost with browser headers.
deploy-wasm [BUNDLE_DIR]                 Stage a versioned private bundle without restarting a game.
test-wasm                                Test the gateway and validate a built WASM bundle.
generate                                 Generate StarCraft catalogs and consumers.
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
