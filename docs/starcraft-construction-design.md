# StarCraft construction: source findings and implementation plan

Baseline: `1dc8526` (pinned OpenRCT2 and OpenBW checkouts).

## Findings

- The pinned scripting `Ui` exposes `openWindow`, `activateTool`, tile selection,
  and ordinary menu items, but no toolbar button registration. The upper-right
  buttons are a fixed widget enum, widget array, and order in
  `openrct2-ui/windows/TopToolbar.cpp`. A dedicated button needs a small native
  patch that calls a plugin callback. The scenery, path, and ride buttons already
  use this window/tool convention.
- `rts-bridge.js` already uses `activateTool` for Marine spawning and a separate
  passive viewport interaction for Marine selection and right-click orders. A
  Barracks tool can share tile highlighting if it owns the active tool; building
  inspection should be passive and consume only hits on Barracks. Alt-click
  must continue to reach park objects.
- The plugin discovers saved park tile elements. Ordinary large scenery is
  grouped by object index, anchor, elevation, and rotation, then sent as an
  entity with occupied cells and collision volumes. The bridge stages each
  `world.patch` against the confirmed revision; both OpenBW participants apply
  its navigation and target changes at the same frame before confirmation.
- OpenRCT2 park storage is serialized in park saves, but park storage alone does
  not provide a visible, collidable tile element. A dedicated 4×3 large scenery
  object is the smallest saved, multiplayer native representation. A separate
  bridge-owned object would need new persistence, rendering, demolition, and
  synchronization paths. A BWAPI Barracks today would add another authority for
  footprint and lifetime; native production is a later step after binding a
  stable park structure ID to an OpenBW unit and extending spawn/production
  reconciliation.
- The map transform is one OpenRCT2 tile to one StarCraft build tile, with a
  constant OpenBW tile offset. A 4×3 park footprint therefore maps to 4×3 native
  build tiles. OpenRCT2's large-scenery placement action checks native park
  clearance and ownership; a preflight must additionally check live unit
  occupancy. Its action query remains authoritative at click time.

## Vertical slice

1. Add a narrowly scoped native toolbar callback and dedicated button next to
   ride construction. Keep the window and tool in the plugin.
2. Package an original Barracks large-scenery object with 12 occupied tiles and
   a distinct identifier. Stage it with both OpenRCT2 clients and the server.
3. Query the native placement action while hovering, highlight the 4×3 area,
   reject known unit occupancy, and execute the same action on click. Recognize
   the object in discovery as a `terran_barracks` structure. The existing patch
   and navigation path then handles confirmed additions and removals.
4. Inspect Barracks through passive viewport hits and display a read-only
   information window with identity, owner, health, and a disabled production
   tab. Exercise offline checks, live construction checks, and two-client video.

## Boundaries

The first slice uses OpenRCT2 scenery as the park representation, not a BWAPI
production unit. OpenBW still owns navigation and combat against its bridge
target proxy. Health shown by the UI must come from confirmed bridge/native
state, not a guessed local timer. Save/load persistence follows the native tile
element and custom object; identity across a fresh process session needs an
explicit generation strategy because existing discovered IDs use session-local
generation counters. That recovery path must be verified before it is claimed.
