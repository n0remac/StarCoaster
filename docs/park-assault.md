# Park assault: Frontier Outpost

`park-assault` is a live, two-client demonstration of one OpenBW simulation fighting through an OpenRCT2 park. Twenty preplaced Zerglings move in three squads (8/6/6), attack three preplaced hostile Barracks proxies with normal OpenBW weapons, and trigger native OpenRCT2 demolition of the matching carousel, burger bar, and Ferris wheel. The Barracks do not attack ground units; their 1000 HP gives every Zergling time to participate. The existing patrol, ride siege, and Frontier Defense scenarios remain separate.

## Build and run

The Pi needs the existing OpenRCT2 build, OpenBW/BWAPI build, RCT2 data, and locally licensed StarCraft data described in [bootstrap](bootstrap.md). The commands below run from the repository root:

```sh
python3 scripts/create-park-assault.py --probe-demolition
python3 scripts/create-park-assault-map.py
python3 scripts/export-park-assault-navigation.py
python3 scripts/verify-park-assault-headless.py --reuse-fixtures
python3 scripts/capture-live-demo.py --scenario park-assault \
  --verify-destruction --record-video --video-layout combined
```

`verify-park-assault-headless.py` without `--reuse-fixtures` regenerates all fixtures first. The park generator saves `run-data/park-assault/save/frontier-outpost.park`; its isolated probe loads a separate copy and verifies that `ridedemolish` removes each target's original ride and track. The OpenBW map generator writes a UMS `.scm` with exactly 20 Zerglings and three structure proxies. The capture command starts one OpenBW process, one OpenRCT2 multiplayer server, and two graphical OpenRCT2 clients, then stores a unique run under `run-data/artifacts/`.

## Park and navigation data

Frontier Outpost develops 48 × 48 tiles of the existing flat park map. Real OpenRCT2 footpaths form a loop and intersections; perimeter fencing has west and south entrances. Internal walls force detours through a maze and narrow gaps. Twenty trees, flowers, and shrubs provide scenery. The carousel, food stall, and Ferris wheel occupy distinct regions and begin closed and empty. The generator discovers loaded ride objects through the OpenRCT2 object manager, records actual ride IDs, types, object identifiers, and occupied track tiles, and validates their construction. Ride IDs in the current saved fixture happen to be 100, 101, and 102; the bridge reads them from the generated configuration.

The OpenRCT2 generator exports its actual tile elements and surface elevations to `navigation-elements.json`. `park_navigation.py` rasterizes those elements into 8 × 8 world-pixel cells, with elevation, source identity, classification, cost, and walkability. Wall edges become blocked strips, trees block their scenery footprint, and track tiles block ride footprints. Flowers remain traversable. A 24-pixel planning clearance includes the Zergling radius and a steering margin. Multi-goal A* routes to exterior attack cells, and smoothing accepts a segment only when every sampled cell has clearance. The exported JSON is inspectable; the compact `navigation.grid` feeds the C++ BWAPI planner and records its target count rather than assuming three targets. The scenario transform is recorded once in `fixture.json` (`OpenBW → OpenRCT2: x−128, y−96`) and used by both engines.

OpenBW still owns movement and collision. The park planner supplies short `Unit::move` waypoints and replans when progress stalls; normal BWAPI attack orders begin at safe exterior positions. The verifier checks observed OpenBW positions and each sampled segment against the exported park geometry. Waypoint steering is therefore a measured constraint in this fixture, not native OpenBW collision with arbitrary OpenRCT2 scenery. The terrain is flat; elevation is exported for future use but is not used for multi-level routing. The shop squad also uses a scenario gateway to avoid an unreliable crowded approach to its wall opening.

## Combat, demolition, and revisions

The version 3 `scenario.snapshot` includes session, sequence, map ID, map revision, OpenBW tick, up to 32 actor slots, and independent target identities and HP. The OpenRCT2 server checks identity, bounds, session, sequence, HP transitions, and ride identity before applying snapshots. OpenBW remains the sole health and weapon authority. When a proxy reaches zero HP, the OpenRCT2 host calls native `ridedemolish` once, verifies the original ride and track are gone without changing unrelated scenery or other targets, and records failure explicitly if the action fails. Only a confirmed demolition sends a revisioned `nav` update back to OpenBW over the existing loopback socket. The planner clears that ride's footprint and replans against the new revision. Both graphical clients receive the native park change through OpenRCT2 multiplayer; the host alone runs OpenBW.

The v1 patrol and v2 ride siege snapshot paths remain supported. The new scenario configuration is generated from the park and map manifests by `prepare-park-assault-plugin.py`, so normal runs do not edit source constants.

## Verification and artifacts

The headless verifier checks all twenty distinct Zergling IDs, accepted move and attack orders, real attack frames and HP loss on each proxy, three OpenBW deaths, exactly three native demolitions, ordered navigation revisions, packet size, and observed path clearance. The graphical capture adds agreement on native actor snapshots across the server and two clients, each client's independent ride/track removal, unchanged surviving scenery, and absence of multiplayer desynchronization logs. Failed runs retain diagnostics and are labeled failed.

Each graphical run publishes a combined MP4, staged screenshots, `verification.json`, `scenario-config.json`, filtered OpenBW/OpenRCT2 logs, navigation grid and planned/observed path visualizations, path JSON, per-target combat events, revision events, and any collision violations. These appear in the [private Pi artifact viewer](test-viewer.md). The renderer uses the existing native OpenRCT2 actor action and scenery depth ordering; animation, facing, movement, and attack state come from OpenBW snapshots.

Run the local checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/test_park_assault_plugin.js
node tests/test_plugin_snapshots.js
node tests/test_ride_siege_plugin.js
node tests/test_combat_plugin.js
/usr/local/go/bin/go test ./...
python3 scripts/verify-ride-siege-headless.py
```

The plugin tests include malformed and duplicate packets, stale sessions and sequences, HP regression, mismatched map revisions, invalid target sets, and failed or repeated demolition. The map and navigation tests check real construction data, target separation and attack anchors, wall detours, clearance, and revisioned footprint clearing.

## Measured Pi result

Run [`20261011T210917Z-ec2c8198ca29`](https://raspberrypi.tail628049.ts.net:8443/runs/20261011T210917Z-ec2c8198ca29) passed on 2026-10-11. Its validated combined MP4, 18 staged screenshots, nine navigation/combat diagnostics, scenario configuration, verification JSON, and filtered logs are in `run-data/artifacts/20261011T210917Z-ec2c8198ca29/` and on the private viewer. The run recorded 20 accepted attack orders, 748 genuine attack frames, 557 target HP decreases, three native demolitions, and navigation revisions 2, 3, and 4. The server and both graphical clients agreed on 229 complete 20-actor snapshots; each had zero sequence gaps and no desynchronization report. Both clients independently saw carousel track count 9→0, shop 1→0, and Ferris wheel 4→0 while the 547 surviving scenery/path/wall elements kept the same signature.

The observed-path verifier checked 4,160 position samples and their connecting segments with zero prohibited crossings. The largest sampled live packet was 3,804 bytes against a 32,768-byte limit; the slowest recorded route plan took 2.76 ms. OpenBW ran at a measured lower bound of 21.77 frames/s from process launch to the last target death, including startup time. Snapshot application showed zero dropped sequence numbers on all three OpenRCT2 peers. The final recording shows the intact overview, approaching squads, close views of walls and attacks, the three native disappearances, and the cleared park. The viewer was tested through its local listener and private Tailscale HTTPS address.

Regressions passed during implementation: 39 Python unit tests, the park assault and existing snapshot/ride siege/combat Node tests, all Go viewer tests, the original eight-Zergling headless and two-client live ride siege, and the original two-client patrol (102 common snapshots, zero state mismatches). The final park assault headless gate also passed with all three real OpenBW kills, three native demolitions, and no observed obstacle crossings.
