> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Local Zergling renderer

Direct developer builds default to the original CC0 alien scout;
`scripts/start.sh` selects and prepares local StarCraft Marine and Zergling art
by default. The classic StarCraft artwork is prepared from a local installation and stays under ignored
`run-data/`. The network unit still has `kind: "alien_scout"`; artwork selection
does not change simulation or synchronized actions.

## Prepare and build

Install Pillow and StormLib's `smpq` utility (Debian package `smpq`). Fetch and
build the pinned upstream projects using the [bootstrap guide](../bootstrap.md),
then run:

> Historical command removed in v0.6; use the packaged scenario CLI.


`STARCRAFT_DATA_DIR` defaults to `/home/pi/games/starcraft` if omitted. The
preparation script requires classic MPQs and searches `Patch_rt.mpq`,
`BrooDat.mpq`, then `StarDat.mpq` for each resource. It records which archive
provided each resource. The Zergling pack contains 136 transparent PNGs and a
manifest with source frame, dimensions, mirroring, visible pixel count, and
OpenRCT2 draw offset; the Marine pack contains 56 frames. The build script validates every frame before staging it
in the ignored upstream checkout. A missing local pack fails with a direct
message before compilation.

The Zergling body is `unit/zerg/zergling.grp`. This installation's resource is
296 frames on a 128×128 canvas. The script uses `Tileset/Badlands.wpe`, the
palette OpenBW loads for the Badlands terrain. Seventeen directional groups are
used for idle, ten walking poses, and six death poses. Source directions 0, 4, 8, 12, and 16 are
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

`former render park generator` starts the pinned `BigMapTest.sv6` park locally,
adds a path along the actor's x=320..640, y=480 route, two large trees, a
smaller tree, a fence, and a raised section, then saves an ignored `.park` file.
The generator script in `scripts/former render park plugin` makes this reproducible.

`former prototype capture driver` starts one headless OpenBW publisher, one OpenRCT2
server, and two graphical clients. Client A stays at rotation 0. With
`--cycle-rotations`, client B rotates independently through 0–3, and screenshots
are tagged with its actual camera rotation. The capture checks synchronized
session, tick, identity, motion, and position logs. `--verify-zergling` also inspects screenshot
pixels for the Zergling's localized purple body and verifies that it moves on
client A. `--publisher-restart` captures actor removal and return; the capture
retries a client park transfer up to twice if OpenRCT2 reports decompression
failure, preserving the failed logs. The separate `verify-rendered-sprites.py`
compares visible screenshot pixels with the generated PNGs at the capture zoom,
checks walking frames and camera-relative direction (including diagonal
headings with the expected axis component near turns), and records match scores.
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

## Video capture and remote review

Install FFmpeg and FFprobe with `sudo apt-get install ffmpeg`. The optional
recorder reads the two existing Xvfb displays after both clients have joined.
It records through the screenshot checks and publisher restart, then finalizes
the MP4 before Xvfb exits. For the full visual regression:

> Historical command removed in v0.6; use the packaged scenario CLI.


The default `combined.mp4` is 1920×600: client A occupies the left 960×600
half and client B the right. The defaults are 10 FPS, H.264, CRF 32,
`veryfast`, and no audio. For separate simultaneous recordings, use
`--video-layout separate`; this writes `client-a.mp4` and `client-b.mp4`
instead. `--video-width` sets each client's even output width; height follows
the original 1280×800 aspect ratio. `--video-fps`, `--video-crf`, and
`--video-preset` control capture rate and encoding. A lower-cost setting is
`--video-fps 5 --video-preset ultrafast`; a lower CRF raises quality and file
size. No video flags are needed for the original PNG-only capture.

The chosen `DEMO_OUTPUT_DIR` contains the MP4, `video-capture.log`,
`video-metadata.json`, client/server logs, and original screenshots. Metadata
records UTC capture times, elapsed time, encoder settings, output size and
measured frame rate, display IDs, test status, and screenshot/event offsets
from the recording's monotonic start. Each output also has an estimated delay
before its first encoded frame, so later tools can align event offsets with
video positions. Recordings are retained on test failure.
FFprobe checks H.264, resolution, nonzero frames, and duration after shutdown.
The lossy video is for motion review; keep using the original PNGs with
`verify-rendered-sprites.py` for exact sprite comparison.

From a laptop with SSH/Tailscale access, copy a recording and play it locally:

```bash
scp pi:/path/to/StarCoaster/run-data/zergling-video/combined.mp4 .
mpv combined.mp4
```

To browse all artifacts without copying them first, mount the Pi directory
with SSHFS (install `sshfs` on the laptop if needed):

```bash
mkdir -p ~/starcoaster-captures
sshfs pi:/path/to/StarCoaster/run-data/zergling-video ~/starcoaster-captures
ls ~/starcoaster-captures
fusermount -u ~/starcoaster-captures
```

The output stays under ignored `run-data/`; do not commit recordings, PNGs, or
locally extracted game graphics.

### Pi performance check (2026-10-10)

Run the same 65-second rotation, animation, Zergling, and publisher-restart
regression at all capture rates with:

```bash
python3 scripts/benchmark-video-capture.py
```

The script saves per-run logs and MP4s under `run-data/video-benchmark-*` and
sampled process metrics in `run-data/video-benchmark-summary.json`. One run of
each mode on this Pi, with the local scenery park and `veryfast`/CRF 32, gave:

| Capture | Wall time | FFmpeg CPU, one-core equivalent | Peak FFmpeg RSS | MP4 size | Encoded FPS | Common snapshots / mismatches |
|---|---:|---:|---:|---:|---:|---:|
| Off | 103.0 s | — | — | — | — | 656 / 0 |
| 5 FPS | 118.0 s | 27.8% | 273 MiB | 0.99 MiB | 5.0 | 674 / 0 |
| 10 FPS | 113.0 s | 54.7% | 274 MiB | 1.11 MiB | 10.0 | 690 / 0 |
| 15 FPS | 116.4 s | 81.5% | 272 MiB | 1.21 MiB | 15.0 | 684 / 0 |

All four runs passed the PNG and multiplayer checks with no desync warning.
Client B advanced over 3,545, 3,751, 3,946, and 4,035 OpenRCT2 ticks,
respectively. The sampled peak sum of process RSS for the full test tree was
1,313 MiB without video and 1,611–1,618 MiB with video; shared memory can be
counted more than once in this sum. Wall time includes startup, park transfer,
pixel verification, video finalization, and FFprobe, so a single run at each
rate does not isolate a small encoding effect on test duration. These runs
show no observed multiplayer disruption at the default 10 FPS. The 5 FPS
`ultrafast` setting above is available if another Pi has less CPU headroom.
