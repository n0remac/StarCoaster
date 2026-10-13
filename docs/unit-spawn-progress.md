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

## Phase 5 — trusted scenario Zergling wave

- Prior HEAD: `981fd6c`.
- Added optional `spawn_waves` scenario configuration with one `on_ready` Zergling wave in a separate Frontier Outpost test scenario. The bridge submits it internally through the same idempotent queue and native command, keyed by the authoritative session. OpenRCT2 player requests still reject Zerglings. The existing assault AI orders every Zergling owned by the native Zerg player, including new units.
- Passed: Go scenario and queue tests, `scripts/project.sh test`, and `tests/test_unit_spawn_zerg_live.sh`: five unique native Zerglings, both clients showing seventeen, native movement, and attack frames. Passing evidence: `run-data/zerg-spawn-live-1791867620/`.
- Earlier Zerg run `run-data/zerg-spawn-live-1791867462/` exposed an observer field unavailable from `getActors()`. The next run `run-data/zerg-spawn-live-1791867563/` showed native attack frames but its parser was sensitive to interleaved process logs. Both test errors were corrected.
- Next: Phase 6, full reconnect, bridge restart, death and replacement recovery, fault injection, documentation, and final gates.

## Phase 6 — recovery and full integration verification

- Prior HEAD: `627f3ad`. Phase 6 HEAD: `a98426c` (`test(bridge): verify dynamic spawning and multiplayer recovery`).
- Added explicit native reconciliation for an uncertain spawn. The publisher replays a terminal result or reports `not_received`; only that report allows the bridge to issue the command again. A native death after creation but before binding is retained as a terminal failure through bridge reconnection. The Go queue tests cover a partial batch journal, explicit unreceived retry, death before binding, and client status query after disconnect.
- Extended the two-client Marine live test to reconnect client B, restart the Go bridge, kill `openbw:3001` through a test-only native hook, request and command replacement `openbw:3006`, and verify no duplicate IDs. A second deterministic hook disconnects the publisher after index 2 is issued; the batch reconciles and completes without reissuing that native creation. The standard live gate now includes Marine and Zergling spawn tests.
- The generic two-client target-removal test now waits for the complete server target catalog and joins client A before B. A previous simultaneous-join run timed out with `Invalid attack target`; the focused rerun and final full gate passed.
- Passed final gates: `PATH=/usr/local/go/bin:$PATH go test ./...`, both required Node plugin tests, CTest (3/3), `scripts/project.sh build`, `scripts/project.sh test`, and `scripts/project.sh test-live`. The final full live artifacts are `run-data/frontier-native-nav-1791869110/`, `run-data/world-live-1791869165/`, `run-data/actor-lifecycle-1791869198/verification.json`, `run-data/unit-spawn-live-1791869292/`, and `run-data/zerg-spawn-live-1791869301/`. Final focused recovery and in-flight disconnect artifacts are `run-data/unit-spawn-live-1791869341/` and `run-data/unit-spawn-live-1791869365/`.
- The first bare `go test ./...` command failed because this shell does not include `/usr/local/go/bin` in `PATH`; the same installed Go binary passed with that path set. Earlier recovery attempts `run-data/unit-spawn-live-1791868058/` and `run-data/unit-spawn-live-1791868296/` exposed unsafe test attack travel and an occupied replacement cell, both corrected. One full live attempt `run-data/world-live-1791868935/` timed out in the generic target probe before the ordered-join test fix.
- Unverified: a graphical recording of a mouse click on the Spawn Marine placement tool. The OpenRCT2 synchronized action and two-client native spawning path were exercised headlessly. No known unresolved duplicate-identity or request-retry defect remains in the tested paths. Static navigation, the 256-unit snapshot ceiling, and direct spawn without production buildings remain milestone limits.
- Next phase: v0.3.1 implementation is complete. The next gameplay milestone may add ongoing Zerg attack waves and Terran production or reinforcement rules using the shared spawn queue.

## Commit map for session recovery

| Phase | Commit | Outcome |
| --- | --- | --- |
| 1 | `b569133` | Actor creation recovery across adapter readiness and bridge connectivity |
| 2 | `705e756` | Validated, journaled, idempotent spawn protocol and queue |
| 3 | `b5187d5` | Native OpenBW Marine creation and shared actor binding |
| 4 | `981fd6c` | OpenRCT2 Marine placement tool and synchronized action |
| 5 | `627f3ad` | Trusted scenario Zergling waves through the same queue |
| 6 | `a98426c` | Reconciliation, final live gates, and verification report |
