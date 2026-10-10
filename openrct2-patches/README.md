# OpenRCT2 native patch

`0001-m1-paint-probe.patch` applies to the commit pinned in `dependencies.lock.json`. `scripts/apply-openrct2-patches.sh` applies it once and copies the separately tracked, original creature PNGs into the checkout; `scripts/build-openrct2.sh` calls that script automatically.

This is an **M1 probe**, not the synchronized bridge. It adds twelve image IDs and a fixed alien scout at world position `(320, 480)` through `PaintAddImageAsParent`, called beside `EntityPaintSetup` for the appropriate tile. It uses the terrain's base Z, camera rotation, a paint bounds box, and noninteractive selection. A graphical client with RCT2 `g1.dat` is needed to inspect occlusion and sprite offsets. The actor is not yet animated, driven by snapshots, invalidated on movement, or distributed to two clients. The presentation registry and script binding are the next renderer steps.
