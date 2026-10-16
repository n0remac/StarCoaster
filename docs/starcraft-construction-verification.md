# StarCraft construction vertical slice

The first construction option is a Terran Barracks. The OpenRCT2 toolbar patch
adds one button beside ride construction and invokes the plugin's registered
menu item. The plugin owns the RCT2-style window, active placement tool,
passive building inspection, and construction status. The native park contains
an original, indexed-palette large-scenery object with twelve occupied tiles;
its generator is `scripts/install-starcraft-construction-object.py`.

The placement action is OpenRCT2's synchronized `largesceneryplace`, subject to
its terrain, clearance, ownership, and multiplayer permission checks. The
plugin also rejects unit occupancy from the latest native actor snapshot,
including unbound actors and a conservative 16-pixel edge margin. Placement
waits for the first native snapshot.
The server discovers the placed object as a `structure` with the stable
`terran_barracks` type, owner 1, 4×3 collision cells, and a park-storage-backed
generation. Its ordinary `world.patch` reaches both OpenBW participants before
the bridge confirms the new revision. The information window reads confirmed
target identity and current native HP from the synchronized target catalog.

## Verification

Native commands used `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR` pointing to the
local licensed installations. All listed `run-data/` artifacts are ignored.

| Check | Result | Evidence |
| --- | --- | --- |
| `scripts/build-openrct2.sh` | Passed | Native toolbar patch compiles; applying it twice reports `current` on the second pass. |
| `scripts/project.sh test` | Passed | Go and three C++ tests passed; 87 Python tests passed with one skipped; JavaScript plugin tests passed. |
| `node tests/test_barracks_plugin.js` | Passed | Menu, 12-tile preview, placement, path and actor obstruction, inspection, health refresh, and reload ID checks. |
| `tests/test_live_construction_scenery_path.sh` | Passed | `run-data/live-construction-scenery-path-1792187402/verification.json`. |
| `tests/test_live_construction_navigation.sh` | Passed | `run-data/live-construction-nav-1792188006/verification.json`; native movement rerouted around construction and reopened after removal. |
| `tests/test_live_construction_overlap.sh` | Passed | `run-data/live-construction-overlap-1792188045/verification.json`; occupied native geometry was rejected without teleporting the actor. |
| `tests/test_live_construction_recovery.sh` | Passed | `run-data/live-construction-recovery-1792188097/verification.json`; generic construction state, damage, and two-client catalog recovered across a bridge restart. |
| `python3 tests/test_marine_controls_live.py` | Passed | `run-data/marine-controls-live-1792188186/`; both commands reached native OpenBW in order and redirected a Marine within five seconds. |
| `scripts/project.sh record --scenario mt-zergling --duration 45 --no-video --video-layout combined` | Passed | `run-data/artifacts/20261016T215657Z-5a31624b43b3/verification.json`; 362 shared, matching two-client snapshots and no mismatches. |
| `scripts/project.sh record --scenario mt-zergling --duration 30 --no-video --video-layout single` | Passed | `run-data/artifacts/20261016T220736Z-033662cd80af/`; inspection shows native HP 40 and repeat clicking retains one information window. |

The combined Mt. Zergling capture includes `barracks-menu.png`,
`barracks-preview.png`, `barracks-built-a.png`, `barracks-synced-b.png`, and
`barracks-obstructed.png` in that ignored artifact directory. They show the
toolbar button, construction window, valid preview, completed structure on
both clients, and rejection over an occupied footprint. Its
`barracks-verification.json` confirms 4,076 changed building pixels on each
client and one addition. The final single-client capture includes
`barracks-info-first.png` and `barracks-info-repeat.png`, which show the
completed building's owner, identity, native HP, status, and disabled production
control with no duplicate window. The synchronized Barracks patch used navigation hash
`ee9230f1842ece7d` at native frame 837 on both OpenBW participants; the bridge
confirmed revision 2 with three targets. The first client B screenshot was
taken before patch confirmation; `barracks-synced-b.png` shows the confirmed
building.

## Current limits

- The first tool uses direction 0. OpenRCT2's scripting tile selection provides
  the 4×3 outline; the window text reports valid or invalid placement because
  the scripting API does not expose a highlight colour for that outline.
- OpenRCT2 large scenery requires a positive price, so placement currently
  deducts £1 of park cash. StarCraft mineral, gas, and supply costs remain out
  of scope.
- Actor occupancy is checked against the latest synchronized positions before
  the native placement action. A moving actor can still enter a site before
  OpenBW stages the resulting park revision. The native stage rejects occupied
  geometry; resolving that race across park and bridge transactions remains
  future work.
- The custom park object and generation data are designed for OpenRCT2 save
  files. The JavaScript restart test retains the same ID from saved park storage.
  A native save/load cycle with this Barracks and a bridge reconnection after
  construction were not exercised in this milestone; treat both as unsupported
  recovery paths for Barracks-specific state until native regression covers them.
- The OpenBW target proxy currently reports 40 HP for the completed Barracks.
  The information window displays that native value without a guessed maximum.
  The park structure is not a BWAPI production unit. To add training later,
  bind its stable park ID to a real `Terran_Barracks` under the Terran player,
  reconcile native creation and death with park revisions, and route training
  commands through BWAPI `Unit::train` and its queue. OpenBW's `action_train`
  requires an owned selected producer and calls `unit_can_build` before adding
  to its build queue; resource and supply policy also belongs to that later
  milestone.
