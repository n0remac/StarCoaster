# Legacy script consolidation verification (v0.6)

Baseline: `ace5c9e`. The five phase commits are `a99732b`, `27f4e4c`,
`fe6004f`, `ab5844b`, and the documentation commit containing this report.
The [baseline inventory](legacy-script-inventory-v0.6.md) and
[caller table](legacy-script-callers-v0.6.md) record each original script,
its callers, classification, and disposition.

## Files removed, renamed, and retained

| Disposition | Paths |
| --- | --- |
| Removed launch/config duplicates | `scripts/run-frontier-outpost.sh`, `scenarios/frontier-outpost.json`, `scenarios/frontier-outpost-mapping.json` |
| Removed legacy native path | `openbw-bwapi-module/src/ParkAssaultNavigation.h`; historical patrol, battle, siege, frontier defense, and park assault controller code in `BridgeAIModule.cpp`; equivalent plugin branches in `openrct2-plugin/rts-bridge.js` |
| Removed legacy scripts | `capture-live-demo.py`, `create-render-test-park.py`, `render-test-park.js`, `create-ride-siege-map.py`, `verify-ride-siege-headless.py`, `create-park-assault-map.py`, `export-park-assault-navigation.py`, `prepare-park-assault-plugin.py`, `verify-park-assault-headless.py`, `park_assault_artifacts.py`, `park_assault_verification.py`, `park_assault_visual.py`, `verify_render_fixture.py`, `demo-camera.js`, `park-assault-camera.js`, `frontier-command-probe.js`, `test-battle-feasibility.py`, `receive-snapshots.py`, `test-bwapi-headless.py`, `test-two-clients-headless.py` (all formerly under `scripts/`) |
| Removed obsolete tests | `tests/test_combat_plugin.js`, `tests/test_park_assault_plugin.js`, `tests/test_plugin_snapshots.js`, `tests/test_ride_siege_map.py`, `tests/test_ride_siege_plugin.js` |
| Renamed | `scripts/record-frontier-outpost.py` → `scripts/record-scenario.py`; `scenarios/frontier-outpost-zerg-wave.json` → `tests/fixtures/frontier-outpost-zerg-wave.json` |
| Retained runtime | `scripts/project.sh`, `scripts/start.sh`, `scripts/scenario_package.py`, `scripts/run-world-session.sh`, `scripts/create-park-assault.py`, `scripts/park-assault-generator.js`, both packaged scenarios, native world adapters, and the world plugin |
| Retained distinct diagnostics | `scripts/benchmark-video-capture.py`, `scripts/render-battle-replay.py` with its occlusion test, `scripts/verify-rendered-sprites.py`, `scripts/verify-squad-frames.py`, `scripts/squad_verification.py`, `scripts/frontier-camera.js`, `scripts/world-256-camera.js` |

The Frontier package's `scenario.json` and `mapping.json` are now regular,
authoritative files. Example Defense links to that package mapping. Historical
prototype reports moved to `docs/archive/`; active guides and skills describe
the packaged workflow.

Unique legacy test assertions were carried into `tests/test_world_plugin.js`,
`tests/test_park_assault_navigation.py`, current native map tests, and the
retained park generator demolition probe. These cover authority, malformed
snapshots, target generations, duplicate and failed demolition, Marine orders,
spawn status, routes, collision, and native object removal. The replay
compositor remains as an offline diagnostic because its occlusion assertion
has no equivalent current native unit test.

## Commands and results

| Phase/check | Command | Result |
| --- | --- | --- |
| Baseline | `scripts/project.sh test` | Pass: Go, C++ 3/3, Python 71, JavaScript 5 |
| CLI/config cleanup | `scripts/project.sh test`; `play frontier-outpost --plan`; `play example-defense --plan`; `record --help`; `start --help` | Pass |
| Legacy runtime removal | `scripts/build-bridge-module.sh`; `scripts/project.sh test`; `tests/test_playable_start_live.sh` | Pass: C++ module rebuilt, Python 66, world plugin, six Marines, twelve Zerglings, five ready-wave actors |
| Test/tool cleanup | `scripts/project.sh test` | Pass: Go, C++ 3/3, Python 66, world plugin |
| Final build | `scripts/project.sh build` | Pass: pinned OpenBW/BWAPI, OpenRCT2 assets, C++ module, Go bridge |
| Full native gate | `scripts/project.sh test-live` with local RCT2 and StarCraft data | Pass: ridge, native navigation, 256×256, two-client world, victory/reconnect, two actor cycles, Marine spawn, Zergling spawn, graphical playable start, and scenario runtime |
| Package park | `scripts/project.sh park example-defense` | Pass: regenerated park, fixture, navigation export |
| Example recording | `scripts/project.sh record --scenario example-defense --duration 15 --video-layout single --video-width 800` | Pass: native readiness, scenario status, 102 client snapshots, screenshots, MP4 |
| Recorder verifier regression | `python3 -m unittest discover -s tests -p 'test_scenario_record.py'` | Pass: 5 tests, including Frontier single-client park state |
| Frontier recording | Same recorder with `--scenario frontier-outpost` | First run failed a single-client park-state verifier condition. After the verifier fix and focused regression, rerun passed as a short `capture_only` check with 97 client snapshots, screenshots, MP4, and native readiness. |
| Final offline gate | `scripts/project.sh test` | Pass: Go, C++ 3/3, Python 66, world plugin |
| Reference audit | Repository search for removed names outside the historical inventory and caller table; local Markdown link check | Pass: no deleted-file references or broken local links |

The full native gate wrote evidence under ignored `run-data/`:

- `frontier-ridge-1791991135/`, `frontier-native-nav-1791991173/`, `world-256-native-1791991269/`, `world-live-1791991276/`.
- `frontier-lifecycle/cycle-1/` and `cycle-2/`; `actor-live-1791991310/`, `actor-live-1791991355/`, and `actor-lifecycle-1791991310/verification.json`.
- `unit-spawn-live-1791991400/`, `zerg-spawn-live-1791991410/`, `playable-start-1791991439/`, and `scenario-runtime-live-1791991449/verification.json`.
- `artifacts/20261014T152603Z-970eb60c8bed/` (Example Defense) and `artifacts/20261014T152739Z-9867e3a6b53b/` (Frontier Outpost).

The two 15-second recordings verify capture and playback artifacts. They are
single-client smoke captures, not full 85-second two-client gameplay videos.
The full live gate supplied the two-client combat, navigation, lifecycle,
spawning, and wave evidence. Licensed assets and local captures remain ignored.
