# Enemy Zerg bases: B2 verification

Branch: `enemy-zerg-bases`. B2 adds a finite native production lifecycle to
the B1 generated colony. B3 wave assignment and assaults remain unimplemented.

## Implementation

Ready generated colonies now declare 300 starting enemy minerals, at least 16
native supply units, and six maximum Zergling train orders. Both OpenBW
participants receive the starting balance; the Bumbly Bazaar native fixture
reported 18 total supply units (Hatchery plus Overlord) and no change to the
Terran's 50 starting minerals. There is no refill. Six accepted orders spend
the finite 300 mineral bank and can yield at most twelve Zerglings in a capped
colony garrison. Native `canTrain` and a fresh train check decide whether each
order is possible. The bridge never creates a compensating Zergling.

The bridge writes a versioned scenario production intent before sending an
internal order to the Zerg publisher. Request IDs are session scoped and
sequential; the order binds the authoritative Hatchery native ID, projection
proxy, revision, unit type, and native frame. The publisher keeps same-session
receipts across bridge reconnects. A pending request without a native receipt
becomes `native_receipt_missing` and is never sent again. Native rejection is
terminal for this B2 staging run. `production_exhausted`, supply failure,
native failure, and uncertain states are published in scenario status. The
StarCraft Settings window shows production state, enemy mineral balance,
Eggs, and completed Zerglings.

Native Larva and Egg morphs use the existing actor registry. The Egg's
canonical ID remains attached to its first Zergling; the second member of the
pair receives its own actor ID. Bridge readiness waits for actor reconciliation
when native Zergling counts lead actor lifecycle messages during reconnect.

## Focused results

| Check | Command or artifact | Result |
| --- | --- | --- |
| Failing first regression | `go test ./internal/world -run TestEnemyProduction` before implementation | Failed: `NewEnemyProduction` undefined. |
| Journal, schema and recovery regressions | `GOCACHE=$PWD/build/go-cache-b1 GOMAXPROCS=2 GOFLAGS=-p=2 go test ./internal/world ./cmd/world-bridge -run 'TestEnemyProduction\|TestGeneratedEnemyBase\|TestProducedZerglings' -count=1` | Pass. Full affected Go packages also passed (`cmd/world-bridge` 144.9 s). |
| Generated park, map and plugin checks | `python3 -m unittest tests.test_existing_park_defense tests.test_enemy_base_map`; all `tests/test_*plugin.js`; `node --check openrct2-plugin/rts-bridge.js`; `python3 -m json.tool bridge-protocol/world.v1.schema.json` | Pass. |
| Native module | `scripts/build-bridge-module.sh`; `ctest --test-dir build/bridge-module --output-on-failure` | Pass, 3 C++ tests. |
| Generated scenario | `TMPDIR=/tmp/starcoaster-b2-tmp GOTMPDIR=/tmp/starcoaster-b2-tmp GOCACHE=$PWD/build/go-cache-b1 GOMAXPROCS=2 GOFLAGS=-p=2 scripts/project.sh validate-scenario run-data/enemy-base-b2/exit-probe/prepared/scenario.json` | Pass. The first attempt without `TMPDIR` was blocked by the sandbox's read-only default temporary directory. |
| Ordinary park native production and reconnect | `python3 tests/test_enemy_base_production_native_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --runtime run-data/enemy-base-b2/final-probe` | Pass: all eleven checks in `verification.json`. Order 1 spent 300→250 minerals at frame 907; order 2 spent 250→200 at frame 1025; after bridge reconnect near frame 1440, order 3 spent 200→150 at frame 1473. Larva `openbw:3001` became an Egg and then a Zergling; distinct `openbw:3005` was its paired birth. Native train request and actor IDs were each unique. Source SHA-256 `84aeb880c2d5e2610d6a760eb13c087b3eefcd0683fc71aabe1b4e51cc585f44` was checked unchanged by the probe. |
| Native rejection fixtures | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft tests/test_zerg_production_rejection_native_live.sh` | The three native fixtures rejected missing Pool, insufficient minerals, and full supply without charging resources or producing Eggs. One script assertion initially failed because publisher and controller stderr text interleaved in a controller Larva line. The verifier now checks the authoritative publisher Larva; offline recheck of the same captured run passes all nine checks in `run-data/zerg-production-rejection-1794178134/verification-rechecked.json`. No second native run was made. |

The ignored `run-data/enemy-base-b2/final-probe/` directory contains the
scenario, native map, session and restart logs, journal, and checks. The source
park was copied into run-data and was not modified. No browser or Chromium
gameplay, visible two-client inspection, exhaustive finite-bank run, or full
`test-live` suite was run.

## Manual check

From the private Pi browser New Game menu, choose **Bumbly Bazaar**. In Map >
StarCraft Settings, confirm the colony becomes `native_validated`, its minerals
drop from 300 as Eggs appear, and completed Zerglings collect at the base.
Reload or rejoin and confirm no duplicate Egg, unit, or order appears. The
native probe establishes production and reconnect behavior; a graphical
client and second-client projection check remain for the user. B3 must assign
the produced units to waves and command attacks before the full milestone
playthrough can be performed.
