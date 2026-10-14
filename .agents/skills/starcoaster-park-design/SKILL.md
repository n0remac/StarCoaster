---
name: starcoaster-park-design
description: Edit the deterministic playable parks while preserving footprints, spawns, collision geometry, and native navigation routes.
---

# Design a playable park

The two legacy parks use `scripts/park-assault-generator.js` in compatibility modes. New parks use a package-local `park-layout.json` with `"generator": "layout-v1"`; `scenarios/midway-junction/` is the example. The same OpenRCT2 generator prepares the source park, creates and validates rides, exports actual geometry, and saves the park. Do not copy its code for a new mission. `scripts/park_layout.py` validates the data-only layout before OpenRCT2 starts.

## Layout-v1 format

The top-level JSON fields are exactly `version: 1`, `name`, `size: [64,64]`, `rides`, `paths`, `walls`, `scenery`, and `large_scenery`. All coordinates are park tiles in the inclusive buildable area 8–55. Flat terrain is the only supported terrain mode. Each ride has `id`, unique `name`, supported `object`, and placement origin `x`,`y`. Supported ride objects are the stock Ferris wheel (`fwh1`), carousel (`mgr1`), burger bar (`burgb`), and drink stand (`drnks`). The validator supplies track type, expected footprint, and existing native proxy metadata. Generation fails if OpenRCT2 rejects placement or the exported footprint differs.

Path primitives are `{ "kind": "horizontal", "y": Y, "x0": A, "x1": B }`, `{ "kind": "vertical", "x": X, "y0": A, "y1": B }`, and `{ "kind": "plaza", "x0": A, "y0": B, "x1": C, "y1": D }`; endpoints are inclusive. Each wall entry has `x0`,`y0`,`x1`,`y1`,`direction`,`object` and represents one tile edge or a straight continuous run. Wall edge directions are 0 west, 1 south, 2 east, 3 north. Supported stock wall IDs are `rct2.scenery_wall.wpf`, `wbr1`, and destructible `wbr2`. A small or large scenery entry has `x`,`y`,`object`; the allowed stock IDs are in `scripts/park_layout.py`. Small scenery cannot overlap an authored path or wall tile. Large scenery is placed through the normal OpenRCT2 action.

Create `scenarios/ID/park-layout.json`, point its package metadata at it, and set outputs to `run-data/ID/save/ID.park`, `run-data/ID/fixture.json`, and `run-data/ID/navigation-elements.json`. Run `scripts/project.sh validate-scenario ID`, `scripts/project.sh play ID --plan`, `scripts/project.sh park ID`, and `scripts/project.sh test`. A layout change invalidates all three generated outputs. `tests/fixtures/fourth-layout.json` is a separate test-only layout that generates without generator changes.

Footpaths alone do not constrain OpenBW. Use real wall edges, rides, and blocking scenery to define routes. Check the generated export and native movement, not just the JSON. Keep objective footprints, spawn tiles, chokepoints, and intended openings aligned with the scenario. For Frontier, preserve the gate at `(28, 35)` unless its tests are updated together. The legacy generator's layout version is 4; its path ramps face uphill. Plugin collision rectangles and `scripts/park_navigation.py` must agree with OpenRCT2's painted geometry.

Run `python3 -m unittest tests/test_midway_park_geometry.py tests/test_frontier_park_geometry.py` and `scripts/project.sh test`. For Midway wall changes, run `NAV_SCENARIO=midway-junction tests/test_frontier_native_navigation_live.sh`; for Frontier use its default. For terrain or elevation, also use the ridge and 256×256 checks in `starcoaster-verify`. Capture changed parks with `scripts/project.sh record --scenario ID --duration 120`, inspect screenshots and footage, and keep saved parks and captures out of Git.
