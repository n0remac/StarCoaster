# OpenRCT2 native patch

`0001-native-bridge.patch` applies to the commit pinned in `dependencies.lock.json`. `scripts/apply-openrct2-patches.sh` applies it once and copies the separately tracked, original creature PNGs into the checkout; `scripts/build-openrct2.sh` calls that script automatically.

The patch adds twelve image IDs, an immutable one-actor presentation registry, world paint beside `EntityPaintSetup`, old/new viewport invalidation, terrain-base Z, camera-relative four-direction art, two walking frames, and a QuickJS `rtsBridge.applySnapshot` binding. It also advances the headless client network handshake from the title scene. The matching remote plugin calls the binding only from synchronized custom action execution. Server and two headless clients replicated 143 common snapshots with matching ticks and coordinates. A graphical client with RCT2 `g1.dat` is still needed to inspect placement and occlusion.
