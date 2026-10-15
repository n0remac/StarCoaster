# Height-aware ground navigation

The bridge now projects OpenRCT2 vertical construction onto OpenBW's existing
8-pixel ground walk grid. The [geometry contract](height-aware-navigation-contract.md)
defines units, intervals, quadrants, the shared 32-Z Marine/Zergling clearance,
and fallback rules. OpenBW still performs 2D movement and combat. OpenRCT2
still owns construction and tile geometry. One logical entity remains per ride;
its complete `geometry.rects` continues to identify the combat target while
`collision.volumes` controls ground obstruction.

## Supported geometry

| Source | Ground projection |
| --- | --- |
| Legacy entity without `collision.mode` | Original full 2D rectangle mask |
| Flat track | Per-tile rail approximation `[baseZ, baseZ+8)` |
| Station track (types 1–3) | Per-tile station approximation `[baseZ, baseZ+32)` |
| Vertical loop and other complex track | Conservative per-segment volume from local terrain base through its construction height |
| Wall | Existing 4-pixel directional edge, checked against its physical Z interval |
| Small scenery with `hasNoSupports`; large scenery tile with `hasSupports=false` | Approximate occupied tile/quadrants from base Z upward |
| Other scenery | Conservative per-tile support fallback from terrain base upward |
| Flat or sloped raised footpath | Approximate 8-Z slab at its walking surface; no upper route is created |
| Ground or subsurface footpath | Ground remains walkable; subsurface layer is metadata |
| Terrain | Existing supported slope connectivity, cliff barriers, water blocking, and map padding |

Construction clearance is never taken as a full solid collider for supported
track, paths, and walls. Exact coaster support positions, footpath undersides,
object meshes, and complex track solids are not available from the pinned
scripting tile elements. High flat track and raised paths can therefore clear
the ground while their unrepresented supports remain an explicit limitation.
Unknown track and scenery geometry remains conservative. Ghost tile elements
are absent from snapshots and construction patches.

The additive `world.v1` fields are `collision.mode`, `collision.volumes`, and
terrain `path_layers`. Missing collision mode retains legacy behavior. An
explicitly empty `height_aware` list means no represented obstruction. Bad
volumes fail validation. Legacy `ground_paths` remains supported; a tile using
both path fields fails as conflicting input. The plugin sorts and deduplicates
volumes and path layers so equivalent park discoveries produce stable patches
and mask hashes. `world.patch` still stages the full candidate and waits for
both native participants to apply at the same frame. Overhead edits that leave
the mask unchanged use the existing revision-only native path.

Snapshot chunks and patches retain the 1 MiB wire limit. The plugin measures
serialized entity and chunk sizes and explicitly reports `entity_too_large`
or `snapshot_chunk_too_large` before sending an impossible snapshot. It falls
back from an oversized patch to a snapshot when individual entities still fit.
The bridge also rejects an oversized transformed entity before forwarding a
native snapshot. No compression or streaming protocol was added.

## Reproducible test park and evidence

`python3 scripts/create-layered-navigation-park.py` generates an ignored copy
of Frontier Outpost at `run-data/layered-navigation/layered-navigation.park`.
The committed generator uses real OpenRCT2 actions for a high coaster rail,
low rail, station, vertical loop, ground path, and raised path. It adds an
isolated water tile and raised wall and inserts one deliberately low overhead
path tile as fixtures. Ordinary construction clearance rejects the low path
configuration. The original Frontier park is not
modified. `tests/test_height_navigation_live.sh` launches two OpenBW
participants and two OpenRCT2 clients, orders a Marine from beneath the high
track, observes a Zergling moving from beneath the raised path, and places
additional high track and footpath sections through real client actions. The
driver then removes and replaces a low straight rail at the same X/Y tile but
at a higher Z, preserving its ride identity.

With `BRIDGE_NAV_DIAGNOSTICS_DIR` set by the test, the bridge writes the exact
committed mask, source entities, Z volumes, terrain layers, and per-cell
blocking causes under ignored `run-data/`. The renderer creates SVG overlays
for track and footpath regions. The expanded focused run at
`run-data/layered-nav-live-1792100868/` passed all 22 checks in
`verification.json`: high track, raised path, and raised wall cells were clear;
low track, station, vertical loop, low path, and water cells were blocked for
their recorded causes. The Marine reached its ordered destination; 148 position
samples also show the Zergling leaving its raised-path starting tile. Two real
overhead actions became synchronized revisions 2 and 3 at frames 393 and 501 with
identical native hash `841939c51f4bc26d`; both participants reported
`unchanged=1`. See `source-elements.json`, `navigation/*.json`,
`initial-ground-mask.svg`, and `after-overhead-edits.svg` there. A later run at
`run-data/layered-nav-live-1792103663/` passed all 26 checks, including the
same-X/Y height edit: the low rail's tile reopened, the ride ID stayed stable,
and both native participants applied revision 4 at frame 665 with new hash
`c882c2fb325024ad`. Its `after-height-change.svg` shows the reopened cells.
The final run at `run-data/layered-nav-live-1792105312/` passed all 28 checks.
A real OpenRCT2 ghost wall was visible in the source tile but absent from the
authoritative entity snapshot and native mask. Marine and Zergling movement,
both unchanged-mask overhead revisions, and the changed-mask height revision
also passed.

## Measurements and limits

The same run exported 295 collision volumes initially. Initial discovery took
373 ms; construction discoveries took 137 and 166 ms. The largest initial
entity was 2,877 serialized bytes and the largest snapshot chunk was 28,630
bytes. The two patch payloads were 3,315 and 876 bytes. Their Go navigation
derivations took 3.978 and 3.934 ms. Native unchanged-mask application took
0.113–0.169 ms; initial mask application took 16.302 ms in the publisher and
16.214 ms in the controller. End-to-end patch synchronization took 4,271 and
4,302 ms. The previous [live construction baseline](live-construction-milestone.md)
reported 3.338–3.538 ms derivation, 16–23 ms native rebuild, and 4,346–4,435
ms synchronization. These are individual runs with different park geometry;
they do not establish a statistically significant regression. Full-mask
derivation remains in use.

In the later height-change run, the 3,599-byte patch took 3.662 ms to derive;
the publisher and controller rebuilt their native masks in 22.618 and 24.981
ms, and synchronization took 4,361 ms. The initial entity and snapshot chunk
maxima in that run were 3,138 and 29,807 bytes.

Exact UTF-8 payload sizing initially raised one layered-park discovery from
373 to 1,293 ms. An ASCII fast path reduced two subsequent discoveries to
628 and 635 ms while retaining the Unicode byte-count test. In a
`run-data/layered-nav-live-1792103865/` run, construction discoveries took
137–172 ms; patch payloads were 3,599, 876, and 3,599 bytes. The three
navigation derivations took 5.187, 3.664, and 4.151 ms. Revision 4 rebuilt
native masks in 23.104 and 23.598 ms and synchronized in 4,364 ms.
The final ghost-preview run measured 621 ms initial discovery, 295 volumes,
3,138 bytes for its largest entity, and 29,807 bytes for its largest snapshot
chunk. Construction discoveries took 140–149 ms. Its three patch payloads were
3,599, 876, and 3,599 bytes; navigation derivations took 3.680, 4.362, and
3.855 ms. The changed revision rebuilt native masks in 23.184 and 23.470 ms
and synchronized in 4,320 ms. Both overhead revisions used the unchanged-mask
path.

Initial `source` tags classify those volumes as 217 wall edges, 48 scenery
support fallbacks, 2 scenery elements flagged without supports, 25 complex
track fallbacks, 2 straight rails, and 1 station. These are approximation
counts, not failed synchronizations. The trace keeps their source IDs and
Z intervals beside the final blocked-cell causes.

The native overlap safeguard checks active unit center cells, not complete
unit footprints. Adjacent construction and the existing overlap rejection
remain covered by the live-construction tests; a general native collision
rewrite is outside this milestone. Same-session native recovery retains the
current mask until the bridge stages the authoritative new mask, so logical
overhead ride footprints cannot cause a provisional overlap rejection.

The optional locally authored `Mt. Zergling.park` was absent during this run.
Exact support pillars, unusual scenery meshes, and upper-level unit routes
remain follow-up work.

## Regression commands

| Command | Result | Evidence |
| --- | --- | --- |
| `scripts/project.sh test` | Passed: Go, C++, Python, and plugin checks. | `run-data/height-aware-offline-complete.log` |
| `tests/test_height_navigation_live.sh` | Passed 28/28 mask, source, ghost, native movement, height-change, and synchronization checks. | `run-data/layered-nav-live-1792105312/verification.json` |
| `scripts/project.sh test-live-construction` | Passed the complete sequential construction suite, including overlap, unchanged masks, target HP, restart, interruption, and death recovery. | `run-data/height-aware-test-live-construction-phase6.log` |
| `scripts/project.sh test-live` | Passed on the second aggregate, including graphical startup, scenario runtime, and all nested construction cases. | `run-data/height-aware-test-live-rerun.log` |
| `NAV_SCENARIO=midway-junction tests/test_frontier_native_navigation_live.sh` | Passed native detour, gate demolition, and reopened route checks. | `run-data/midway-junction-native-nav-1792103746/verification.json` |
| `python3 tests/test_midway_scenario_live.py --mode defeat` | Passed two-client defeat outcome. | `run-data/midway-live-defeat-1792103917/` |
| `python3 tests/test_midway_scenario_live.py --mode victory` | Ended in native defeat, matching the documented intermittent tactical outcome. | `run-data/midway-live-victory-1792104002/bridge-restart.log` |

An earlier construction aggregate failed only because the new
`payload_bytes` metric changed two test log parsers; both were corrected and
the focused batch plus complete aggregate then passed. Other abandoned
attempts collided with already running live tests on the shared ports, so
their `WORLD_READY` timeouts provide no regression evidence. The prior
intermittent Frontier scenario outcome and Midway victory timing are described
in the [live construction baseline](live-construction-milestone.md); any
aggregate failure will be classified against those records. The first full
native aggregate stopped at graphical startup: the server was ready and the
opening wave spawned, but the client did not reach its first actor snapshot
before the test timeout. The focused graphical rerun and second full aggregate
both passed with 37 and 39 client snapshots respectively. This was an
intermittent client-startup failure; it is not a confirmed navigation
regression.
One post-optimization focused attempt synchronized the geometry but its
single Marine command did not receive an action callback. The probe now
retries the request until acceptance; the later focused rerun passed all 28
checks. This was a test command delivery race, not a confirmed
mask regression.

The first attempt at the new rail height-change probe did not start client A:
OpenRCT2 reported `zstdDecompress` data corruption during its map download.
The immediate rerun passed all 26 checks, so the failed attempt provides no
navigation result and remains unclassified as an engine/network startup event.
