---
name: starcoaster-park-design
description: Edit the deterministic Frontier Outpost park while preserving wall continuity, ride footprints, spawns, collision masks, and native navigation routes.
---

# Design the Frontier park

Edit `scripts/park-assault-generator.js` and regenerate with `scripts/project.sh park`. Use the edge mapping in `docs/park-design-v0.2.md`: wall directions 0 west, 1 south, 2 east, 3 north. The plugin's wall rectangles and `scripts/park_navigation.py` must agree with native OpenRCT2 painting. Preserve the gate at `(28, 35)`, objective ride, shop and ride footprints, Marine and Zergling spawns, and intentional perimeter openings.

Run `python3 -m unittest tests/test_frontier_park_geometry.py` and `scripts/project.sh test`. For wall or route changes, run `tests/test_frontier_native_navigation_live.sh`; use `scripts/project.sh record --duration 24 --video-layout single --cycle-rotations` to inspect all four views. Record generated geometry counts, live navigation results, and any visual limitation. Do not commit saved parks or proprietary game graphics.
