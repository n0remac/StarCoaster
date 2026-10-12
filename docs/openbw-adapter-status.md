# OpenBW adapter status and measurements

> Historical measurement: the capacity run below predates the native
> navigation patches now shipped in `openbw-bwapi-module/`. Frontier Outpost
> currently reports `navigation=native` after OpenBW and the Terran controller
> apply the park mask. See [first playable verification](first-playable-verification.md)
> for observed movement and the remaining route failures.

Measured on 2026-10-12 against `frontier-outpost.park` and the reusable `world-base-v4.scm`. This is an implementation report, not a declaration that the proposed milestone is complete.

## What runs now

The generic `world.v1` snapshot stages and validates a desired world before reconciliation. The OpenBW adapter keeps living, explicitly associated native target proxies across same-session snapshots, retires obsolete ones, and reports unsupported mappings. A second BWAPI player adapter applies Marine orders on a simulation frame. Preplaced Marines and Zerglings use common actor IDs across the two BWAPI processes. The bridge waits for controller target-link acknowledgments before publishing `world.ready`; it correlates Marine results, damage, park demolition confirmation, and obstacle-removal acknowledgments. Combat snapshots carry up to 256 actors and report total and omitted counts.

The target link between the two BWAPI processes includes logical entity ID, publisher proxy ID, and proxy location. The Terran controller accepts a target only when exactly one enemy civilian matches the link and no other linked target is nearby. This is a guarded compatibility mechanism, not a durable native cross-process unit identifier. Crowded or ambiguous placements are rejected.

At the time of these capacity measurements, `WorldNavigation.h` stored
footprints without applying them to OpenBW. The current adapter submits the
combined 8-pixel mask to the patched native VF4 collision and region builder
at startup and after confirmed demolition. `world.ready.navigation` reports
`native` only after both OpenBW processes acknowledge the mask.

## Capacity and performance

The park snapshot contained 4,426 entities, 65,536 terrain cells, and 3,006 objects eligible for a native combat proxy under the generic rules. The table uses the same Marines-only fixture so combat did not retire targets during initialization. Times are elapsed from Go listener startup to its `OpenBW ready` log line on this host; they include park scanning, snapshot transfer, and proxy creation. RSS is one post-ready process sample, not a peak measurement.

| Configured target attempts | Native targets created | Native placements rejected | Other eligible targets excluded by configured limit | Startup to ready | Publisher / controller RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 113 | 15 | 2,878 | about 29 s | not sampled |
| 256 | 156 | 100 | 2,750 | 33 s | about 101 / 39 MiB |
| 512 (default) | 197 | 315 | 2,494 | 52 s | about 101 / 39 MiB |

These observations show that native civilian placement, proximity ambiguity, and the built-in proxy footprint constrain useful coverage before the configured attempt limit. They do not establish the OpenBW engine's absolute unit-slot maximum. The maximum practical target count for arbitrary parks and the cost of a lightweight custom target remain unmeasured. The adapter reports successes, failed placements, and excluded counts rather than promising complete coverage.

The separate `100-separated-v4.scm` fixture preplaces 50 Marines and 50 Zerglings away from each other. With the example assault controller paused, both headless OpenRCT2 clients reported `WORLD_UNIT_COUNT 100`. This establishes snapshot transport and native-renderer input capacity for 100 mixed actors; it does not measure sustained 100-unit combat frame rate. The transient actor protocol is capped at 256 in this implementation and reports omitted actors if that limit is exceeded.

Local evidence: `run-data/world-adapter-test/session-cap256.log`, `session-cap512.log`, `session-100-separated.log`, and corresponding client logs. The repeatable native integration test passed three times; its latest logs are in `run-data/world-live-1791806662/`. `run-data` is intentionally ignored by Git.

## Acceptance check

| Criterion | Status | Evidence or remaining work |
| --- | --- | --- |
| Saved park initializes through the generic bridge | Passed | `frontier-outpost.park` discovered 4,426 entities without park-specific export. |
| Stable entity-to-simulation mappings | Partial | Explicit logical IDs and retained proxies; cross-process target association still relies on unique spawn location. |
| Repeated resynchronization does not duplicate proxies | Passed for one live bridge restart | 113 targets before and after restart; existing associations retained, two previously unsupported placements succeeded. More repeated-run coverage is needed. |
| Removed entities retire their representations | Passed for tested rides and scenery | Confirmed OpenRCT2 removal leads to native proxy retirement. |
| Rebuilt objects get new logical identities | Passed in world-model tests | OpenRCT2 generation registry differentiates location reuse; arbitrary live rebuild is deferred. |
| Bridge restart reconstructs a consistent registry | Passed for one live restart | Same OpenRCT2 session resnapshotted at revision 2 and OpenBW returned to `world.ready`. |
| Multiple park object types can be attacked and destroyed | Passed for tested ride and scenery | Existing Zergling runs and Marines-only ride 1 run. Exhaustive park-object coverage is limited by native placement. |
| Native OpenBW damage and targeting remain authoritative | Passed for tested proxies | Marine attack on ride 1 yielded native proxy death at frame 2399, then confirmed OpenRCT2 removal. |
| Marine commands in generic world mode | Passed for move and attack | Live client move changed the publisher's Marine position; logical ride attack was accepted by the Terran controller. Hold, stop, and attack-move have protocol checks but no live test yet. |
| Zergling AI without scenario target IDs | Passed | Example controller selects from the generic target registry. It remains embedded in the adapter and can be disabled for tests. |
| Attack and death animations | Partial | Snapshot publishes native attack state and brief death state; full renderer asset and animation validation remains. |
| Destruction removes intended OpenRCT2 object exactly once | Passed for tested ride | Ride 1 death produced one confirmed native removal; two clients agreed on resulting ride set. |
| Carousel and scenery full-footprint avoidance | Historical failure; now passed for the tested carousel | `tests/test_frontier_native_navigation_live.sh` observed Marines avoid the intact carousel and traverse its footprint after confirmed demolition. |
| Walls, narrow gaps, and blocked corridors route correctly | Historical failure; now passed for the tested Frontier routes | The live native navigation probe observed a legitimate opening, rejected a blocked corridor, and observed six Marines crossing the newly opened wall tile. |
| Confirmed destruction unblocks native routes | Historical failure; now passed for the tested wall and carousel | Both OpenBW processes applied removal at the same acknowledged frame; see `run-data/frontier-native-nav-1791834732/verification.json`. |
| Navigation capability reports enforced behavior | Passed | Frontier Outpost reports `navigation=native` only after both OpenBW processes acknowledge the mask. `metadata_only` is retained only as a historical fallback state for generic sessions that cannot apply a mask. |
| At least 100 mixed units through snapshots | Passed | Both clients received 100 on separated-army fixture. |
| Unsupported targets are reported | Passed | `world.ready` reports total and reason counts plus bounded example IDs. |
| Server and two clients agree on unit states and demolition | Partial | Two clients received the 100-unit snapshot and matching post-demolition ride sets; complete long-running equality comparison was not rerun. |
| Park-assault, ride-siege, and Marine-defense regressions | Partial | JavaScript/Python regression suites passed; live graphical scenario runs were not repeated for this change. |

## Required work for milestone completion

The `0002-native-navigation-openbw.patch` and
`0003-native-navigation-bwapi.patch` add dynamic VF4 masks and path region
rebuilding. The historical failures in the table above are superseded by the
live probe results. Those results cover the Frontier fixture and do not prove
every terrain, scenery, and height combination in arbitrary parks.

Combat still uses a Terran Civilian's native hitbox. A multi-tile ride has one health pool and one demolition identity but can be attacked only through that small proxy. Path objects remain non-targetable. Target placement limits, cross-process target identity, and client click-to-target geometry need stronger solutions. Live construction remains explicitly unsupported. The graphical two-client Frontier Outpost demonstration is available in the [first playable verification report](first-playable-verification.md) and the Pi artifact viewer.

## Reproduce checks

```bash
/usr/local/go/bin/go test ./...
ctest --test-dir build/bridge-module --output-on-failure
for test_file in tests/test_*plugin.js; do node "$test_file"; done
node tests/test_plugin_snapshots.js
python3 -m unittest discover -s tests -p 'test_*.py'
# Requires local licensed game data:
RCT2_DATA_DIR=/path/to/rct2 STARCRAFT_DATA_DIR=/path/to/starcraft \
  tests/test_world_live.sh
```

For a repeatable 100-unit transport fixture, generate the separated base map and start the normal world session with the example assault AI paused:

```bash
python3 scripts/create-world-base-map.py --output run-data/world-base/100-separated-v4.scm \
  --zerglings 50 --marines 50 --separate-armies
RCT2_DATA_DIR=/path/to/rct2 STARCRAFT_DATA_DIR=/path/to/starcraft \
  BRIDGE_MAP_FILE="$PWD/run-data/world-base/100-separated-v4.scm" \
  BRIDGE_DISABLE_ASSAULT_AI=1 scripts/run-world-session.sh /path/to/park.park
```

The `scripts/world-command-probe.js`, `scripts/world-target-probe.js`, and `scripts/world-unit-count-probe.js` files are local client fixtures. The target probe intentionally references one known ride ID in the regression park; the production adapter does not depend on that ID.
