# Frontier Outpost park design — v0.2

The deterministic 64 × 64 playable layout now has a carousel plaza, shared food court, Marine staging garden, Ferris wheel walk, and connected outer route. The central defense wall still has its destructible gate at tile `(28, 35)`; the west and south perimeter entrances remain open. The rides, shops, six Marine spawns, twelve Zergling spawns, and objective footprint retain their scenario coordinates.

OpenRCT2 paints wall direction 0 on a tile's west edge, 1 on its south edge, 2 on its east edge, and 3 on its north edge. The generator, generic plugin collision rectangles, and Python navigation grid now share those edge definitions. `scripts/frontier_geometry.py` checks duplicate or floating edges, corner connections, the gate, path connectivity, and ride footprint overlap. The same edge graph is checked under all four camera rotations.

The generated playable park contains 214 wall segments, 350 connected path tiles, 15 ride track tiles, and 45 small scenery elements. `tests/test_frontier_native_navigation_live.sh` passed all six observed OpenBW movement checks after regeneration, including crossing the removed gate at x=896 and walking through the demolished carousel footprint. Its logs and position samples are in `run-data/frontier-native-nav-1791847495/`.

The legacy 48 × 48 park assault fixture remains a separate regression. Its six southern Zergling starting points moved north of the corrected south wall collision strip; all 20 routes and demolition fixture tests pass.

The graphical run `run-data/artifacts/20261012T233122Z-01c58848c6db/` contains screenshots at all four OpenRCT2 camera rotations for both clients. Visual inspection found continuous perimeter fence lines, joined barrier corners, and the intentional entrance and gate openings in each view. The same run records a two-client combat video and matching state snapshots.
