# Generated Zerg colony rotation layout

The original generated layout placed the 4×3 Hatchery at `(x+1, y+1)` and the 3×2 Spawning Pool at `(x+5, y+2)` inside the selected 9×9 perimeter site. Their native footprints did not collide, but their painted OpenRCT2 sprites extended beyond those footprints. Rendering the installed object PNGs with their actual per-rotation origins showed overlapping nontransparent pixels in all four rotations: 3,165, 160, 26, and 843 pixels respectively. The original four-view montage is in ignored `run-data/enemy-base-b4/overlap-current.png`.

Layout policy 2 keeps the Hatchery at `(x+1, y+1)` and moves the Pool to `(x+1, y+7)`. The installed sprite masks now have **zero overlapping nontransparent pixels in all four rotations**. The four-view montage is in ignored `run-data/enemy-base-visual/overlap-pool-south.png`. The Pool remains on native Hatchery creep in the probed parks, and the assembly and approach tiles remain open. Generated package caches receive a new preset identity so an old layout is rebuilt. Existing policy-1 sessions remain valid; authored scenario layouts are unchanged.

## Focused verification

| Check | Result |
| --- | --- |
| `node tests/test_economy_layout_plugin.js` | Passed. The regression projects both sprite bounds in all four rotations; it failed on the previous layout. |
| `GOCACHE=$PWD/build/go-cache-visual /usr/local/go/bin/go test ./internal/world -run TestGeneratedEnemyBase -count=1` | Passed; policy 1 and 2 accepted, unknown policy rejected. |
| `python3 -m unittest -q tests.test_existing_park_defense tests.test_single_map_cache tests.test_enemy_base_map` | Passed, 20 tests. |
| `scripts/project.sh validate-scenario run-data/enemy-base-visual/{bumbly-final,extreme-final}/prepared/scenario.json` | Both generated packages passed configuration validation. |
| Focused native bootstrap, Bumbly Bazaar and Extreme Heights | Both passed 8/8 checks. OpenBW publisher and controller accepted the Hatchery, Pool and supply; the bridge bound both structures; no free wave spawned. Source parks remained unchanged. Evidence: `run-data/enemy-base-visual/{bumbly-final,extreme-final}/verification.json`. |
| Synthetic blocked-site native bootstrap | Passed 5/5 checks: explicit blocked status, no colony targets, and no free waves. The source park remained unchanged. Evidence: `run-data/enemy-base-visual/blocked-final-fixed/verification.json`. |

The montage uses the installed sprite images and their projection offsets, and the native probes are headless. An actual OpenRCT2 four-rotation screenshot remains a manual graphical check. In the normal New Game flow, select Bumbly Bazaar and Extreme Heights, center the colony, rotate through all four views, and confirm the Pool silhouette stays separate from the Hatchery while both structures remain selectable. The first selection should rebuild the generated cache under layout policy 2.
