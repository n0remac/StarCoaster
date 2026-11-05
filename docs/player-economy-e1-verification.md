# Player economy E1 verification

Status: E1 exit evidence complete on the authored fixture. Branch: `economy-e1`,
implementation commit `9219b0a` based on E0 commit `662308b`. Date: 2026-11-05.
This report covers the fixed authored
fixture only. E2 worker controls, E3 player construction transactions, and E4
ordinary-park placement are outside E1.

## Implemented boundary

`scenarios/economy-e1` declares one visible Command Center, four SCVs, six
1,500-mineral fields, one 5,000-gas geyser, and a finite 50/0 starting balance.
The native CHK has no hidden Depot. The explicit `economy.mode=finite` path
rejects legacy unlimited grants and uses the Command Center's native supply and
train-SCV production. Authored scenarios without the finite mode retain their
previous defaults.

The one-file declaration generator now emits neutral resources and SCV worker
capabilities and visual states. The original 1,355 sprite paths retain their
order and hash `21887e075201da8a6fb41b113d713d20a6a6beae2949e2f42bdbb65f419ddbbe`;
116 E1 paths follow them. OpenBW reports resource amount, lifecycle, native ID,
owner, worker order/cargo/target, and construction progress. The Go bridge
publishes a resource site only after publisher and controller observations agree.
The native adapter adopts the exact observed Command Center at the authored
site; it does not create a free duplicate. OpenRCT2 renders the real neutral
resource HP of 100,000 after a bounded compatibility change.

Resource site IDs are authored labels. Runtime bindings use exact-site BWAPI
observations and generation numbers, never CHK record IDs or nearest-unit
guesses. Go regression cases cover a Refinery retaining the geyser native ID,
then a restored geyser receiving a new ID and generation. No E1 test calls the
E0-crashing `removeUnit` path.

## Commands and results

The Pi had about 5.2 GiB available RAM and 677 GiB free on the USB checkout
before heavy work; swap was already effectively full. Builds used two jobs at
most. All generated/license-bearing inputs, captures, profiles, and logs below
are ignored under `build/` or `run-data/`.

| Check | Exact command | Result |
| --- | --- | --- |
| Generator | `python3 scripts/generate-starcraft-types.py --check` | Pass |
| Focused Python | `python3 -m unittest tests.test_player_economy_e1 tests.test_player_economy_e0_map -v` | Pass |
| Declaration/ledger | `python3 -m unittest tests.test_starcraft_entity_declarations -q` and `python3 -m unittest tests.test_sprite_order -q` | Pass |
| Focused Go | `GOCACHE="$PWD/build/go-cache-e1" /usr/local/go/bin/go test ./internal/world -run 'TestFiniteBaseProjection|TestFiniteEconomy|TestResourceBindings' -count=1` | Pass |
| Fixture | `scripts/project.sh validate-scenario economy-e1`, `scripts/project.sh park economy-e1` | Pass |
| Visual staging | `python3 scripts/install-starcraft-construction-object.py build/openrct2-stage/usr/local/share/openrct2 --game-dir /home/pi/games/starcraft --all`; `python3 scripts/verify-starcraft-visuals.py --record` | Pass; the licensed sprites and park objects remain ignored. |
| Native engines | `CCACHE_DIR=/home/pi/.cache/ccache CCACHE_READONLY=1 CCACHE_TEMPDIR="$PWD/run-data/economy-e1/ccache" BRIDGE_BUILD_JOBS=2 scripts/build-openrct2.sh`; `BRIDGE_BUILD_JOBS=2 scripts/build-bridge-module.sh`; `GOCACHE="$PWD/build/go-cache-e1" /usr/local/go/bin/go build -o build/world-bridge ./cmd/world-bridge` | Pass |
| Full offline | `TMPDIR=/tmp/economy-e1-tmp GOCACHE="$PWD/build/go-cache-e1" GOFLAGS=-p=2 scripts/project.sh test` | Pass on final source: Go packages, 3 CTest cases, 218 Python cases (1 skipped), plugin checks; `run-data/economy-e1/offline-final.log`. An earlier run failed because newly declared construction objects had not yet been installed; staging them resolved it. |
| Native graphical/restart | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft bash tests/test_player_economy_e1_native_live.sh` | Pass; evidence below. Initial attempts exposed the native 100,000-HP validator mismatch and two test-harness restart races; retained in ignored run directories. |
| WASM build | `OPENRCT2_WASM_LOCAL=1 BRIDGE_BUILD_JOBS=2 TMPDIR="$PWD/build/tmp-e1-wasm" CCACHE_TEMPDIR="$PWD/run-data/economy-e1/ccache" scripts/build-openrct2-wasm.sh` | Pass; bundle `build/wasm-client/`. |
| WASM broad suite | `TMPDIR=/tmp/economy-e1-tmp GOCACHE="$PWD/build/go-cache-e1" WASM_PRIVATE_RCT2=1 WASM_RCT2_DIR=/home/pi/games/rct2 WASM_TEST_PORT=46397 WASM_SERVER_READY_TIMEOUT_MS=240000 WASM_TEST_PROFILE="$PWD/run-data/economy-e1/wasm-test-profile" scripts/project.sh test-wasm` | Pass on repackaged final bundle: socket gateway, bundle, persisted private assets, graphical canvas, main menu, New Game interaction, incompatible-version and missing-assets errors. Earlier attempts timed out on server inventory or main-menu indexing; `run-data/economy-e1/test-wasm*.log` preserves them. |
| Browser economy | `WASM_E1_WASM_PORT=46397 WASM_E1_PROFILE="$PWD/run-data/economy-e1/wasm-test-profile" RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft bash tests/test_player_economy_e1_browser_live.sh` | Pass: graphical starting economy, native SCV debit/binding, and a fresh browser reload with five workers and no reissued train order. |

The broad WASM suite is a browser launcher test without a game host. Its
first-use private origin did provision 2,465 licensed RCT2 files (about
680 MiB) and persisted them in IndexedDB. The first attempt timed out before
the server finished inventorying licensed files; the second reached a canvas
and object index but its main-menu wait expired while scenario files were
still scanning (11/57 in `build/wasm-browser-test/main-menu.png`). After
making the server-ready timeout configurable and reusing the warmed private
origin, the final suite passed; `run-data/economy-e1/test-wasm-final.log`
and `build/wasm-browser-test/runtime.json` are the evidence. This suite does
not establish gameplay; the separate browser economy probe connects to an
isolated native host.

## Native graphical evidence

Passing run: `run-data/player-economy-e1-1793911797/` (ignored). The native
client screenshot `native-client.png` visibly shows the Command Center, SCVs,
six minerals and geyser. `session.log`, `client.log`, and
`restarted-bridge.log` preserve the commands and observations.

At native frame 552, player 1 held 50 minerals, 0 gas and 8/20 half-supply.
The Command Center train-SCV command was accepted at frame 1185 with native
balance 0/0 and 10/20 half-supply; frame 1200 confirmed the same balance. One
worker appeared as canonical `openbw:3001`, generation 1, with observed BWAPI
native ID 225 bound on both participants at frame 1189. The initial SCVs were
canonical IDs 2506–2509. The six minerals bound to actual native IDs 4–9 at
amount 1500, and the geyser to native ID 10 at amount 5000, generation 1.
The authored `scenario:base` Command Center adopted native `openbw:11`
at its exact configured center; no second base was created.

The bridge restarted while OpenBW and OpenRCT2 continued. The park requested
a second snapshot for the same session and revision 1. The first player
balance after restart (frame 1992) remained 0/0 and 10/20, and all seven
resource sites were republished with the same IDs and quantities at frame
2016. No second `openbw:3001` spawn occurred. Initial navigation mask hash
`b57efe9dc0ce67d9` applied at publisher/controller frames 528/530; reconnect
applied the same hash at 1985/1987.

## Browser graphical evidence

Passing run: `run-data/player-economy-e1-browser-1793917308/` (ignored).
`browser/final.png` and `browser/economy-reconnect.png` both visibly show the
base, six mineral fields, geyser and five SCVs in the park. The browser
first observed the four starting SCVs, then its 212-target late-join catalog
arrived and one train-SCV request was accepted. Its native host accepted that
order at frame 14802, charged 50 minerals and raised supply from 8/20 to
10/20 by frame 14808, and bound canonical `openbw:3001` to observed native
ID 225 at frame 14806. On page reload, a new OpenRCT2 instance rebuilt its
object index, rejoined the same native session, and freshly observed five
workers. The test-only probe switched to observe-only mode for the reload:
the log contains one accepted train order total and no train-order attempt
after reload. The native balance and worker count stayed at the charged
values. `browser/runtime.json`, `browser.log`, and `session.log` preserve the
evidence.

An earlier browser run `run-data/player-economy-e1-browser-1793914403/`
rendered and trained the worker, but its Playwright reload wait expired after
30 seconds; the next probe captured a loading screen before the new client
had joined. Those runs are retained as failed harness evidence. A later
retry `run-data/player-economy-e1-browser-1793914994/` failed during
Chromium worker startup before gameplay. The passing run uses a new-page
worker observation and a visible reconnect screenshot, so those failures
are not counted as E1 gameplay passes.

## E1 exit criteria

| Criterion | Result |
| --- | --- |
| One-file neutral/worker declarations and appended visuals | Met; generator and sprite-order regressions pass. |
| Finite authored economy without hidden supply or refills | Met; CHK/Go checks and native 50/0, 8/20 observation pass. |
| Native and WASM/browser graphical starting economy | Met; both captures show the base, workers, six minerals and geyser. |
| Trained SCV native cost, supply and identity | Met; both live runs show 50→0 minerals, 8/20→10/20 half-supply, one `openbw:3001` bound to native ID 225. |
| Browser reconnect and bridge restart without bootstrap replay | Met; new browser client rendered five workers with no train reissue, and restarted Go bridge retained balance/sites/session. |
| Worker/resource/construction observation contract | Met for E1 state transport and initial native observations; live Refinery replacement and player construction remain later integration checks. |

## Remaining boundary

The E0 two-frame participant offset for applying an unchanged navigation mask
persists in the E1 fixture, even though both accept the same hash. Initial
target resolution reported nine `proxy_not_created` wall targets; seven
resolved after restart, leaving two wall targets near the starting economy.
The authored Command Center and seven resource identities were unaffected.
This does not prove frame ordering of a future incomplete-building park
projection; E3 must test that against the confirmed revision/frame contract.
E0's `removeUnit` call on an active Refinery crashed a native participant;
its tested `killUnit` path restored a neutral geyser. E1 did not invoke the
crashing operation or live-test a new Refinery morph through the bridge; its
generation-qualified replacement handling is regression-tested, while E2
still needs a live lifecycle check before player gas controls use it.

E1 does not give players gather/build commands, a resource amount UI, or the
native worker-construction transaction. E2 can use the worker/resource
observations and Command Center training path. E3 must close free-building
routes and prove ordered native construction projection. E4 can consume the
typed finite configuration and exact-site binding contract to choose valid
ordinary-park layouts; E1 leaves those defaults unchanged.

## Ignored local inputs and artifacts

The fixture source `run-data/economy-e1/source/Frontier Outpost.park` is local
licensed park input; its generated save and native map are
`run-data/economy-e1/save/economy-e1.park` and
`run-data/economy-e1/economy-e1.scm`. The StarCraft sprite pack and inventory
are in `run-data/generated-assets/starcraft/`; staged engines and WASM bundle
are in `build/openrct2-stage/`, `build/bridge-module/`, and
`build/wasm-client/`. The browser profile is
`run-data/economy-e1/wasm-test-profile/`. Passing live evidence is in
`run-data/player-economy-e1-1793911797/` and
`run-data/player-economy-e1-browser-1793917308/`. None of these paths is
committed. Recreating the fixture on another machine requires its own
licensed local RCT2 and StarCraft data.
