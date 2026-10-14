---
name: starcoaster-verify
description: Select StarCoaster offline, native, and graphical checks for scenario, bridge, navigation, combat, synchronization, or rendering changes.
---

# Verify StarCoaster changes

Run `scripts/project.sh test` for the Go, C++, Python, and JavaScript suite. Use `scripts/project.sh validate-scenario ID` for edited scenario configuration; it checks configuration but still requires a live geometry check. Run the affected live tests with built engines and locally licensed RCT2 and StarCraft data. `scripts/project.sh test-live` runs the full native suite; avoid running live tests concurrently because they share ports and engine processes.

| Change | Focused live checks |
| --- | --- |
| Terrain, elevation, or navigation | `tests/test_frontier_ridge_live.sh`, `tests/test_frontier_native_navigation_live.sh`, `python3 tests/test_world_256_native_live.py` |
| Generic demolition and two-client synchronization | `tests/test_world_live.sh` |
| Playable launcher, starting units, or ready wave | `tests/test_playable_start_live.sh` |
| Victory, reconnect, or bridge restart | `python3 scripts/verify-frontier-lifecycle.py` |
| Native actor lifecycle | `tests/test_actor_lifecycle_live.sh` |
| Dynamic Marine or Zergling spawning | `tests/test_unit_spawn_live.sh`, `tests/test_unit_spawn_zerg_live.sh` |
| Scenario waves, manual reinforcements, or runtime recovery | `python3 tests/test_scenario_runtime_live.py` |

For actor lifecycle changes, inspect both cycles, including client reconnect, bridge restart, death, and post-death command rejection. For spawn recovery, run `BRIDGE_SPAWN_RECOVERY=1 BRIDGE_TEST_KILL_RUNTIME_MARINE_FRAME=450 tests/test_unit_spawn_live.sh`; for in-flight reconciliation, run `BRIDGE_TEST_DISCONNECT_SPAWN_INDEX=2 tests/test_unit_spawn_live.sh`. Verify unique native actor IDs and both client bindings. These hooks and `scripts/world-spawn-probe.js` are test-only.

For terrain and scale evidence, use `scripts/project.sh record --help` for the test-only `--ridge-probe`, `--ridge-assault`, and `--world-256` captures. Review `docs/world-geometry-milestone.md` and the generated `verification.json` before claiming graphical success. For changed playable parks, check layout version 4 so path ramps face uphill in OpenRCT2. Keep saved parks, native maps, and captures under ignored `run-data/`.

Report every command's result, the relevant `run-data/` path, and unrun checks with their missing dependency or failure. Prior baselines are in `docs/archive/first-playable-verification.md` and `docs/archive/foundation-verification.md`.
