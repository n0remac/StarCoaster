# Enemy Zerg bases: B4 verification

Status: B4 focused hardening and native checks passed; **manual browser gameplay gate pending**. Branch `enemy-zerg-bases`, 2026-11-08. B4 code revisions: `33ef7de` (status, cache probe, blocked fixture), `41061bc` (authored native probe), and `6bfb033` (reconnect identity fix). The B3 baseline was `39ab33d`. No merge or deployment was performed.

## Focused results

| Case | Command or check | Observation and ignored evidence |
| --- | --- | --- |
| Compact authored package | `scripts/project.sh validate-scenario mt-zergling`; `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_enemy_base_authored_bootstrap_native_live.py --runtime run-data/enemy-base-b4/authored-native` | Six checks passed. Authored Hatchery/Pool remained native targets; no generated train request; source SHA-256 unchanged (`3be807b9…41`). Runtime reached frame 2307. `run-data/enemy-base-b4/authored-native/verification.json`. |
| Ordinary 100×100 park, cache and map switch | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_park_supervisor_cache_native_live.py --map 'Bumbly Bazaar.SC6' --second-map 'Extreme Heights.SC6' --cache-root run-data/enemy-base-b4/cache --runtime run-data/enemy-base-b4/supervisor-switch` | Bumbly first build 33.04 s; second selection was a validated cache hit at 14.32 s, with source staging, native map generation and isolated preflight skipped. Extreme Heights switch built in 67.70 s. New session had no inherited assault waves and used a distinct `enemy-train:<session>:1` ID. Source hashes matched. `run-data/enemy-base-b4/supervisor-switch/{verification.json,load-timings.jsonl}`. This exercised the supervisor backend selection, not a graphical New Game click; it ran before the final plugin hash change, which will require one expected cache rebuild. |
| Larger 150×150 ordinary park | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Extreme Heights.SC6' --runtime run-data/enemy-base-b4/extreme-native` | Eight checks passed: both OpenBW participants accepted Hatchery/Pool/Overlord, the park bound both structure targets, shared status reached `native_validated`, and no free wave spawned. Native train receipt spent 300→250 minerals at frame 1089; journal reached frame 1098. Source SHA-256 unchanged (`c2153130…af`). Economy site scan checked 28,476 positions and one native route; enemy base checked two sites. `run-data/enemy-base-b4/extreme-native/verification.json`. The map name and dimensions are confirmed; a separate elevation metric was not recorded. |
| Impossible enemy site | `node tests/test_economy_layout_plugin.js`; `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --fixture-no-colony --expect-blocked --runtime run-data/enemy-base-b4/blocked-colony` | The deterministic JS geometry has a ready Terran layout but no valid enemy perimeter. The native test derives an isolated Bumbly fixture with `no_valid_perimeter_site`; five checks passed: world ready, explicit blocked status, no colony targets and no free waves. The native Bumbly fixture is synthetic; it does not claim that the stock Bumbly park is unplaceable. Terran economy remained present; journal reached frame 927. Source SHA-256 unchanged (`84aeb880…5f44`). `run-data/enemy-base-b4/blocked-colony/verification.json`. |
| Same-session bridge restart | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_enemy_base_bootstrap_native_live.py '/home/pi/games/rct2/Scenarios/Extreme Heights.SC6' --runtime run-data/enemy-base-b4/extreme-reconnect-fixed --restart-bridge` | All twelve checks passed. A first train order was accepted at frame 1115. After Go bridge restart, native readiness reported two Zerglings, one with a stable map-start Larva identity and one runtime actor. Readiness resumed with 31 targets; both native participants revalidated the same Hatchery/Pool/Overlord IDs. The journal kept order `:1` and accepted a distinct order `:2` at frame 1769; no free wave spawned. Source unchanged. `run-data/enemy-base-b4/extreme-reconnect-fixed/{verification.json,restart.log,spawn-queue.json.scenario.json}`. |

The first Extreme Heights restart probe exposed a real readiness bug: one Zergling had morphed from a map-start Larva, so the bridge waited indefinitely for a runtime ID it would never receive. Failed evidence is retained in `run-data/enemy-base-b4/extreme-reconnect/`. Revision `6bfb033` has OpenBW report that static morph ID and makes Go validate it alongside runtime Zergling identities. The passing restart above used rebuilt Go and C++ binaries. It also confirmed the production journal did not duplicate its first request.

Targeted offline results: the Go enemy-base, production, assault, readiness, construction and recovery tests passed in `./internal/world ./cmd/world-bridge`; `node tests/test_world_plugin.js`, `node tests/test_economy_layout_plugin.js`, `node --check openrct2-plugin/rts-bridge.js`, and 45 Python supervisor/cache/park/protocol unit tests passed. `BRIDGE_BUILD_JOBS=2 scripts/build-bridge-module.sh` passed; `ctest --test-dir build/bridge-module --output-on-failure` passed 3/3. `scripts/project.sh validate-scenario` accepted the authored, generated and blocked packages. `git diff --check` passed.

The exact final offline commands were:

```sh
GOCACHE=$PWD/build/go-cache-b4 /usr/local/go/bin/go test ./internal/world ./cmd/world-bridge -run 'TestProducedZerglingsPermitBridgeReadinessRecovery|TestEnemyBaseB4SharedStatus|TestEnemyAssault|TestEnemyProduction|TestGeneratedEnemyBase|TestParkCatalogReadSurvivesConstructionRevision|TestBridgeTerminalDemolitionSurvivesJournalRecovery|TestSameSessionSnapshotReplaysPendingCombatDemolition|TestParkPatchStagesWithoutAdvancingConfirmedWorld' -count=1
node --check openrct2-plugin/rts-bridge.js
node tests/test_world_plugin.js
node tests/test_economy_layout_plugin.js
python3 -m unittest -q tests.test_park_session_supervisor tests.test_single_map_cache tests.test_existing_park_defense tests.test_enemy_base_map tests.test_protocol_starcraft_types
BRIDGE_BUILD_JOBS=2 scripts/build-bridge-module.sh
ctest --test-dir build/bridge-module --output-on-failure
git diff --check
```

## Bounds and status

The generator retains at most 4,096 route candidates for a map no larger than 256×256. Native base validation and route checks use OpenBW, and an impossible site leaves a blocked park with no fallback spawn. Generated production allows six native train orders; the durable assault ledger holds at most twelve waves. Failed native assault queries retry no sooner than 240 frames. The status window shows colony count, production and attack state, native block reason, and the existing difficulty, interval and enable controls. The plugin logs a meaningful state transition immediately and otherwise limits countdown/resource updates to one per five seconds. A settings-only change updates the native-frame schedule and does not rebuild the map cache.

## Manual gameplay gate

Use the private Pi browser route and the final built revision. Keep licensed RCT2 and StarCraft data local. No automated Chromium gameplay, video capture, full `test-live` run, deployment, or two-client graphical session was started for B4.

1. From the normal main menu choose **New Game** and Bumbly Bazaar, then Extreme Heights. Record the selected map, session generation and source hash; check the expected first cache rebuild after the plugin change, then a same-map cache hit.
2. In **Map > StarCraft Settings**, confirm one colony, native production state, attack countdown and difficulty/interval/enable controls. Observe Larva → Egg → Zerglings at the Hatchery and a genuine attack on the park.
3. Build Terran defenses and train Marines. Confirm one construction revision reaches both native participants before it appears synchronized. Send Marines to the colony; destroy the Spawning Pool and Hatchery. Existing attackers should continue consistently, while later training and attacks should stop without a free replacement wave.
4. Join a second graphical client during the same session, reload one client, and compare structures, actors, target health, status and orders. Restart only the Go bridge if desired; verify readiness, IDs and the train/assault journal continue without duplicate effects.
5. Record native frame, map, revision and any blocked reason if behavior differs. The final milestone acceptance remains pending these player observations, including a live base-kill and two-client visual check.

All `run-data/enemy-base-b4/` artifacts are ignored and contain no committed licensed assets. Focused tests establish native and transport behavior; they do not establish the manual graphical observations above.
