# Enemy Zerg bases: B3 verification

Branch: `enemy-zerg-bases`. Implementation commit: `462229c`.
B3 assigns already produced native Zerglings to durable waves and gives them
native attack moves. B4 integration and the human graphical gate remain open.

## Behavior

The `base_production` policy no longer treats every colony Zergling as an
automatic attacker. The bridge waits for completed Zerglings in a complete
native snapshot with publisher and controller bindings. At the first due
frame it records a wave containing the source Hatchery native ID, exact actor
IDs and generations, destination, desired count and request ID before sending
an assignment. A short group uses only available actors. The Zerg publisher
validates the living Hatchery, each actor and each actor's actual OpenBW path.
The existing native assault controller issues attack moves after acceptance.
The policy never submits a free `actor.spawn` wave.

The default first delay remains 7,200 native frames after finite economy
readiness, followed by a 2,880-frame interval unless the player changes the
setting. Difficulty changes the desired size of future groups only. Disabling
waves pauses new training, assignments and route retries while previously
ordered attackers continue. Re-enabling starts a fresh countdown. A dead
Spawning Pool blocks later training but leaves existing Eggs and Zerglings;
a dead Hatchery also blocks new assignments. Native route rejection receives
at most three journaled attempts. A missing receipt becomes uncertain and
is never replayed blindly.

The first native probe exposed a path-check mismatch: OpenBW reported
`unit_path=1` for an actual Zergling whose occupied starting position made
`hasUnitTypePath` return false. The final check uses that actual unit's native
`hasPath` result. B1's colony site query already proves a Zergling route from
the assembly tile to the Terran approach and a Marine return route. The final
native assignment also validates the Hatchery's current identity and life.

## Focused results

| Check | Command or evidence | Result |
| --- | --- | --- |
| Failing first regression | `go test ./internal/world ./cmd/world-bridge -run TestEnemyAssault` before implementation | Failed: missing B3 journal symbols. |
| Go journal, service, migration and B1/B2 neighbors | `GOCACHE=$PWD/build/go-cache-b3 /usr/local/go/bin/go test ./internal/world ./cmd/world-bridge -run 'TestEnemyAssault\|TestEnemyProduction\|TestGeneratedEnemyBase\|TestProducedZerglings' -count=1` | Pass. Includes short group, duplicate snapshot, retry and late receipt, death, Pool/Hatchery gates, toggle countdown, accepted-order reconnect and B2 journal migration. |
| Python and protocol | `python3 -m unittest tests.test_protocol_starcraft_types tests.test_enemy_base_map tests.test_existing_park_defense`; `python3 -m json.tool bridge-protocol/world.v1.schema.json`; `python3 -m py_compile tests/test_enemy_base_assault_native_live.py` | Pass, 10 Python tests and syntax checks. |
| JavaScript | `node --check openrct2-plugin/rts-bridge.js`; `node tests/test_world_plugin.js` | Pass. |
| Native C++ | `cmake --build build/bridge-module -j2`; `ctest --test-dir build/bridge-module --output-on-failure` | Pass, 3 C++ tests. |
| Generated scenario | `TMPDIR=/tmp/starcoaster-b3-tmp GOTMPDIR=/tmp/starcoaster-b3-tmp GOCACHE=$PWD/build/go-cache-b3 scripts/project.sh validate-scenario run-data/enemy-base-b3/assault-confirmed/prepared/scenario.json` | Pass; live geometry still requires the native probe. |
| Ordinary park native assault | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_enemy_base_assault_native_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --runtime run-data/enemy-base-b3/assault-confirmed` | Pass, all seven checks in `verification.json`. |
| Source and diff | Probe SHA-256, `git diff --check` | Source unchanged; no whitespace errors. |

The successful probe used a **test-only 1,200-frame first delay** in its
ignored generated scenario. The shipping generator still uses 7,200. Economy
readiness occurred at frame 912; wave `base-0001` journaled eight completed
actors at frame 2112; OpenBW accepted all eight at frame 2113. At frame 2136,
all eight received native attack moves toward `(4400, 3984)`. The journal
records Hatchery native ID 5 and eight distinct canonical actor/native ID
pairs. No free scenario spawn request or duplicate assignment appeared. The
source park SHA-256 remained
`84aeb880c2d5e2610d6a760eb13c087b3eefcd0683fc71aabe1b4e51cc585f44`.
The ignored `run-data/enemy-base-b3/assault-confirmed/` contains the map,
scenario, log, journal and JSON checks. Earlier failing route evidence is in
`run-data/enemy-base-b3/assault-probe/` and `route-debug/`.

The native probe confirms issuance of attack moves, not a graphical
playthrough, observed post-order park damage, or a generated-colony combat
kill. The deterministic service checks cover the destroyed Pool and Hatchery
gates; the existing combat destruction and ordered park revision path is
reused. No browser, Chromium, video, full `test-live` or deployment run was
performed.

## Manual B3 check

In the private Pi browser, choose **Bumbly Bazaar** from New Game. Note the
map ID and confirmed revision. Identify the Terran economy and Zerg colony;
watch Larva become Eggs and paired Zerglings. In Map > StarCraft Settings,
confirm the attack countdown, then watch an assigned group leave the colony
and fight at the park. Train Marines, counterattack the Pool and Hatchery,
and confirm no further training or new waves from the destroyed source while
already committed attackers remain consistent. Reload and rejoin with a
second client; check the same structure state, actor IDs and revision. Record
any unexpected behavior with the map, revision and native frame.
