# v0.3.1 unit spawning progress

## Phase 1 — actor creation reliability

- Branch: `feat/reliable-unit-spawning-v0.3.1`; base: `12d583e`.
- Publisher captures native Marine and Zergling creation events before adapter readiness, retains them until registry preparation, and publishes them after readiness or during reconciliation. Destruction removes pending creations so delayed events cannot resurrect dead units.
- Controller retains unmatched native creation candidates while their units live. Registry preparation excludes pending runtime creations from the six Marine and initial Zergling position based ID assignment.
- Added a Go actor recovery test for interrupted publisher and controller binding, replay, and death tombstones.
- Passed: baseline and post-change Go unit tests, JavaScript plugin tests at baseline, C++ module build, CTest, and `git diff --check`.
- Live test attempted: `tests/test_actor_live.sh` failed immediately because `RCT2_DATA_DIR` is unset. Native reconnect behavior remains unverified in this workspace.
- Next: Phase 2, add validated spawn protocol, bounded idempotent queue, and mock protocol tests.

## Phase 2 — spawn protocol and request queue

- Prior HEAD: `b569133`.
- Added `unit.spawn.request`, `execute`, `status`, `query`, and `cancel` contracts. The Go bridge validates session, game state, request parameters, park bounds, faction, queue capacity, and live actor capacity, then transforms coordinates and issues one native creation at a time.
- The queue preserves per-unit outcomes and request ID idempotence. Native rejection advances a batch; interrupted creation becomes `uncertain`. A journal under `run-data/` preserves requests across a bridge restart without retrying uncertain native creation.
- Mocked Go tests cover a transformed native execution, idempotent retry, native rejection, invalid park position, unauthorized enemy request, journal recovery, five-unit serialization, partial failure, queue overflow, and stale session.
- Native execution is intentionally absent until Phase 3. The live actor test still needs `RCT2_DATA_DIR`.
- Next: Phase 3, implement OpenBW native execution, placement validation, request correlation, and reconciliation of journaled uncertain units.

## Phase 3 — native OpenBW spawning

- Prior HEAD: `705e756`.
- The publisher handles `unit.spawn.execute` with BWAPI `createUnit`, resolves ownership from the existing native armies, checks compact offsets against park navigation, native walkability, map bounds, and occupied units, then waits for the native creation event. It registers through `WorldActorRegistry` and reports the canonical actor ID and actual native position. Replayed execute commands cannot create another unit.
- The bridge marks a result ready only after publisher and controller bindings. It handles native rejection, uncertain creation, and death before ready. The old environment-driven Marine fixture now calls the same native execution path.
- Passed: `scripts/build-bridge-module.sh`, CTest, Go focused tests including binding completion, `tests/test_actor_live.sh` after correcting owner resolution, and `tests/test_unit_spawn_live.sh` with five sequential native Marines, two eleven-Marine clients, and accepted native move and attack orders.
- Failed earlier runs: `run-data/actor-live-1791866646/` and `run-data/actor-live-1791866801/` exposed fixture placement and ambiguous race-only owner selection; both were fixed. The first two unit-spawn runs exposed nondeterministic client join order in the test; the test now joins the commander first.
- Passing artifacts: `run-data/actor-live-1791866966/` and `run-data/unit-spawn-live-1791867143/`.
- Next: Phase 4, finish and commit the OpenRCT2 spawn tool, status feedback, and action-path regression tests.

## Phase 4 — OpenRCT2 Marine reinforcement tool

- Prior HEAD: `b5187d5`.
- Added a five-choice count selector and Spawn Marine placement tool to the squad window. The action uses OpenRCT2's synchronized action path, checks the authenticated commander, and sends the player's park coordinates without a native owner. Escape cancels placement; the Select button restores Marine selection. Spawn status is synchronized to clients and shown in the window.
- Existing snapshots, native sprites, hit testing, squad selection, control groups, and orders include the new Marines without a new render path.
- Passed: `node tests/test_world_plugin.js`, `node tests/test_plugin_snapshots.js`, `node --check`, `scripts/project.sh test`, and the earlier five-Marine live action run in `run-data/unit-spawn-live-1791867143/`. The live test joined client A first so its authenticated player became commander.
- Next: Phase 5, submit trusted scenario Zergling waves through the same request queue and verify native combat.
