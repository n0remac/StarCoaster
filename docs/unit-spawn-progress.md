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
