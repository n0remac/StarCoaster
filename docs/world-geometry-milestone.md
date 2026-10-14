# 256×256 world geometry and terrain navigation

StarCoaster uses one OpenRCT2 tile for one OpenBW build tile. Parks up to
256×256, including rectangular parks allowed by OpenRCT2, are centered in the native 256×256 map.
The offset on each axis is `(256 - park_tiles) / 2`, rounded down. Frontier's
64×64 park therefore starts at native tile (96, 96). Pixel coordinates retain
their 32-pixel tile scale in both engines; transforms reject a larger park
instead of compressing it. The generated StarCraft CHK includes matching
256×256 `DIM`, `MTXM`, `TILE`, `MASK`, and `ISOM` sections. Native VF4 obstacle
overlays share immutable variants, avoiding the 0x8000 tile-index limit.

OpenRCT2 exports base surface height in its world-Z units, raw slope bits,
water, walkability, and ground-path base height and slope direction. One
`baseHeight` step is 8 world-Z units; a land slope rises 16 units. The bridge
derives four quarter heights from OpenRCT2's native slope encoding and joins
adjacent tiles only when both heights at their shared edge agree. A valid
slope joins low and high ground; a flat height jump is a cliff. Ambiguous
diagonal encodings, overlapping ground paths, and paths that do not follow
the one supported surface fail with `unsupported_terrain`.

The bridge derives one packed 8-pixel native collision mask and sends the same
hash to both OpenBW participants. Startup waits for both applied hashes.
Centered-map padding, water, missing terrain cells, and solid park footprints
are blocked. Cliffs block both full tiles beside an incompatible edge:
live native path smoothing crossed narrower barriers. The ridge is wide enough
to retain an open interior and a usable slope. A confirmed demolition derives
and schedules a new mask without clearing permanent terrain barriers. OpenBW
continues to own movement, pathfinding, collision, and combat; actors retain
2D movement coordinates. OpenRCT2 samples its own terrain height at the
actor's interpolated X/Y for painting, including the health bar. Raised paths
above a ground actor are not chosen as its surface.

Frontier Outpost remains 64×64. Its southwestern Marine staging garden now has
55 raised flat tiles at Z=128, 15 native slope tiles, three approaches, and a
cliff along the western side. Six Marines begin on the raised platform. The
carousel, Ferris wheel, shops, defense gate, and existing wall and ride
demolition routes remain. Regenerate with `scripts/project.sh park`; the
playable fixture must have layout version 4. Sloped footpaths use OpenRCT2's
native uphill direction, so their visible ramps follow the ground slope.
The normal `scripts/start.sh` launcher installs the bridge plugin for its
graphical client. Its Frontier scenario starts six Marines and twelve
Zerglings, then issues a five-Zergling `on_ready` spawn wave. Use
`tests/test_playable_start_live.sh` to check the regular launcher or
`PLAYABLE_FULL_START=1 tests/test_playable_start_live.sh` to include the full
fetch, build, and park-regeneration startup path.

## Reproduce the live evidence

With the pinned patched engines built and licensed data provided:

```sh
export RCT2_DATA_DIR=/path/to/rct2
export STARCRAFT_DATA_DIR=/path/to/starcraft
scripts/project.sh park
scripts/project.sh test
tests/test_frontier_ridge_live.sh
tests/test_frontier_native_navigation_live.sh
python3 tests/test_world_256_native_live.py
scripts/project.sh record --duration 45 --video-layout combined --cycle-rotations --ridge-probe
scripts/project.sh record --duration 45 --video-layout combined --cycle-rotations --ridge-assault
scripts/project.sh record --duration 40 --video-layout combined --cycle-rotations --world-256
```

The ridge probe observes a Marine below the cliff, verifies no direct cliff
crossing, then records slope ascent and a later native attack. The test-only
ridge assault changes starting Zergling tiles and makes the existing native
assault policy pursue Marines so its graphical capture shows Zerglings
ascending the saved park's actual slope and fighting on top. Normal Frontier
scenario AI and spawning are unchanged. The separate scale fixture is generated
from a local OpenRCT2 test park by `scripts/create-world-256-park.py` and its
native map by `scripts/create-world-base-map.py --scenario
scenarios/world-256-scale-map.json --output run-data/world-256-park/world-256-scale.scm`.
The scale capture issues commands at opposite boundaries and toward the distant
map center. Its two graphical clients watch opposite edges.

Generated parks, licensed game data, captures, logs, videos, and verification
JSON stay under ignored `run-data/`. The `run-data/artifacts/` directory holds
combined MP4s, rotation screenshots, process logs, performance measurements,
and machine-readable checks. Neither test-only probe is loaded by the normal
playable launcher.

## Measured runs and limits

The live native 256×256 probe loaded a real map, moved a Marine near the far
edge, routed a Zergling through the only slope opening, and applied a fully
blocked 65,536-tile mask in 0.554 seconds. Three follow-up native scale probes
passed with the Zergling initially outside autonomous sight range and mask
application times of 0.563, 0.556, and 0.555 seconds. Their evidence is under
`run-data/world-256-native-1791935337/`, `run-data/world-256-native-1791935352/`,
and `run-data/world-256-native-1791935361/`. The Frontier ridge route passed in
`run-data/frontier-ridge-1791933750/`; the existing demolition regression
passed on the raised park in `run-data/frontier-native-nav-1791933583/`.

The final `scripts/project.sh test-live` run passed every stage. Its current
ridge, demolition-navigation, native-scale, and two-client world logs are in
`run-data/frontier-ridge-1791937169/`,
`run-data/frontier-native-nav-1791937207/`,
`run-data/world-256-native-1791937306/`, and
`run-data/world-live-1791937312/`. Both Frontier victory/reconnect cycles
passed in `run-data/frontier-lifecycle/cycle-1/` and `cycle-2/`; the two
actor lifecycle cycles passed in `run-data/actor-live-1791937351/` and
`run-data/actor-live-1791937397/`. Dynamic Marine and Zergling runs passed
in `run-data/unit-spawn-live-1791937445/` and
`run-data/zerg-spawn-live-1791937455/`. Extra Marine recovery runs passed
with bridge restart/death/replacement in
`run-data/unit-spawn-live-1791937488/` and with an interrupted in-flight
native creation in `run-data/unit-spawn-live-1791937512/`; both retained five
unique native Marine IDs and matching eleven-Marine client rosters.

The separate graphical 256×256 run passed in
`run-data/artifacts/20261013T234132Z-fa590fa2222d/`. Both graphical clients
matched 241 actor snapshots and saw the opposite park boundaries; the native
map reported 256×256, the park exported 65,536 terrain cells and two marker
objects, and the far Marine reached X=8080 without coordinate compression.
With 70 ms frame pacing on this host, startup to `WORLD_READY` took 27.333 s,
derivation through both native collision acknowledgements took 1,180 ms, the
headless server stack and two native participants used 311,120 KiB resident
memory at readiness, and the clients received 6.45 and 6.00 actor snapshots
per recording second while their local OpenRCT2 ticks advanced at 55.33 and
51.62 per second. These are one-run measurements, not performance limits.

Graphical Marine and Zergling elevation runs passed with four camera rotations,
matching two-client snapshots, slope-height interpolation, and no sampled
height jump above 16 units:

- `run-data/artifacts/20261013T232900Z-98cbdcd8f129/` — Marine descent,
  slope return, and later combat.
- `run-data/artifacts/20261013T232727Z-426b30271787/` — Zergling ascent
  and combat on elevated terrain.

The normal playable Frontier capture passed at
`run-data/artifacts/20261013T234255Z-70da25291a24/`. Both OpenRCT2 clients
matched 454 actor snapshots and changed from carousel present to carousel
demolished after the server confirmed native removal. It recorded Marine
attack frames, Zergling damage, screenshots, process logs, and a combined MP4.
The automated recorder labels this a capture-only run because it did not
perform drag selection or issue a player Marine command; the separate live
ridge and navigation probes exercise those commands and their resulting
positions and demolition routes.

The milestone supports only one ground surface at each X/Y. Elevated bridges,
tunnels with overlapping actors, live terrain construction, flying units, and
StarCraft high-ground combat bonuses remain outside this geometry model.
Very narrow ramps next to multiple cliffs can be closed by the conservative
two-tile native clearance; widen the approach in the park instead of bypassing
OpenBW collision.

The playable startup correction was verified with the full
`scripts/start.sh --client` chain in `run-data/playable-start-1791944156/`.
The current layout version 4 passed ridge routing in
`run-data/frontier-ridge-1791944312/`, demolition navigation in
`run-data/frontier-native-nav-1791944351/`, and the complete
`scripts/project.sh test-live` suite. Its normal graphical launcher run is
`run-data/playable-start-1791944622/`, with a screenshot and
`verification.json` showing six starting Marines, twelve starting Zerglings,
and five automatically spawned Zerglings in the same client.
The updated 55-second two-client ridge capture is in
`run-data/artifacts/20261014T023210Z-3da25e4532f5/`: its four rotations,
combined video, actor-height samples, cliff detour, slope return, and combat
checks passed. Client B joined after the ready wave and lacked those five
runtime actors for 33 shared snapshots. It received their lifecycle replay at
sequence 68; all 277 later shared snapshots matched. Capture verification
reports this initial join interval separately and fails any mismatch after
convergence.

## Frontier terrain orientation correction

The terrain correction keeps layout version 4 and adds `terrain_version: 1`
to the playable fixture. Regenerate older fixtures with `scripts/project.sh park`.
The northern approach uses land slope 9, the southern approach slope 6,
and the eastern approach slope 12. Their footpath uphill directions remain
1, 3, and 0 respectively. All three approaches rise toward the platform.

OpenRCT2's named north corner lies at tile-local `(32,32)`, rather than
`(0,0)`. The bridge now compares corners in map-coordinate order
`(0,0), (32,0), (32,32), (0,32)`, using raised-corner bits 4, 2, 1, 8.
Footpath directions map to land slopes 12, 9, 3, 6, as in OpenRCT2's
`kPathSlopeToLandSlope`. The previous terrain and bridge edge mapping were
both reversed, so their agreement did not establish correct native painting.
The earlier visual evidence above predates this correction.

Verification after the correction:

- `scripts/project.sh park` regenerated `run-data/frontier-playable/save/frontier-outpost-playable.park`: 216 walls, 350 path tiles, 15 ride tiles, 55 raised tiles, and 15 slopes.
- `python3 -m unittest tests/test_frontier_park_geometry.py` passed both geometry checks, including connections at all three ridge approaches.
- `scripts/project.sh test` passed Go, three C++ checks, Python (55 tests, two skipped), and JavaScript checks; log: `run-data/frontier-slope-tests.log`.
- `go build -o build/world-bridge ./cmd/world-bridge` rebuilt the bridge used by the live runs.
- `tests/test_frontier_ridge_live.sh` passed all six route/combat checks in `run-data/frontier-ridge-1791949428/verification.json`.
- `tests/test_frontier_native_navigation_live.sh` passed all six navigation/demolition checks in `run-data/frontier-native-nav-1791949475/verification.json`.
- `python3 tests/test_world_256_native_live.py` passed in `run-data/world-256-native-1791949575/`. An earlier attempt overlapped the ridge run and failed because port 40011 was in use; the sequential retry passed.

Local runs set `RCT2_DATA_DIR=/home/cameron/games/rct2` and
`STARCRAFT_DATA_DIR=/home/cameron/games/starcraft`. The initial sandboxed
park-generation and regression attempts could not access localhost sockets
and the Go cache; the successful runs used the approved local execution context.

The two-client graphical command
`scripts/project.sh record --duration 55 --video-layout combined --cycle-rotations --ridge-probe`
passed in `run-data/artifacts/20261014T034649Z-e36a349a88fd/`, using
`PATH=/tmp/starcoaster-xvfb/usr/bin:$PATH`. The first attempt could not find
Xvfb on the default PATH (`run-data/artifacts/20261014T034630Z-bf96b2345450/`);
the retry used the already available local binary. All four saved camera
views were inspected for aligned land and path ramps. The elevation JSON
passes all eight checks: native painter heights include 112, 114, 116, 119,
120, 122, 123, 126, 127, and 128 with no sampled jump over 16. The clients
matched 272 shared snapshots after five initial join mismatches, with no
post-convergence mismatch. This is a capture-only check driven by the
test-only ridge probe, not a completed player-controlled gameplay demo.
Generated parks, screenshots, and the combined MP4 remain ignored local artifacts.
