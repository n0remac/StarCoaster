# Legacy script consolidation baseline (v0.6)

Source commit: `ace5c9e`; the worktree was clean. Inventory covers all 77 tracked
files in `scripts/`. Callers were checked with repository-wide filename and
Python module searches, along with `project.sh`, shell launchers, plugin staging,
and the native scenario switch in `BridgeAIModule.cpp`.

| Class | Scripts and caller/dependency summary |
| --- | --- |
| Active runtime | `project.sh` dispatches `start.sh`, `play-scenario.py`, `park-scenario.py`, `record-frontier-outpost.py`, builds, tests; `scenario_package.py` resolves packages; `run-world-session.sh` launches `run-bwapi.sh` and `run-openrct2-host.sh`; `create-world-base-map.py`, `starcraft_map_pack.py`, `create-park-assault.py`, `park-assault-generator.js`, `park_navigation.py`, `frontier_geometry.py` produce packaged assets. |
| Build and install utilities | `fetch-upstream.py`, `check-dependencies.py`, `apply-bwapi-patches.py`, `apply-openrct2-patches.sh`, `build-bwapi.sh`, `build-openrct2.sh`, `build-bridge-module.sh`, `install-openrct2-local.sh`, `install-bridge-sprites.py`, `prepare-starcraft-sprites.py`, `sprite_anchor_report.py`. Build and asset staging call these directly or through `start.sh`/`project.sh`. |
| Active capture and regression | `artifact_runs.py`, `video_capture.py`, `verify-scenario-capture.py`, `verify-frontier-capture.py`, `verify-frontier-elevation-capture.py`, `verify-frontier-lifecycle.py`, `verify-frontier-native-navigation.py`, `verify-frontier-ridge.py`, `verify-world-256-capture.py`, `create-world-256-park.py`, `world-256-park-generator.js`, `frontier-camera.js`, `frontier-lifecycle-probe.js`, `frontier-native-navigation-probe.js`, `frontier-park-sync-probe.js`, `frontier-ridge-probe.js`, `world-256-camera.js`, `world-256-scale-probe.js`, `world-actor-observer.js`, `world-actor-probe.js`, `world-client-probe.js`, `world-spawn-probe.js`, `world-target-probe.js`, `world-zerg-spawn-observer.js`, `scenario-defense-probe.js`. These are loaded by recorder/live tests or their verification helpers. |
| Legacy demonstration | `capture-live-demo.py`, `create-render-test-park.py`, `render-test-park.js`, `create-ride-siege-map.py`, `verify-ride-siege-headless.py`, `create-park-assault-map.py`, `export-park-assault-navigation.py`, `prepare-park-assault-plugin.py`, `verify-park-assault-headless.py`, `park_assault_artifacts.py`, `park_assault_verification.py`, `park_assault_visual.py`, `verify_render_fixture.py`, `demo-camera.js`, `park-assault-camera.js`, `frontier-command-probe.js`, `test-battle-feasibility.py`. The legacy capture driver, old map tests, and historical guides are their callers. |
| Redundant wrapper | `run-frontier-outpost.sh` is called by `project.sh run` and one package test. `record-frontier-outpost.py` has a generic package interface and needs only a rename. |
| Review in phase 4 | `receive-snapshots.py`, `test-bwapi-headless.py`, `test-two-clients-headless.py`, `benchmark-video-capture.py`, `render-battle-replay.py`, `squad_verification.py`, `verify-squad-frames.py`, `verify-rendered-sprites.py`. These have standalone diagnostic or replay value; inspect unique assertions before deciding. |

Native modes: `BRIDGE_SCENARIO=world` is the packaged runtime; `patrol`,
`battle`, `ride_siege`, `frontier_defense`, and `park_assault` are historical
branches in `run-bwapi.sh`, `run-openrct2-host.sh`, `BridgeAIModule.cpp`, and
`rts-bridge.js`. The low-level smoke receiver may merit a diagnostic path.

## Removal manifest

| Candidate | Current dependency | Replacement or preservation |
| --- | --- | --- |
| `run-frontier-outpost.sh`, `project.sh run` | package test, active guides | `project.sh play frontier-outpost` |
| root `frontier-outpost.json`, `frontier-outpost-mapping.json` | live tests, recorder, lifecycle verifier, Go tests | identical package copies |
| `frontier-outpost-zerg-wave.json` | wave Go/live tests | `tests/fixtures/` for v1 compatibility |
| legacy capture/map/plugin pipeline above | old tests and historical guides | packaged recorder, world/scenario tests; migrate distinct assertions first |
| legacy native and plugin branches | legacy launchers and Node tests | world adapter and world plugin regression suite |
| early smoke and replay tools | standalone scripts/tests | retain when diagnostics or assertions are distinct; remove redundant wrappers |

## Baseline gate and native dependencies

`scripts/project.sh test` passed: Go packages, C++ 3/3, Python 71/71, and five
JavaScript suites. The source tree has local build artifacts. `test-live`,
graphical recording, map generation from local fixtures, and the live shell and
Python tests require locally licensed RCT2 and StarCraft data plus built engines;
these were not run for the baseline. Live verification must report its own
results and `run-data/` evidence before any native pass claim.

## Phase 4 decisions

The v1 `receive-snapshots.py`, `test-bwapi-headless.py`, and
`test-two-clients-headless.py` expected patrol packets and native log markers
that the world adapter no longer emits. The world plugin suite and
`tests/test_world_live.sh` now cover snapshot validation, two-client identity,
movement, and synchronization. `scripts/project.sh test-live` also covers
native movement and reconnect.

Keep `benchmark-video-capture.py`: it benchmarks the packaged recorder at
several frame rates and reports client progress and FFmpeg load. Keep
`verify-rendered-sprites.py` and `verify-squad-frames.py` for exact bitmap
and gait-frame diagnostics, `squad_verification.py` for log identity and
projection checks, and `render-battle-replay.py` with its occlusion test for
historical trace replay. That replay tool is an offline diagnostic; it does
not launch a gameplay mode. `frontier-camera.js` and `world-256-camera.js`
remain current recorder probes. No shared live-test harness was introduced:
the existing tests use distinct client and reconnect setups.
