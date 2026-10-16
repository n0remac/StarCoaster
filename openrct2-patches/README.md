# OpenRCT2 native patch

`0001-native-bridge.patch` applies to the pinned OpenRCT2 commit in `dependencies.lock.json`. `scripts/build-openrct2.sh` applies it and stages generated sprites. The patch contains source and sprite metadata only; it does not contain StarCraft art or a compiled `g2.dat`.

`0005-starcraft-construction-toolbar.patch` adds the dedicated StarCraft button
beside ride construction. It invokes the plugin's registered construction menu
item and remains hidden when that item is unavailable. The Barracks scenery
object is generated locally by `scripts/install-starcraft-construction-object.py`.

The fork paints Marine and Zergling actors in the world paint pass, including walking, attacks, deaths, and health bars. An immutable snapshot registry preserves safe access during rendering; old and new regions are invalidated for movement. The fork exposes snapshot, hit testing, cursor location, and actor inspection bindings to the plugin. It also adds `onRightClick` to the existing custom map tool, since OpenRCT2 intentionally does not route right mouse clicks through shortcuts. The plugin distributes state through synchronized game actions and sends player orders to the Terran BWAPI endpoint.

Marine selection uses `ui.registerViewportInteraction`, a passive handler for the
main viewport. A callback must return `true` to consume hover, left release, or
right click; otherwise native OpenRCT2 interaction continues. Active tools take
priority. The handler and its callbacks are released when the owning plugin stops.
Actor screen projections include zoom scale and exclude actors hidden by viewport
settings. The plugin uses compact screen footprints rather than a world-radius
search for unit selection. Alt bypasses unit input for overlapping park entities.

`0004-shared-viewport-input-upgrade.patch` upgrades existing patched checkouts;
`0001-native-bridge.patch` includes the same changes for clean checkouts. The
patch reconciler verifies the final native code and preserves unrelated local edits.

The native compatibility version is 4 and the asset version is 3. Older bridge clients are rejected by the plugin. Local art is installed with `BRIDGE_SPRITE_SOURCE=starcraft-local`; the public `alien-scout` build uses original open art and a CC0 Marine placeholder.
