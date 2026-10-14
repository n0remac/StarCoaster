---
name: starcoaster-park-design
description: Edit the deterministic playable parks while preserving footprints, spawns, collision geometry, and native navigation routes.
---

# Design a playable park

The current packaged parks share `scripts/park-assault-generator.js`. Regenerate with `scripts/project.sh park frontier-outpost` or `scripts/project.sh park example-defense`. The generator's current layout version is 4; keep the saved path ramps facing uphill. `docs/park-design-v0.2.md` defines wall edges: 0 west, 1 south, 2 east, 3 north. Plugin collision rectangles and `scripts/park_navigation.py` must agree with OpenRCT2's painted geometry.

Keep the objective and other structure footprints, scenario starting and wave spawn tiles, chokepoints, and intentional openings aligned with each package's `scenario.json` and native map. For Frontier, preserve the gate at `(28, 35)` unless the scenario and navigation checks are deliberately updated together.

Run `python3 -m unittest tests/test_frontier_park_geometry.py` and `scripts/project.sh test`. For wall or route changes, run `tests/test_frontier_native_navigation_live.sh`; for terrain or elevation, also use the ridge and 256×256 checks in `starcoaster-verify`. Use `scripts/project.sh record --scenario frontier-outpost --duration 24 --video-layout single --cycle-rotations` to inspect all four views. Record geometry counts, live route results, and visual limits. Do not commit saved parks or proprietary graphics.
