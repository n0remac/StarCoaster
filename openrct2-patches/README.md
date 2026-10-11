# OpenRCT2 native patch

`0001-native-bridge.patch` applies to the pinned OpenRCT2 commit in `dependencies.lock.json`. `scripts/build-openrct2.sh` applies it and stages generated sprites. The patch contains source and sprite metadata only; it does not contain StarCraft art or a compiled `g2.dat`.

The fork paints Marine and Zergling actors in the world paint pass, including walking, attacks, deaths, and health bars. An immutable snapshot registry preserves safe access during rendering; old and new regions are invalidated for movement. The fork exposes snapshot, hit testing, cursor location, and actor inspection bindings to the plugin. It also adds `onRightClick` to the existing custom map tool, since OpenRCT2 intentionally does not route right mouse clicks through shortcuts. The plugin distributes state through synchronized game actions and sends player orders to the Terran BWAPI endpoint.

The native compatibility version is 4 and the asset version is 3. Older bridge clients are rejected by the plugin. Local art is installed with `BRIDGE_SPRITE_SOURCE=starcraft-local`; the public `alien-scout` build uses original open art and a CC0 Marine placeholder.
