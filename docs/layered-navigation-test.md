# Layered ground navigation test park

The focused park is generated under ignored `run-data/layered-navigation/` from
a generated Frontier Outpost save. No park or licensed object data is committed.
With locally installed RCT2 and StarCraft data and built engines:

```sh
scripts/project.sh park frontier-outpost
python3 scripts/create-layered-navigation-park.py
RCT2_DATA_DIR=/path/to/RCT2 STARCRAFT_DATA_DIR=/path/to/StarCraft tests/test_height_navigation_live.sh
```

The generator uses real OpenRCT2 `ridecreate`, `trackplace`, and `footpathplace`
actions to add a high straight rail over the Marine start, low straight rail,
station, vertical loop, and two paths at different heights on one tile. It
inserts one deliberately low overhead footpath as a fixture because normal
construction clearance rejects that overlapping configuration. The source
element export is `source-elements.json`; it includes Z, track sequence,
quadrants, slopes, and action parameters. The test driver adds overhead track
and path through synchronized construction actions while OpenBW moves a Marine
and a Zergling. It then replaces a low rail at the same X/Y position at a
higher Z and checks that the ground cells reopen.

Each live run writes `verification.json`, `server.log`, both client logs,
`navigation/confirmed-revision-1.json`, candidate revision traces, and three SVG
overlays under `run-data/layered-nav-live-*/`. The traces contain the committed
terrain and entities, exact packed native mask, and cell-level obstruction
causes recorded by the same `DeriveNavigation()` projection. The SVGs show the
coaster and footpath regions at 8-pixel native resolution. Test assertions
check clear high track and layered path cells, blocked low track, station,
loop, and low overhead path cells, cause labels, actor positions, movement
progression, synchronized patch revisions, unchanged-mask application for the
overhead edits, and a changed mask for the rail height edit.

The inherited Frontier terrain supplies supported slopes, cliffs, and ground
walls. The generator also adds an isolated water tile and elevated wall; the
native mask check expects water to block and the raised wall to clear the
ground. The test driver previews a wall through a real OpenRCT2 ghost action
and checks that no corresponding committed entity or native obstruction appears.
The Marine route starts under elevated
track; the Zergling starts beneath the raised path and then moves under native
control. A further route matrix through each isolated feature would strengthen
the evidence.
