# Height-aware ground navigation contract

This contract describes the bridge's ground-only projection. OpenRCT2 owns tile
geometry, the Go bridge derives the packed 8-pixel mask, and OpenBW owns 2D
movement. `geometry.rects` remains the complete logical combat footprint.

## Coordinates and collision profile

- X/Y are OpenRCT2 world pixels: one tile is 32 pixels. Rectangles are
  axis-aligned half-open `[x,x+width) × [y,y+height)`. The centered native-map
  offset applies once to X/Y, never to Z.
- Every bridge Z is an OpenRCT2 world Z (`baseZ`/`clearanceZ`), with 8 units
  per tile-element `baseHeight` step. Vertical intervals are half-open.
- The one Marine/Zergling profile uses an 8-pixel native walk cell and 32 Z
  units of clearance above its local ground. This is OpenRCT2's
  `kPathClearance = 4 * kCoordsZStep` (8 each), also used by guest wall
  validation in `Guest.cpp`. It is a shared passage calibration, not an
  inferred OpenBW sprite height. Boundary fixture: a slab beginning exactly
  at ground+32 clears; beginning at ground+31 obstructs.
- A walk cell uses the minimum and maximum supported terrain corner heights
  over its footprint, with conservative intersection of the unit interval
  `[ground_min, ground_max+32)`. Native steep/diagonal land shapes retain the
  existing conservative cliff rule; unsupported encodings fail validation.
  Water and incompatible terrain edges stay blocked.
- Horizontal contact at a rectangle boundary is nonoverlap. A volume's
  occupied quadrants use the **already rotated** low four bits exported by
  `TileElement.occupiedQuadrants`; they are not rotated a second time. In the
  source `QuarterTile::Rotate`, quarter bits rotate with direction; the
  physical quadrants are SW=1, NW=2, NE=4, SE=8. Each covers a 16×16 part
  of its source tile. Zero occupancy is invalid for a physical volume.

## Physical space and fallback

`baseZ` and `clearanceZ` describe a tile element's construction interval, not
necessarily a solid object. `MapCanConstructWithClearAt` intersects those
intervals and occupied quarters, then makes track, path, terrain, and crossing
exceptions. `landSlopeFitsUnderTrack` reads the track descriptor's rotated
quarter-clearance heights. These checks validate construction, not Marine
collision. `FootpathPlaceAction` reserves `kPathClearance` above its walking
surface. `GuestPathfinding` uses the path clearance; neither makes that air
space a physical slab.

Collision modes are `legacy` (missing mode also means legacy footprint),
`height_aware` (only supplied physical volumes), and `conservative` (documented
fallback volume or footprint). An explicitly empty height-aware list asserts
no represented ground obstruction. Missing, malformed, or unclassified
geometry must fail validation or use `conservative`; it must never silently
become empty. `blocks:false` disables entity collision, including path entity
collision. Paths have one projection from terrain layers instead.

Supported physical classes are ground station tiles (full tile), wall edges
(the established 4-pixel edge), low simple track (tile/quadrant approximation),
and scenery with a supported solid footprint. Elevated simple track uses its
base Z as the lowest known rail and permits passage below it. OpenRCT2 does
not export reliable support-pillar positions through the scripting tile
elements, so the rail can be confirmed overhead while support collisions
remain unknown. Elevated footpath slabs use the walking surface as their
lowest represented solid height; exact underside thickness and supports are
unknown. Vertical loops, complex track, unfamiliar scenery, and missing
metadata use a conservative footprint until object-specific evidence supports
a narrower collider. Never substitute construction `clearanceZ` for physical
solidity merely because the field is present.

Diagnostics distinguish `unknown_track_shape`, `unknown_scenery_shape`,
`missing_physical_geometry`, `unsupported_slope`, and
`unrepresented_supports`. They describe approximation provenance; malformed
data is rejected. Fixtures must cover exact Z boundaries, slope under an
overhead slab, rotated quarter occupancy, layered paths, ghost omission,
centered transforms, equivalent volume order, and same-X/Y Z edits.

Source references in the pinned checkout: `world/ConstructionClearance.cpp`
(`MapCanConstructWithClearAt`, `landSlopeFitsUnderTrack`,
`landSlopeFitsUnderPath`), `world/QuarterTile.cpp`, `world/Map.cpp`
(`TileElementInsert`), `world/Footpath.cpp`, `peep/GuestPathfinding.cpp`,
`actions/footpath/FootpathPlaceAction.cpp`, `entity/Guest.cpp`,
`ride/ted/TrackElementDescriptor.h`, tile-element headers, and
`distribution/scripting/openrct2.d.ts`.
