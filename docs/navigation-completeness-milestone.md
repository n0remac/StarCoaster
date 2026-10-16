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
