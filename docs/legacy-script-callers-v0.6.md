# Baseline script callers (v0.6)

Static source inventory from `ace5c9e` for all 77 tracked `scripts/` files. The caller column searches scripts, tests, native adapters, and plugin code for a filename or Python module import; dynamic file staging and developer CLI dispatch are described in the [removal manifest](legacy-script-inventory-v0.6.md). Documentation callers were audited separately during phase 5. A dash means standalone/manual use or a dynamic caller.

| Baseline script | Class | Source callers at baseline | v0.6 disposition |
| --- | --- | --- | --- |
| `scripts/apply-bwapi-patches.py` | Shared utility | `scripts/build-bwapi.sh`, `tests/test_bwapi_patches.py` | Retained |
| `scripts/apply-openrct2-patches.sh` | Shared utility | `scripts/build-openrct2.sh` | Retained |
| `scripts/artifact_runs.py` | Shared utility | `scripts/capture-live-demo.py`, `scripts/record-frontier-outpost.py`, `scripts/render-battle-replay.py`, `tests/test_artifact_runs.py`, `tests/test_video_capture.py` | Retained |
| `scripts/benchmark-video-capture.py` | Shared utility | — | Retained |
| `scripts/build-bridge-module.sh` | Shared utility | `scripts/park_assault_verification.py`, `scripts/project.sh`, `scripts/run-bwapi.sh` | Retained |
| `scripts/build-bwapi.sh` | Shared utility | `scripts/project.sh`, `scripts/run-bwapi.sh` | Retained |
| `scripts/build-openrct2.sh` | Shared utility | `scripts/project.sh`, `scripts/run-openrct2-host.sh` | Retained |
| `scripts/capture-live-demo.py` | Legacy demonstration | `scripts/frontier-command-probe.js`, `tests/test_video_capture.py` | Removed; packaged world path |
| `scripts/check-dependencies.py` | Shared utility | `scripts/build-bridge-module.sh`, `scripts/build-bwapi.sh`, `scripts/build-openrct2.sh`, `scripts/capture-live-demo.py`, `scripts/install-openrct2-local.sh`, `+3 more` | Retained |
| `scripts/create-park-assault-map.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py`, `scripts/run-bwapi.sh`, `tests/test_park_assault_map.py`, `tests/test_park_assault_navigation.py` | Removed; packaged world path |
| `scripts/create-park-assault.py` | Active runtime | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py`, `scripts/project.sh`, `scripts/scenario_package.py`, `tests/test_frontier_park_geometry.py`, `+4 more` | Retained |
| `scripts/create-render-test-park.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/render-test-park.js` | Removed; packaged world path |
| `scripts/create-ride-siege-map.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/create-park-assault-map.py`, `scripts/run-bwapi.sh`, `scripts/verify-ride-siege-headless.py`, `tests/test_ride_siege_map.py` | Removed; packaged world path |
| `scripts/create-world-256-park.py` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/create-world-base-map.py` | Active runtime | `scripts/record-frontier-outpost.py`, `scripts/run-bwapi.sh`, `scripts/run-world-session.sh`, `scripts/scenario_package.py`, `scripts/verify-frontier-lifecycle.py`, `+8 more` | Retained |
| `scripts/demo-camera.js` | Legacy demonstration | `scripts/capture-live-demo.py` | Removed; packaged world path |
| `scripts/export-park-assault-navigation.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py` | Removed; packaged world path |
| `scripts/fetch-upstream.py` | Shared utility | `scripts/start.sh`, `tests/test_scenario_start.py` | Retained |
| `scripts/frontier-camera.js` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/frontier-command-probe.js` | Legacy demonstration | `scripts/capture-live-demo.py` | Removed; packaged world path |
| `scripts/frontier-lifecycle-probe.js` | Active regression | `scripts/verify-frontier-lifecycle.py` | Retained |
| `scripts/frontier-native-navigation-probe.js` | Active regression | `tests/test_frontier_native_navigation_live.sh` | Retained |
| `scripts/frontier-park-sync-probe.js` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/frontier-ridge-probe.js` | Active regression | `scripts/record-frontier-outpost.py`, `tests/test_frontier_ridge_live.sh` | Retained |
| `scripts/frontier_geometry.py` | Active runtime | `tests/test_frontier_park_geometry.py` | Retained |
| `scripts/install-bridge-sprites.py` | Shared utility | `scripts/apply-openrct2-patches.sh`, `scripts/capture-live-demo.py`, `tests/test_sprite_registry.py` | Retained |
| `scripts/install-openrct2-local.sh` | Shared utility | `scripts/run-openrct2-host.sh`, `scripts/start.sh`, `tests/test_scenario_start.py` | Retained |
| `scripts/park-assault-camera.js` | Legacy demonstration | `scripts/capture-live-demo.py` | Removed; packaged world path |
| `scripts/park-assault-generator.js` | Active runtime | `scripts/create-park-assault.py`, `scripts/scenario_package.py` | Retained |
| `scripts/park-scenario.py` | Active runtime | `scripts/project.sh`, `tests/test_scenario_packages.py` | Retained |
| `scripts/park_assault_artifacts.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py` | Removed; packaged world path |
| `scripts/park_assault_verification.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/verify-park-assault-headless.py` | Removed; packaged world path |
| `scripts/park_assault_visual.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/verify_render_fixture.py` | Removed; packaged world path |
| `scripts/park_navigation.py` | Active runtime | `openbw-bwapi-module/src/ParkAssaultNavigation.h`, `scripts/create-park-assault.py`, `scripts/export-park-assault-navigation.py`, `scripts/park_assault_artifacts.py`, `scripts/park_assault_verification.py`, `+3 more` | Retained |
| `scripts/play-scenario.py` | Active runtime | `scripts/project.sh`, `scripts/run-frontier-outpost.sh`, `scripts/start.sh`, `tests/test_scenario_packages.py`, `tests/test_scenario_start.py` | Retained |
| `scripts/prepare-park-assault-plugin.py` | Legacy demonstration | `scripts/capture-live-demo.py`, `scripts/run-openrct2-host.sh` | Removed; packaged world path |
| `scripts/prepare-starcraft-sprites.py` | Shared utility | `scripts/capture-live-demo.py`, `scripts/install-bridge-sprites.py`, `scripts/render-battle-replay.py`, `scripts/start.sh`, `tests/test_scenario_start.py`, `+1 more` | Retained |
| `scripts/project.sh` | Active runtime | `scripts/start.sh`, `tests/test_playable_start_live.sh`, `tests/test_scenario_packages.py`, `tests/test_scenario_start.py`, `tests/test_terrain_export_live.py` | Retained |
| `scripts/receive-snapshots.py` | Legacy demonstration | `scripts/test-bwapi-headless.py` | World live tests and plugin suite |
| `scripts/record-frontier-outpost.py` | Redundant wrapper | `scripts/benchmark-video-capture.py`, `scripts/project.sh`, `tests/test_scenario_record.py` | Renamed to `record-scenario.py` |
| `scripts/render-battle-replay.py` | Shared utility | `tests/test_battle_replay_occlusion.py` | Retained |
| `scripts/render-test-park.js` | Legacy demonstration | `scripts/create-render-test-park.py` | Removed; packaged world path |
| `scripts/run-bwapi.sh` | Active runtime | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py`, `scripts/run-world-session.sh`, `scripts/start.sh`, `scripts/test-battle-feasibility.py`, `+4 more` | Retained |
| `scripts/run-frontier-outpost.sh` | Redundant wrapper | `scripts/project.sh`, `tests/test_scenario_packages.py` | `project.sh play frontier-outpost` |
| `scripts/run-openrct2-host.sh` | Active runtime | `scripts/capture-live-demo.py`, `scripts/park_assault_verification.py`, `scripts/run-world-session.sh`, `scripts/test-two-clients-headless.py`, `tests/test_terrain_export_live.py` | Retained |
| `scripts/run-world-session.sh` | Active runtime | `scripts/play-scenario.py`, `scripts/record-frontier-outpost.py`, `scripts/verify-frontier-lifecycle.py`, `tests/test_actor_live.sh`, `tests/test_frontier_native_navigation_live.sh`, `+7 more` | Retained |
| `scripts/scenario-defense-probe.js` | Active regression | `tests/test_scenario_runtime_live.py` | Retained |
| `scripts/scenario_package.py` | Active runtime | `scripts/park-scenario.py`, `scripts/play-scenario.py`, `scripts/record-frontier-outpost.py`, `tests/test_scenario_packages.py` | Retained |
| `scripts/sprite_anchor_report.py` | Shared utility | `scripts/capture-live-demo.py` | Retained |
| `scripts/squad_verification.py` | Shared utility | `scripts/capture-live-demo.py`, `scripts/render-battle-replay.py`, `scripts/test-two-clients-headless.py`, `scripts/verify-squad-frames.py`, `scripts/verify_render_fixture.py`, `+2 more` | Retained |
| `scripts/starcraft_map_pack.py` | Active runtime | `scripts/create-world-base-map.py`, `tests/test_frontier_scenario_map.py`, `tests/test_world_base_map.py` | Retained |
| `scripts/start.sh` | Active runtime | `scripts/project.sh`, `tests/test_playable_start_live.sh`, `tests/test_scenario_start.py` | Retained |
| `scripts/test-battle-feasibility.py` | Legacy demonstration | — | Removed; packaged world path |
| `scripts/test-bwapi-headless.py` | Legacy demonstration | — | World live tests and plugin suite |
| `scripts/test-two-clients-headless.py` | Legacy demonstration | — | World live tests and plugin suite |
| `scripts/verify-frontier-capture.py` | Active regression | `scripts/record-frontier-outpost.py`, `tests/test_scenario_record.py` | Retained |
| `scripts/verify-frontier-elevation-capture.py` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/verify-frontier-lifecycle.py` | Active regression | `scripts/project.sh` | Retained |
| `scripts/verify-frontier-native-navigation.py` | Active regression | `tests/test_frontier_native_navigation_live.sh` | Retained |
| `scripts/verify-frontier-ridge.py` | Active regression | `scripts/record-frontier-outpost.py`, `tests/test_frontier_ridge_live.sh` | Retained |
| `scripts/verify-park-assault-headless.py` | Legacy demonstration | — | Removed; packaged world path |
| `scripts/verify-rendered-sprites.py` | Shared utility | — | Retained |
| `scripts/verify-ride-siege-headless.py` | Legacy demonstration | — | Removed; packaged world path |
| `scripts/verify-scenario-capture.py` | Active regression | `scripts/record-frontier-outpost.py`, `tests/test_scenario_record.py` | Retained |
| `scripts/verify-squad-frames.py` | Shared utility | — | Retained |
| `scripts/verify-world-256-capture.py` | Active regression | `scripts/record-frontier-outpost.py`, `tests/test_scenario_record.py` | Retained |
| `scripts/verify_render_fixture.py` | Legacy demonstration | `scripts/capture-live-demo.py` | Removed; packaged world path |
| `scripts/video_capture.py` | Shared utility | `scripts/capture-live-demo.py`, `scripts/record-frontier-outpost.py`, `scripts/render-battle-replay.py`, `tests/test_live_squad_artifacts.py`, `tests/test_video_capture.py` | Retained |
| `scripts/world-256-camera.js` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/world-256-park-generator.js` | Active regression | `scripts/create-world-256-park.py`, `scripts/record-frontier-outpost.py` | Retained |
| `scripts/world-256-scale-probe.js` | Active regression | `scripts/record-frontier-outpost.py` | Retained |
| `scripts/world-actor-observer.js` | Active regression | `tests/test_actor_live.sh`, `tests/test_unit_spawn_live.sh` | Retained |
| `scripts/world-actor-probe.js` | Active regression | `tests/test_actor_live.sh` | Retained |
| `scripts/world-client-probe.js` | Active regression | `tests/test_world_live.sh` | Retained |
| `scripts/world-spawn-probe.js` | Active regression | `tests/test_unit_spawn_live.sh` | Retained |
| `scripts/world-target-probe.js` | Active regression | `tests/test_world_live.sh` | Retained |
| `scripts/world-zerg-spawn-observer.js` | Active regression | `tests/test_unit_spawn_zerg_live.sh` | Retained |
