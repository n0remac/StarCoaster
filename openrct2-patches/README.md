# OpenRCT2 native patch

`0001-native-bridge.patch` applies to the pinned OpenRCT2 commit in `dependencies.lock.json`. `scripts/build-openrct2.sh` applies it and stages generated sprites. The patch contains source and sprite metadata only; it does not contain StarCraft art or a compiled `g2.dat`.

`0005-starcraft-construction-toolbar.patch` adds the dedicated StarCraft button
beside ride construction. It invokes the plugin's registered construction menu
item and remains hidden when that item is unavailable. The Barracks scenery
object is generated locally from the player's classic StarCraft MPQs by
`scripts/install-starcraft-construction-object.py`; see
`docs/barracks-starcraft-art.md`. No extracted art is in the patch.

`0006-barracks-training-animation.patch` adds a display-only building tile
registry and selects the generated Barracks GRP frame bank while OpenBW reports
an active training queue. The plugin updates it through `setBuildingAnimations`;
the ordinary large-scenery images and saved object ID remain stable.
`0007-barracks-light-only.patch` updates the native bank comment for existing
patched checkouts. The generated object repeats the idle frame in its dark
banks and blends only indicator lights into the lit banks.

`0008-actor-visual-registry.patch` resolves supported actor visuals through a
type mapping. `0009-building-animation-registry.patch` tracks animation banks
per scenery object with a declared frame count and cadence. The Barracks keeps
its original seven training light frames at three ticks each.

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

The native compatibility version is 5 and the asset version is 4. Older bridge clients are rejected by the plugin. `BRIDGE_SPRITE_SOURCE=starcraft-local` installs local StarCraft unit art; `alien-scout` uses original open unit art and a CC0 Marine placeholder. Barracks scenery art is generated locally from the player's StarCraft data in either mode.

`0017-json-byte-vector-portability.patch` passes byte-vector JSON input as a
character view. This preserves the parsed bytes and builds with the libc++
`char_traits` definitions supplied by the pinned Emscripten toolchain.

`0018-socket-immediate-connect.patch` handles a nonblocking socket that connects
immediately under Emscripten's WebSocket-backed POSIX layer. Native TCP behavior
and the OpenRCT2 multiplayer packet protocol remain unchanged.
`0019-network-future-include.patch` supplies the standard `<future>` declaration
needed when multiplayer is enabled in the browser build.

`0021-authoritative-new-game-menu.patch` sends the connected client's File → New
Game and File → Load Game actions to the existing StarCoaster park picker. Local
OpenRCT2 games retain the standard file menu. The server still validates park
names and performs the fresh OpenBW session transition.
