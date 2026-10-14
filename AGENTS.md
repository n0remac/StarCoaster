# StarCoaster development guide

OpenRCT2 owns the park, scenery, rides, multiplayer state, and rendering. OpenBW owns unit movement, pathfinding, health, and combat. The Go world bridge coordinates snapshots and commands between them; do not duplicate either engine's authority in an adapter or test probe.

## Source map

- `openrct2-plugin/` and `openrct2-patches/`: park synchronization, player controls, and native rendering.
- `openbw-bwapi-module/`: OpenBW/BWAPI bridge, actor state, and native navigation.
- `cmd/world-bridge/`, `internal/world/`: Go transport, world model, scenario coordination.
- `scenarios/`: current gameplay configuration; `scripts/`: builds, launchers, park generation, captures; `tests/`: regressions.
- `bridge-protocol/`: versioned wire contracts. `docs/archive/`: historical specifications. `upstream/`, `build/`, and `run-data/` are local, ignored inputs or outputs.

## Standard commands

```sh
scripts/project.sh build
scripts/project.sh park example-defense
scripts/project.sh play frontier-outpost
scripts/project.sh test
scripts/project.sh test-live
scripts/project.sh record --duration 85
```

`start [--scenario ID]` performs the full fetch/build/stage/play flow;
`play ID` uses an existing build. `park [ID]` force-generates only that package's
park, fixture, and navigation data; `record [--scenario ID]` captures it.
All default to `frontier-outpost` except `play`, which requires an ID.
Supported packages are `frontier-outpost` and `example-defense`; use
`play ID --plan` to inspect paths. `scripts/scenario_package.py` owns package
resolution and preparation; `scripts/run-world-session.sh` launches gameplay.

Use the relevant unit tests before live graphical tests. Preserve navigation, combat, synchronization, and rendering regressions when refactoring. Park changes must keep structure footprints, spawn points, chokepoints, and destructible openings aligned with the scenario and native map. Keep generated parks and captures deterministic where possible.

Terrain or navigation changes also require `tests/test_frontier_ridge_live.sh`, `tests/test_frontier_native_navigation_live.sh`, and `python3 tests/test_world_256_native_live.py` with local licensed game data. The ridge run checks actor positions below the cliff, through a native slope, and during combat. For graphical elevation and 256×256 scale evidence, use `scripts/project.sh record --help` and the test-only `--ridge-probe`, `--ridge-assault`, and `--world-256` options. Review `docs/world-geometry-milestone.md` and the ignored verification JSON before claiming success. The scale park generator uses a local OpenRCT2 fixture; never commit its saved park or capture.

Changes to the playable launcher, starting units, or automatic waves also require `tests/test_playable_start_live.sh`: it starts the normal graphical client under Xvfb and checks that six starting Marines, twelve starting Zerglings, and the five-unit ready wave appear in client snapshots. The saved park must have layout version 4 so path ramps face uphill in OpenRCT2.

`scripts/project.sh test-live` includes `tests/test_actor_lifecycle_live.sh`: two native actor cycles with client reconnect, bridge restart, death, and post-death command rejection. Keep its test-only spawn and probe scripts out of player-facing flows. Record both cycle paths when changing actor lifecycle behavior.
It also runs `python3 tests/test_scenario_runtime_live.py` headlessly to verify
waves, manual Marine reinforcements, bridge recovery, and client synchronization.

Dynamic spawn changes also require `tests/test_unit_spawn_live.sh` and `tests/test_unit_spawn_zerg_live.sh` with local licensed game data. Use `BRIDGE_SPAWN_RECOVERY=1 BRIDGE_TEST_KILL_RUNTIME_MARINE_FRAME=450` to test two-client reconnect, bridge restart, death and replacement. Use `BRIDGE_TEST_DISCONNECT_SPAWN_INDEX=2` to interrupt native creation after issue and verify the in-flight request reconciles without duplication. These hooks and `scripts/world-spawn-probe.js` are test-only. Record each run directory and verify unique native actor IDs and both participant bindings.

Never commit user supplied RCT2 or StarCraft data, extracted sprites, proprietary graphics, local captures, or bundled engine builds. Follow `docs/licensing.md` and check staged paths before committing.

Report the commands run, pass or fail results, artifact paths, and remaining limits. If a live test cannot run, state the missing dependency or failure plainly. See `README.md` for the current playable workflow and `docs/first-playable-verification.md` for the prior baseline.

Reusable workflows live in `.agents/skills/starcoaster-verify/`, `.agents/skills/starcoaster-demo/`, and `.agents/skills/starcoaster-park-design/`.
