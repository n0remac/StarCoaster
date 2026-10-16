# Navigation completeness and visual verification

## Phase 0: painter and graphical baseline

The baseline is height-aware navigation commit `41d65bb`; the pinned
OpenRCT2 checkout is `33aacdeb0d9e22c1622acf071e6698f946365453` with the
project's native bridge patch applied. The ground collision and Z conventions
remain those in [height-aware-navigation-contract.md](height-aware-navigation-contract.md).

### Painting audit

`PaintSessionGenerateRotate()` calls `TileElementPaintSetup()`,
`EntityPaintSetup()`, and `PaintBridgeActors()` in each relevant tile pass.
`PaintBridgeActors()` sets the actor's interpolated world X/Y as
`session.SpritePosition`, samples `TileElementHeight()` at those exact
coordinates for ground Z, and registers the GRP image with
`PaintAddImageAsParent()`. `PaintAddImageAsParent()` puts the actor in a paint
quadrant. `PaintSessionArrange()` then sorts parent entries by rotated
bounding boxes, including the actor, walls, track, and scenery. Insertion
after tile elements is therefore not itself a guarantee that an actor is
painted in front of them. Its bounding box and the structure's paint bounds
decide the result. The health bar is an actor child entry, so it follows the
actor's parent order.

The bridge's common actor bound is `[-6,-6,z+5]` with size `12×12×18`.
For comparison, OpenRCT2's guest bound is `1×1×11` at `z+5`. Local StarCraft
walk frames are up to 26 pixels wide for Marines and 38 for Zerglings;
those image extents are larger than the bridge's physical paint bound.
This is a plausible source of edge occlusion differences, but it is not yet
evidence that the bound is wrong. In particular, a wider paint bound can
sort an actor against a wall at a different physical position. Keep the
current bound until a close graphical overlap shows a failure.

`BridgeApplySnapshot()` interpolates an actor between its previous displayed
position and the next native position when the change is at most 64 X/Y
pixels and the previous blend is recent. It adds the actor to every tile
bucket crossed by the two endpoints and invalidates old and new visual
positions. A jump above that threshold snaps to the native location. This
is the local target if a tile-boundary pop is observed; native OpenBW
positions remain the movement evidence. Direction is projected through the
viewport rotation before choosing a GRP frame. The terrain Z comes from
OpenRCT2's slope interpolation, not from a raised path.

The pinned Corkscrew coaster painter uses a three-Z-unit paint body above
`height` for a flat rail and a station-specific base for station track.
The track descriptor's clearance is construction space and cannot be used
as a painted or physical body. Wall painting also supplies its own edge
bounds. These source observations support separate collision and visual
checks; a matching navigation mask alone cannot establish paint order.

### Exploratory capture and classification

The initial Frontier graphical capture used the default wide camera. Its
two clients synchronized and recorded valid video, but the actors and wall
occupied too few pixels to judge depth. The layered-park capture then used
the test-only `--navigation-baseline` recorder option and close, stable
camera rotations 0 and 1. A first close attempt reused a probe whose wall
blocked its own commanded corridor; it did not establish a front/behind
crossing. The dedicated baseline probe now discovers its Marine ID at
runtime, places a wall through an ordinary action, and issues native Marine
commands around both sides. In the long exploratory run, the native Marine
reached all five waypoints, both clients shared 383 identical snapshot
sequences, and the wall patch synchronized at revision 2. The video was
valid H.264, 1600×500, about 70 seconds. The original generic verifier
rejected the empty wave state of this test-only version-1 scenario; it now
accepts that valid state without changing its identity or snapshot checks.

That run also exposed a capture-order problem: the native route completed
while the second graphical client was joining, before FFmpeg started. The
test-only probe now waits for a recorder-triggered OpenRCT2 shortcut. The
short capture records the trigger 68 milliseconds after the video clock
starts, then starts construction and movement. At `client-a-t14.png` the
Marine is partly hidden by the wall; the alternate rotation in
`client-b-t14.png` shows it in front. It reappears in `client-a-t18.png`.
Those are inspected paint-order frames, not inferred from navigation logs.
The elevated straight track and Marine share source X/Y at the start, and
the native route crosses its tile. The rail and Marine are visible in both
rotations, but these samples do not establish an overlapping rail/sprite
paint boundary, so that interaction is **navigation-only** for now. No
missing sprite, terrain-Z jump, or snapshot discontinuity was apparent in
the inspected frames; the short baseline cannot exclude those defects in
other scenes. There is no evidence yet that changing paint insertion or
bounding volume would improve the result.

The clean triggered smoke artifact is
`run-data/artifacts/20261016T000838Z-74b68a326139/`. Its `run.json` lists
the verified `combined.mp4` and 24 screenshots. `ffprobe` measured H.264 at
1600×500, 416 frames, 12.0 fps, and 34.667 seconds. The two clients shared
matching actor snapshots. A regular wall action synchronized at revision
2, hash `5518593e25d6b2fd`; both native participants reported that hash at
the same frame. The discovered Marine `openbw:1000` accepted and crossed
the five ordered native waypoints after video capture began. The baseline
route checker passes 8/8 checks; its separate `visual-verification.json`
records the manually reviewed wall and navigation-only rail classes.
Inspection used the actual screenshots
`client-a-t2.png`, `client-a-t6.png`, `client-a-t10.png`, `client-a-t14.png`,
their client-B counterparts, and the extracted contact sheet from the
long exploratory run. Source fixtures are a generated copy of the layered
park plus test-only camera and movement probes; no licensed save is checked
into Git.

| Interaction | Native result | Visual result | Phase 0 finding |
| --- | --- | --- | --- |
| One-tile wall, both sides | Passed in the triggered route | Supported in two rotations | A foreground overlap and reappearance are visible. |
| Elevated straight rail | Source tile traversed | Navigation-only | Inspect close underpass frames and paint order. |
| Tile-boundary movement | Continuous sampled route | No visible pop in selected frames | Repeat during required final scenes. |
| Two camera rotations | Two graphical clients | Both views captured | Verify close occlusion in each rotation. |

Phase 1 should use source-backed collision classes and keep these rendering
results separate. Phase 2 must put the foreground wall directly across a
controlled projected actor path. Phase 3 must inspect before/during/after
frames before changing the renderer.

## Phase 1: collision classification audit

The exporter retains one logical ride entity and complete combat footprint.
These rows describe **physical ground collision approximations**, not track
construction clearance. `tests/test_navigation_geometry_plugin.js` exercises
plugin discovery; `TestSlopedRailStripsMeetGroundClearanceBoundary` and the
height-aware Go tests exercise the authoritative mask projection. Existing
fixtures cover walls, scenery, raised paths, terrain slopes, ghosts, and Z
boundaries. The new fixture includes a type-zero shop track that must remain
blocked.

| Source type / sequence / direction | Physical classification | Evidence | Precision and limitation |
| --- | --- | --- | --- |
| Corkscrew flat track 0 / 0 / 0 | Rail `[baseZ,baseZ+8)` with rotated quarters | Pinned Corkscrew flat painter and prior live straight crossing | Approximate; supports unrepresented. |
| Corkscrew flat left/right 5-tile curve 16/17 / 0–6 / all directions | Rail `[baseZ,baseZ+8)` with exported quarters | `TrackData.cpp` sequences and Corkscrew curve painter place rail sprites at `height` | Approximate; sequence-specific rail silhouette and supports unrepresented. |
| Corkscrew flat left/right 3-tile curve 42/43 / 0–3 / all directions | Same rail interval and quarters | Three-tile Corkscrew painter and sequence descriptor | Approximate; supports unrepresented. |
| Corkscrew up/down 25-degree straight 4/10 / 0 / all directions | Four 8-pixel strips; local 4-Z rise plus 8-Z rail thickness | Descriptor `zBegin/zEnd` differ by 16; pinned painter draws a sloped rail sprite; `CoordsDirectionDelta` fixes strip order | Approximate; rail profile within each strip and supports unrepresented. |
| Station 1–3 / any / any | Full occupied tile from ground to at least `baseZ+32` | Station painter has base and platform; existing station fixture | Conservative for an elevated station and its supports. |
| Shop/facility track / any / any | Full occupied tile from ground to construction top | Shop/facility painters draw substantial 28-pixel building bodies and foundations; fixture includes type zero | Conservative body/support footprint; object-specific façade unresolved. |
| Ride entrance/exit / any / any | Full occupied tile from ground to construction top | Pinned `Paint.Entrance.cpp` draws 28×28 front and support; exporter previously omitted the collider | Conservative body/support footprint. |
| Directional wall / any / direction 0–3 | Existing 4-pixel edge with vertical interval | Pinned wall painter and plugin fixture | Approximate edge; fence openings unknown. |
| Raised footpath / flat or supported slope / any | Existing walking-surface slab and terrain-relative check | Pinned footpath semantics and height-aware Go tests | Approximate slab; supports and underside unknown. |
| Small/large scenery / object-specific | Existing solid/support fallback and object footprint | Scripting object flags and height-aware fixture | Approximate or conservative; precise branches and support posts unknown. |
| Other coaster styles and complex pieces, including one-tile curves and loops | Ground-to-clearance fallback | No verified physical body in the selected painter | Conservative; may block a genuine underpass. |

The new curve and slope classes are restricted to ride type 19 (Corkscrew
Roller Coaster), whose pinned painter was inspected. Type-zero flat track
keeps its previous behavior for other rides; stalls and facilities are
explicitly excluded from that rail rule. Other coaster styles await painter
verification. No exact support-pillar geometry is claimed. The Phase 1
fixture verifies high and low curves, mixed blocked/clear slope strips at the
32-Z boundary, solid buildings and entrances, unknown fallback, ghost
exclusion, and one combat identity for the ride. Phase 2 must confirm curve
and slope behavior with real construction and actual native movement.
