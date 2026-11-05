# E0 verification: native player economy under park navigation

Date: 2026-11-05. Branch: `economy-e0`, based on plan commit `3d3b43e`.
Scope: E0 only. No E1-E5 player workflow, browser economy, merge, or deployment.

## Fixture and method

`tests/create_player_economy_e0_map.py` packs a fresh, test-only 256-tile CHK
using the pinned map source. The regular Frontier Outpost park supplies the
mapped RCT terrain/navigation mask. A completed Terran Command Center and two
SCVs start on the level open strip at park row 8. Two mineral fields start at
1,500 each and one geyser at 5,000. The CHK `UNIT` entries use owner slot 11
and `valid_properties=0x10` for explicit resource quantities, matching the
pinned OpenBW loader. The runtime exposes the neutral owner as BWAPI ID `-1`.
CHK record IDs 3000-3005 are **not** runtime native IDs; the loader discards
those record IDs. The test starts at 400 minerals and zero gas to fund its
construction sequence, with no map-only supply fixture or periodic refill.
This is a probe balance, not the proposed 50-mineral player start for E1.

`BRIDGE_TEST_ECONOMY_E0=1` enables a test-only BWAPI probe in both participants.
Only the Terran controller issues worker orders. The probe waits until the
mapped navigation mask is applied, then orders gather, native build, stop,
right-click resume, cancel, Refinery build, gas gather, and native kill. The
publisher independently observes the state. The live script uses four unique
loopback ports, isolated `run-data/`, two native participants, the normal
OpenRCT2 park host, and a bridge process restart without restarting OpenBW.

## Exact commands and results

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.test_player_economy_e0_map -v` | PASS, one fixture/CHK test. |
| `BRIDGE_BUILD_JOBS=1 scripts/build-bridge-module.sh`, then `cmake --build build/bridge-module --target BridgeAIModule --parallel 1` for each probe edit | PASS, test-scoped native probe built with one job. |
| `TMPDIR=/tmp GOCACHE=$PWD/build/go-cache GOFLAGS=-p=2 GOMAXPROCS=2 BRIDGE_BUILD_JOBS=1 scripts/project.sh test` | PASS: Go packages, 3 C++ tests, 214 Python tests (1 skipped), plugin checks; final committed-source rerun. |
| `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft bash tests/test_player_economy_e0_native_live.sh` | PASS, all 22 focused native assertions on the final run. |
| `bash -n tests/test_player_economy_e0_native_live.sh scripts/run-world-session.sh` and `git diff --check` | PASS. |

Final ignored evidence: `run-data/player-economy-e0-1793905486/` contains
`economy-e0.scm`, `session.log`, `bridge-restart.txt`, `verification.json`,
and isolated host/native runtime files. The live run returned zero, and its
listeners were gone after cleanup. Earlier failures are preserved under
`run-data/player-economy-e0-1793904131/` and
`run-data/player-economy-e0-1793904273/` (premature build on a partly explored
footprint), `run-data/player-economy-e0-1793904488/` (worker busy on the
completion frame), and `run-data/player-economy-e0-1793904656/`
(`removeUnit` crash). `run-data/player-economy-e0-1793904893/` passed the
economy checks but failed a log-marker assertion that was corrected to use a
separate evidence file. `run-data/player-economy-e0-1793905176/` passed before
the restored geyser owner assertion was added. The final probe waits for full native buildability
and worker availability, and uses native kill for demolition.

## Decisive native observations

Both roles applied mask `7ebb60776c831bd5` at frame 499, before the first
gather command. After the bridge restart, the same mask was applied again at
publisher frame 1995 and controller frame 1997; the two `WORLD_READY` reports were
`navigation=native`. Its logged 48×48 candidate scan found 1,419 native
Depot sites; the selected upper-left native tile `(135,104)` was explored,
walkable, and `canBuildHere=1`. The initial failed run showed why one-tile
exploration is insufficient: `isExplored(135,104)=1` while the full footprint
still returned `Unbuildable_Location`. This is a native exploration gate, not
evidence that the mapped terrain cannot support construction.

| Frame | Native observation (Terran player ID 1 unless noted) |
| ---: | --- |
| 499 | Center ID 5; SCVs IDs 0 and 1; mineral ID 2 at 1,500 and geyser ID 4 at 5,000, each neutral owner `-1`; balance 400/0; supply 4/20 in half-units. Publisher observed the same IDs and mask. |
| 624 | SCV 0 carried mineral cargo; field had fallen to 1,492 while balance remained 400. |
| 667, 838 | First and second deliveries increased minerals `400→408→416`; field fell `1,500→1,492→1,484`. |
| 896 | SCV 1 `build(Supply_Depot, {135,104})` accepted; native balance later fell `416→316` exactly once. |
| 984, 1067, 1127 | Depot ID 263 was incomplete with 582 frames left at 984; stop accepted at 1067, and remaining time stayed 496 at frames 1080 and 1104; right-click resume accepted at 1127. |
| 1654 | Depot ID 263 completed; supply total rose `20→36` half-units, with minerals still 316. |
| 1815–1818 | Second Depot ID 264 cost 100 (`316→216`); `cancelConstruction()` accepted and native refund was 75 (`216→291`); building disappeared. |
| 1903, 2510 | `canBuildHere(Refinery,{130,104})=1` over geyser ID 4; build accepted; native cost 100 (`291→191`); completed Refinery retained native ID 4 and 5,000 gas. |
| 2658 | Gas delivery increased balance `0→8`; Refinery resource amount was 4,984 after a second gather had begun. Cargo was observed by both roles. |
| 2674–2678 | Native `killUnit` destroyed Refinery ID 4; neutral geyser reappeared as ID 274 with owner `-1` and 4,984 gas. The changed ID is decisive for generation-qualified binding. |

The verifier found no mineral increases except two native deliveries of 8
and the native cancellation refund of 75. It found one Depot build order and
one Refinery build order across the bridge restart. The bridge process was
restarted after Depot completion, while OpenBW and OpenRCT2 continued; the
second `WORLD_READY` and later gas sequence show native balances and actors
continued without replaying initialization.

## Gate result and integration boundary

E0 proves the pinned native APIs work with a confirmed park navigation mask:
worker cargo and delivery, resource quantity fields, native costs and supply,
real incomplete construction, interruption/resume, cancellation/refund,
Refinery replacement, gas delivery, and geyser restoration. No native engine
compatibility patch was required for this working path. Native ID attribution
must use observed runtime IDs, not CHK entry IDs or nearest coordinates.

The reconnect mask logs differ by two native frames, although both accepted
the same hash and subsequent native gas gathering succeeded. E1/E3 should
check confirmed-frame publication when a native-owned building changes the
park projection. The E0 fixture does **not** project its SCVs, resources, or worker-built
structures into OpenRCT2 scenery, nor does it exercise a durable build
transaction, park ownership checks, browser commands, or simultaneous park
edits. Mask application before orders and after reconnect is proved; ordering
of a future incomplete-building visual projection against native occupancy
remains an E3 test obligation. E1 can build native state and identity binding
on these observations, but should not claim a playable economy until E2/E3
command and projection paths are verified.

The test setup call `BWAPI::Game::removeUnit` on an active Refinery caused a
Terran participant segmentation fault in the preserved failed run. A native
`killUnit` after stopping the gas worker restored the geyser cleanly on both
participants. Use the verified destruction path for the next integration
probe; investigate `removeUnit` before using it for economic structures.
The initial park snapshot reported `unsupported=9` before reconnect and
`unsupported=0` afterward; the economy probe still passed, but this existing
target-resolution difference needs review when E1/E3 project entities.

Licensed RCT2 and StarCraft data were installed locally for these checks.
Initial memory was about 5.2 GiB available with 475 MiB of 511 MiB swap used;
after the final run it was about 5.4 GiB available with swap fully used.
No deployed service was changed or stopped.
