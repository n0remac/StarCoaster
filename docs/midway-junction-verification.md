# Midway Junction verification

Midway Junction uses the shared `world.v1` bridge, OpenBW movement and combat, and OpenRCT2 park authority. Its separately authored 64 × 64 layout is in `scenarios/midway-junction/park-layout.json`. Generated parks, native maps, recordings, and licensed data stay outside Git under ignored `run-data/`.

## Reproduce

```sh
export RCT2_DATA_DIR=/path/to/your/rct2
export STARCRAFT_DATA_DIR=/path/to/your/starcraft
scripts/project.sh validate-scenario midway-junction
scripts/project.sh play midway-junction --plan
scripts/project.sh park midway-junction
scripts/project.sh test
STARCOASTER_REGENERATE_GEOMETRY=1 python3 -m unittest tests.test_midway_park_geometry
NAV_SCENARIO=midway-junction tests/test_frontier_native_navigation_live.sh
python3 tests/test_midway_scenario_live.py --mode victory
python3 tests/test_midway_scenario_live.py --mode defeat
scripts/project.sh play midway-junction
scripts/project.sh record --scenario midway-junction --duration 120
```

The package resolver validates the layout without game data. `park` requires a built OpenRCT2 and licensed RCT2 data; the live commands also require a built OpenBW and licensed StarCraft data. `scripts/project.sh test-live` exercises the existing native and Frontier regression suite; the focused Midway commands above cover its own gate and outcomes.

## Observed results (2026-10-14)

The package validation and launch plan passed. Park generation produced `run-data/midway-junction/save/midway-junction.park`, `fixture.json`, and `navigation-elements.json`. The standard `play midway-junction` command reached `WORLD_READY` with native navigation and then a no-command defeat; it was stopped after 45 seconds because `play` is an interactive session. The offline suite passed 75 Python tests with one intentional regeneration skip, all three C++ tests, Go tests, and plugin validation. Explicit regeneration passed four Midway geometry tests. Frontier Outpost and Example Defense were each revalidated and regenerated; their package and Frontier geometry tests passed. A test-only fourth layout at `tests/fixtures/fourth-layout.json` generated through the same layout generator without changing its implementation.

The Midway native gate run is in `run-data/midway-junction-native-nav-1792000592/`. Its verifier passed all six checks: a pre-demolition detour, confirmed OpenRCT2 removal of the gate panel, native navigation updates on both sides, a direct crossing after demolition, accepted normal Marine orders, and completed sequence. The native navigation mask changed from `a124377b15f36945` to `1d1483dc5391de05`. Measured post-demolition Marine crossings included the gate area near y=981; some Marines still chose the southern route near y=1449. The exported-grid comparison shortens the designated route from 121 to 49 cells when the gate panel is removed.

The defended live run is in `run-data/midway-live-victory-1792001881/`. All three waves spawned from their configured east, north, and south zones, with counts 4, 3, and 5. Native snapshots from both clients show at least one attacker from each wave moving at least 192 world units from its spawn and reaching the Ferris wheel's vicinity. The verifier found unique native actor identities, no duplicate wave requests, accepted spawn, move, hold, and attack orders, a moving reinforcement, wave clearance, two-client victory agreement, a client reconnect, and a bridge restart. All checks passed. The independent no-command run in `run-data/midway-live-defeat-1792000733/` passed two-client initialization and confirmed Ferris wheel destruction and defeat through native combat during the opening assault.

The two-client recording is `run-data/artifacts/20261014T180415Z-5b318af0ef99/combined.mp4`, with initial and final screenshots beside it. `verification.json` reports native readiness, 589 matching post-join snapshot sequences, zero mismatches, synchronized defeat, valid screenshots, and complete capture. Viewed frames show the Ferris wheel, carousel, shops, landscaped staging area, connected paths and wall dividers, units aligned with park tiles, and Zerglings moving and fighting around the wheel. No layering or client disagreement was apparent. In this unattended defeat recording, surviving Zerglings continue attacking other scenery and rides after the wheel falls; the server log records confirmed removals and both clients show them. The recording does not show manual reinforcement, the gate shortcut, or a defended victory; those behaviors were checked in the focused live runs.

The full `scripts/project.sh test-live` run passed its Frontier ridge and gate checks, 256 × 256 native map, two-client demolition, actor lifecycle and restart, Marine and Zergling spawning, and playable launcher. It exited 1 in its final Frontier scenario runtime test because client B rejected the transferred map with an OpenRCT2 decompression error (`run-data/scenario-runtime-live-1792001630/`). A focused retry transferred the map and passed its initial actors, opening and timed waves, manual order, and bridge restart checks, but the Frontier objective fell before the expected final-wave ready assertion (`run-data/scenario-runtime-live-1792001785/`). Earlier local Frontier runtime artifacts include passing victory runs; this attempt does not establish a new geometry regression, but the full live suite is **not green** for this milestone. The two failures and their logs remain available for follow-up.

## Limits

Layout-v1 supports flat 64 × 64 parks and a small set of stock objects, path shapes, and straight wall runs. Rides are visual and combat structures without operating ride entrances. The standard recording captures unattended gameplay; it does not drive player decisions. The Midway gate probe and outcome tests use ordinary gameplay actions through the existing client controls and native combat.
