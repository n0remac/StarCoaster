> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Eight-unit visualization bridge

`BRIDGE_DEMO_UNITS=8` makes the BWAPI module create eight Zerglings with distinct IDs and patrol endpoints. The default remains one unit. The publisher sorts by BWAPI ID and sends a complete v1 array every third BW frame. All three receiver layers cap arrays at 32 units; publisher and plugin cap a newline-delimited JSON packet at 16 KiB. The plugin rejects an entire packet on any invalid or duplicate actor. A publisher disconnect sends one synchronized empty array.

The native store swaps an immutable vector on each accepted action. A tile bucket routes each actor to its own map tile; OpenRCT2's paint sorter uses the actor's ground contact height and body volume. Each actor has its own walking start tick and stable ID-derived phase. Display interpolation blends only between two received positions for at most eight OpenRCT2 ticks, and snaps across a new session, large displacement, or long update gap. The synchronized coordinates never change during interpolation.

The locally extracted 296-frame classic Zergling GRP was inspected as 17 directional groups. Group 0 supplies idle. Groups 1–10 form the ten-pose run cycle. Groups 11 onward crouch or collapse and are excluded from locomotion. The generated manifest records each frame's group, source index, mirror status, 128×128 canvas crop offset, palette conversion, and transparent-pixel count. The 88 staged `g2` entries cover one idle and ten walk poses in eight directions. The original CC0 art is repeated into the extra walk slots when `BRIDGE_SPRITE_SOURCE=alien-scout` is selected.

Build and capture on the Pi:

> Historical command removed in v0.6; use the packaged scenario CLI.


`verification.json` compares canonical `(id,x,y,facing,motion)` sets for every common `(session,seq)` across the server and two graphical clients. It also records per-ID projected screenshot pixel counts and walk-region changes. `screenshot-states.json` pairs screenshots with logged source positions and terrain height. `video-metadata.json` contains FFprobe output and recording events. On a failed capture, logs, screenshots, and any finalized video stay under the requested ignored output directory.

For exact frame provenance, run `python3 scripts/verify-squad-frames.py run-data/squad-demo`. It searches near each logged actor's screen projection and requires at least four distinct GRP-derived walk poses to match opaque PNG pixels. The result is retained as `sprite-match.json`.

OpenBW remains authoritative. The proxy actors have no OpenRCT2 collision, pathfinding, combat, or damage logic. Blizzard artwork and derived sprites stay under ignored `run-data/`.
