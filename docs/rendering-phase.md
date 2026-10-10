# Local Zergling renderer

The repository defaults to the original CC0 alien scout. The classic StarCraft
artwork is prepared only from a local installation and stays under ignored
`run-data/`. The network unit still has `kind: "alien_scout"`; artwork selection
does not change simulation or synchronized actions.

## Prepare and build

Install Pillow and StormLib's `smpq` utility (Debian package `smpq`). Fetch and
build the pinned upstream projects using the [bootstrap guide](bootstrap.md),
then run:

```bash
python3 scripts/prepare-starcraft-sprites.py --game-dir "$STARCRAFT_DATA_DIR" --unit zergling
BRIDGE_SPRITE_SOURCE=starcraft-local scripts/build-openrct2.sh
scripts/install-openrct2-local.sh
python3 scripts/create-render-test-park.py
DEMO_PARK=run-data/park-generator/save/bridge-render-test.park \
  DEMO_OUTPUT_DIR=run-data/zergling-regression \
  python3 scripts/capture-live-demo.py --seconds 65 --cycle-rotations \
    --verify-zergling --publisher-restart --sample-animation
python3 scripts/verify-rendered-sprites.py \
  --capture-dir run-data/zergling-regression --expect-motion walk --axis east-west
```

`STARCRAFT_DATA_DIR` defaults to `/home/pi/games/starcraft` if omitted. The
preparation script requires classic MPQs and searches `Patch_rt.mpq`,
`BrooDat.mpq`, then `StarDat.mpq` for each resource. It records which archive
provided each resource. The selected pack contains 24 transparent PNGs and a
manifest with source frame, dimensions, mirroring, visible pixel count, and
OpenRCT2 draw offset. The build script validates every frame before staging it
in the ignored upstream checkout. A missing local pack fails with a direct
message before compilation.

The Zergling body is `unit/zerg/zergling.grp`. This installation's resource is
296 frames on a 128×128 canvas. The script uses `Tileset/Badlands.wpe`, the
palette OpenBW loads for the Badlands terrain. Three 17-direction groups are
used for idle and two walking poses. Source directions 0, 4, 8, 12, and 16 are
north, northeast, east, southeast, and south; western directions mirror the
eastern counterparts. The CC0 pack's four diagonal slots reuse nearby cardinal
art. StarCraft's team colour indices 8–15 are
left in their neutral source colour, and separate shadow artwork is omitted.
The script maps opaque RGB values to OpenRCT2's standard palette before the
`g2.dat` build. Without this step, OpenRCT2's default exact-colour import
silently drops most pixels. Transparent pixels remain transparent.

[IronGRP](https://github.com/sjoblomj/irongrp) was evaluated for GRP-to-PNG
conversion. Its `--transparent` option and palette handling fit this task.
The local script instead decodes the RLE subset used by this GRP directly, so
the workflow does not require Rust/Cargo and can retain the source frame
coordinates for anchors. [mpyq](https://github.com/eagleflo/mpyq) is unsuitable
for these classic archives because it does not support all of their compression
formats; `smpq` uses StormLib.

To return to the public pack:

```bash
BRIDGE_SPRITE_SOURCE=alien-scout scripts/build-openrct2.sh
scripts/install-openrct2-local.sh
```

The `g2.dat` target rebuilds when staged PNG bytes or image offsets change.
Do not commit, publish, or package extracted MPQs, GRPs, local PNGs, or a
compiled `g2.dat` containing Blizzard art without appropriate permission.

## Visual regression

`create-render-test-park.py` starts the pinned `BigMapTest.sv6` park locally,
adds a path along the actor's x=320..640, y=480 route, two large trees, a
smaller tree, a fence, and a raised section, then saves an ignored `.park` file.
The generator script in `scripts/render-test-park.js` makes this reproducible.

`capture-live-demo.py` starts one headless OpenBW publisher, one OpenRCT2
server, and two graphical clients. Client A stays at rotation 0. With
`--cycle-rotations`, client B rotates independently through 0–3, and screenshots
are tagged with its actual camera rotation. The capture checks synchronized
session, tick, identity, motion, and position logs. `--verify-zergling` also inspects screenshot
pixels for the Zergling's localized purple body and verifies that it moves on
client A. `--publisher-restart` captures actor removal and return; the capture
retries a client park transfer up to twice if OpenRCT2 reports decompression
failure, preserving the failed logs. The separate `verify-rendered-sprites.py`
compares visible screenshot pixels with the generated PNGs at the capture zoom,
checks walking frames and camera-relative direction, and records match scores.
The saved screenshots remain the evidence for occlusion and ground contact,
which a colour check alone cannot establish.

On 2026-10-10, the final controlled 65-second run produced 15 screenshots per
client, including all four rotations on client B, removal after publisher
disconnect, and return after a new session. The Zergling was detected in 11
captures per client; 657 common snapshots matched in session, tick, identity,
motion, and position, with no desync warning. Exact pixel matching identified
both walking poses, direction changes, and an idle frame near the end. A
stationary target probe matched the idle PNG exactly in all six screenshots and
reported only `idle` snapshots. A diagonal route test matched diagonal source
frames across all four camera rotations. The original alien scout also rendered
in the scenery park on both clients with 155 matching snapshots after the
eight-direction extension.

Some client park transfers intermittently fail with a zstd decompression
error while the bridge is publishing. The capture tool now retries those joins
and retains each failure log; the transfer failure has not been isolated.
Separately, a 65-second graphical run of `EverythingPark.park` with **no bridge
plugin or publisher** produced `Srand0 mismatch` and a network desync dialog on
both clients. That warning occurs independently of sprite rendering.
