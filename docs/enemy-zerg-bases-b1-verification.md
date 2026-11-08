# Enemy Zerg bases: B1 verification

Branch: `enemy-zerg-bases`. Planning checkout: `1dbfec5`. B1 implementation:
`5a08a52`. This report covers
the B1 geometry and native bootstrap only. B2 training, B3 produced-unit
assaults, and B4 browser release checks remain separate work.

## Implemented B1 behavior

Ordinary-park inspection selects a deterministic colony yard from the owned,
dry, level, clear perimeter after the Terran finite-economy site is fixed. It
reserves the Hatchery, Pool, flying Overlord supply, assembly area, and
approaches without changing the source save. The generated scenario records
policy versions, source seed, exact tiles, stable structure IDs, and an
explicit blocked reason. The cache identity is versioned.

The derived park stages visible Hatchery and Pool scenery; the native CHK map
starts exactly one completed enemy Hatchery, Pool, and Overlord. The bridge
suppresses duplicate park collision over the native structures and rejects
manual removal, mismatched snapshots, and resurrection after confirmed
destruction. Both OpenBW participants report ownership, completed structures,
supply, Pool-footprint creep, a walkable Hatchery exit and assembly tile, and
native Zergling and Marine paths toward the opposite side. Read-only checks
retry at most once per 240 native frames after a failed result or confirmed
revision and run again after bridge reconnection.

Generated scenarios use `base_production`; this B1 state creates no periodic
or manual `actor.spawn` waves. Existing authored and legacy perimeter policies
retain their original scheduler. Map > StarCraft Settings reports the colony
bootstrap or its blocking reason. No enemy training command or production
scheduler was added.

## Results

| Check | Command / evidence | Result |
| --- | --- | --- |
| Generated configuration | `scripts/project.sh validate-scenario run-data/enemy-base-b1-bumbly/exit-probe/prepared/scenario.json` and the Electric Fields blocked scenario | Pass: both v2 definitions valid. |
| Deterministic tests | `go test ./internal/world ./cmd/world-bridge` focused B1 cases; `python3 -m unittest tests.test_single_map_cache tests.test_single_map_cache_reader_races tests.test_enemy_base_map tests.test_existing_park_defense`; `node tests/test_economy_layout_plugin.js`; all `tests/test_*plugin.js` | Pass. The layout test covers deterministic seeds, varied perimeter sides, overlap, and blocked geometry. |
| C++ build and tests | `scripts/build-bridge-module.sh`; `ctest --test-dir build/bridge-module --output-on-failure` | Pass: module builds and 3 C++ tests pass. |
| Ordinary park native bootstrap | `python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --runtime run-data/enemy-base-b1-bumbly/exit-probe` | Pass. Source SHA-256 `84aeb880c2d5e2610d6a760eb13c087b3eefcd0683fc71aabe1b4e51cc585f44` unchanged. Hatchery `(31,13)`, Pool `(35,14)`, Overlord supply `(38,16)`. Both native roles validate the same colony; projections bind `scenario:enemy-hatchery` and `scenario:enemy-spawning-pool`; no free wave. Evidence: `run-data/enemy-base-b1-bumbly/exit-probe/verification.json` and `session.log`. |
| Same-session bridge restart | `python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --runtime run-data/enemy-base-b1-bumbly/recovery-probe --restart-bridge` | Pass. World readiness and native validation return on both roles; publisher native IDs remain Hatchery 5, Pool 7, Overlord 6; no free wave. Evidence: `run-data/enemy-base-b1-bumbly/recovery-probe/verification.json`, `session.log`, `restart.log`. |
| Deliberately blocked perimeter | `python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Electric Fields.SC6' --runtime run-data/enemy-base-b1-electric-fields/blocked-probe --expect-blocked` | Pass. Terran economy and park reach readiness; status is `enemy_base_waiting:no_valid_perimeter_site`; no colony targets or free waves. Source SHA-256 `4c1d07a146b058c9bb49a6b7046ea6abfbe2e887498c6a40f5e14f7d7a39eb68` unchanged. Evidence: `run-data/enemy-base-b1-electric-fields/blocked-probe/verification.json`, `session.log`. |
| Repository offline gate | `TMPDIR=/tmp/starcoaster-b1-tmp GOTMPDIR=/tmp/starcoaster-b1-tmp GOCACHE=$PWD/build/go-cache-b1 GOFLAGS=-p=2 GOMAXPROCS=2 BRIDGE_BUILD_JOBS=2 scripts/project.sh test` | Partial: all Go packages and 3 C++ tests pass; Python runs 237 tests with 1 skip, 5 supervisor-fixture errors and 1 entity-baseline assertion, then the script stops before JS. The supervisor test stub never creates the `scenarios.idx` that cache validation already requires at baseline `1dbfec5`; the entity-baseline fixture already differs from the generated catalog. All plugin JS tests passed separately. Full log: `run-data/enemy-base-b1-verification/offline.log`. |

The first two offline-gate attempts stopped because `scripts/project.sh`
redirected temporary files to `/media/pi/media1/.starcoaster-tmp`, outside
this sandbox's writable root. The final command used `/tmp` for transient
test files and kept generated build/cache output in ignored `build/`.

## Manual B1 check and remaining limits

On the private Pi browser route, start the managed service with no initial
park, choose **Bumbly Bazaar** from New Game, and inspect the Terran economy
and the Hatchery/Pool colony. In Map > StarCraft Settings confirm the colony
status becomes `native_validated`. Train a Marine through the existing Terran
economy and order it toward the colony; the focused native probe proves both
unit-type paths, while an actual browser-issued counterattack remains for the
player to check. Reload or rejoin and confirm one colony remains. Select
**Electric Fields** and confirm the blocked reason with normal park play and
no free attackers. Record the selected generation and observations under
ignored `run-data/`.

No Chromium/browser gameplay, graphical projection review, actual Marine
order, or two-client visual check was run automatically. A chosen geometry
site that fails native validation stays explicitly blocked; this B1
implementation does not try another site within the same session or build a
new base after a park edit. Reopen the edited park for a new preparation pass.
Native path checks establish route availability; they do not substitute for
the manual movement and browser display check. B2 and B3 must establish real
Larva/Egg/Zergling production and subsequent base-driven assaults.
