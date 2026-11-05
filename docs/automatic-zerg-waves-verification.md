# Automatic Zerg waves: validation record

Baseline: `61a065e` on branch `automatic-zerg-waves`. No public service was restarted, no Caddy change was made, and no bundle was deployed.

## Behavioral tests written before their implementation

- `python3 -m unittest tests.test_existing_park_defense.ExistingParkDefenseTest.test_creates_private_package_without_changing_source` failed with `KeyError: 'spawn_policy'` before the generated policy was added.
- `go test ./internal/world -run TestAutomaticPerimeterStartsAtReadyFrameAndKeepsCommittedZone` failed with `invalid scenario configuration` before the automatic policy was accepted.
- `cmake --build build/bridge-module --target world_assault_controller_test -j2` failed because `interiorRallies` did not exist before the native inward rally implementation.
- `go test ./internal/world -run TestAutomaticJournalRequiresVersionWhileLegacyJournalRemainsReadable` failed to compile because `JournalVersion` did not exist before the compatibility rule was added.
- The native-query Go regression initially failed to compile because the pending perimeter query state and response handler did not exist. It passed after commit `83e4481`.
- The first `node tests/test_world_plugin.js` attempt failed at the legacy manual-wave button because the new fixture disabled its eligibility. After separating legacy and automatic fixtures, the automatic UI assertion failed because the harness kept the old manual window open. Closing it in the harness let the new automatic controls pass. These are harness corrections, not proof that the requested UI behavior failed before implementation.

## Passing offline validation

- `python3 -m unittest tests.test_existing_park_defense tests.test_single_map_cache`: 14 tests passed.
- `GOMAXPROCS=2 GOCACHE=/tmp/starcoaster-go-cache /usr/local/go/bin/go test -p 2 ./... -timeout=90s`: all Go packages passed before the journal-version and revision-refresh follow-up; focused `TestAutomatic*` checks passed after it.
- `cmake --build build/bridge-module --target world_assault_controller_test -j2` and `ctest --test-dir build/bridge-module -R '^world_assault_controller_test$' --output-on-failure`: passed.
- `node tests/test_world_plugin.js`: passed.
- `TMPDIR=/tmp/starcoaster-waves GOCACHE=/tmp/starcoaster-go-cache GOMAXPROCS=2 BRIDGE_BUILD_JOBS=2 scripts/project.sh test`: passed after the native query change. Go bridge tests, all three C++ tests, 182 Python tests with one skip, and JavaScript checks passed. Earlier attempts stopped at sandbox paths; a separate 60-second Go timeout ended during the existing 24-wave USB journal test, while the full gate passed with its normal time allowance.
- `node --check tests/universal-defense-probe.js`, `python3 -m py_compile tests/test_universal_park_defense_live.py`, and `git diff --check`: passed for the isolated live-probe commit `0522a3e`.

The pinned OpenRCT2 source places `ui.registerMenuItem` entries in `TopToolbar::initMapMenu` and invokes them in `mapMenuDropdown`. The normal menu path is **top toolbar Map → StarCraft Settings**. The same script and dropdown path are built for native and WASM clients. This source trace is menu access evidence; a graphical capture remains outstanding.

## Native preflight and remaining limits

Commit `83e4481` added a precommit `scenario.perimeter.query` to the OpenBW publisher. For each proposed local tile, native code checks placement on its current navigation mask against live occupancy using the dimensions of every unit type in that wave, samples native walkability across the footprint, checks destination footprint clearance, and uses BWAPI `Game::hasPath(source, destination)` for region connectivity. Go accepts at least four native-valid tiles including the anchor, then journals the wave before any spawn request. Rejected candidates are sampled without replacement, up to 64 per due wave; no accepted candidate leaves the session waiting and creates no wave intent. The focused Go query lifecycle test and native module build passed. Both live runs below exercised this query in the native bridge before journaling and spawning.

## Isolated native runs after `83e4481`

The native module and Go bridge were rebuilt with at most two build jobs. The complete OpenRCT2 rebuild could not finish in this sandbox because `ccache` tried to create `/home/pi/.cache/ccache/tmp`, which is read only; OpenRCT2 source was unchanged, so the existing pinned executable was used. Both runs used free, isolated ports `OPENRCT2_PORT=12153`, `STARCOASTER_BRIDGE_PORT=42110`, `BRIDGE_OPENBW_PORT=42111`, `BRIDGE_CONTROLLER_PORT=42112`, with locally licensed `RCT2_DATA_DIR=/home/pi/games/rct2` and `STARCRAFT_DATA_DIR=/home/pi/games/starcraft`. They ran sequentially and did not touch the managed public game.

- Ordinary generated `frontier-outpost-playable.park`: `python3 tests/test_universal_park_defense_live.py` passed readiness-based automatic startup, 120-second preparation, `periodic-0001`, eight clustered native Zerglings, and inward motion. Report: `run-data/universal-park-defense-live/ordinary-verification.json`. Journal: `run-data/scenarios/park-defense-88c847abaa722fc4/spawn-queue.json.scenario.json`; selected anchor `[59,30]`, interior `[51,30]`. This is a generated ordinary park, not a stock or water-heavy park. Its original session/client logs were overwritten by the next run before the harness gained unique run directories; the report and journal remain.
- Generated 256 × 256 `world-256-scale.park`: the same command with `UNIVERSAL_DEFENSE_SOURCE=$PWD/run-data/world-256-park/world-256-scale.park` passed all seven report checks. Evidence: `run-data/universal-park-defense-live/large-map-evidence/verification.json`, `session.log`, and `client.log`; journal: `run-data/scenarios/park-defense-78073086a413ed68/spawn-queue.json.scenario.json`. Session `f1a8340a1f7a809e20a5978471ac2465` matched the journal; selected anchor `[253,34]`, interior `[243,34]`; eight Zerglings were ready inside the selected cluster and a tracked actor moved toward the interior. This proves the query and movement on this generated large park only. An earlier large-map attempt read the deadline before the first complete frame and failed in the harness; its report is `run-data/universal-park-defense-live/large-map-first-attempt.json`.

The live harness now creates a unique run directory for each launch and verifies the journal session against the `WORLD_SNAPSHOT` session in that run's log. This closes the stale-journal false-positive risk in subsequent checks. The two reports above predate that harness change and use copied evidence paths; the large-map log copies are preserved in `large-map-evidence`.

`Game::hasPath` compares native region groups. It does not take a unit type or prove corridor width for an Ultralisk; the query checks that unit's dimensions at the origin and destination, not every point along its route. Actual `Unit::hasPath` after spawn uses the same region check plus unit corner fallbacks. Terrain elevation and dynamic obstruction can still prevent an attack from reaching the selected destination, and 64 rejected samples can leave a valid anchor untried until the next retry. The focused tests cover no mask route, all four sides on an open 64 × 64 map, a rectangular map with a blocked center, revision reselection before submission, immutable selection after submission, durable recovery, and readiness timing. They do not prove water-heavy, elevation, large-unit corridor, or fully blocked native-region behavior.

Stock and water-heavy park checks, restart, mixed-client and browser gameplay, cache rebuild/reuse timing, and graphical settings access are tracked in `docs/automatic-zerg-waves-plan.md`. The full milestone remains open.
