# Classic StarCraft Barracks art

The Terran Barracks large-scenery object now uses frame 0 of the classic
`unit/terran/TBarrack.grp` from the player's StarCraft MPQs. The filename is
resolved by the pinned game's `images.dat` and `images.tbl` entry for the
Barracks. The installer also reads `Tileset/Badlands.wpe`, maps the sprite to
OpenRCT2's indexed palette, and writes a local `.parkobj` under ignored
`build/` and `run-data/` paths. No extracted image or packaged object is in Git.

The object's identifier and 12 occupied tiles remain the same. OpenRCT2 paints
large scenery in tile regions, so the object gives each tile the same sprite
with an offset that joins the regions into one image. Offsets are calculated
for all four park rotations. The launcher refreshes both the staged object and
each local OpenRCT2 user object's copy before loading a park. This lets older
saves keep their Barracks ID, health, and geometry while using the new art.

The object keeps classic frame 0 in its original idle image bank. Seven more
banks contain completed-building GRP frames 2–8; frame 1 depicts the unfinished
structure and is excluded. All frames share one crop and tile alignment. The
OpenRCT2 plugin sends a display-only tile set to the native renderer when the
authoritative OpenBW `building.state` queue is nonempty. The renderer cycles
those seven banks at eight frames per second and returns to frame 0 when the
queue empties, the native building dies, or the park target is removed. Each
client may display a different animation phase. Training, health, and
demolition remain authoritative in OpenBW and the synchronized park world.

Classic shadows, damage overlays, and team-colour remapping are not yet
rendered. No animation images are committed.

## Verification

- `scripts/project.sh test` passed: Go, C++, 87 Python tests (one skipped),
  and JavaScript plugin checks.
- `BARRACKS_TEST_HEALTH=700 tests/test_barracks_save_load_live.sh` passed in
  `run-data/barracks-save-load-live-1792203855/verification.json`: a real park
  save/load retained generation `#1`, 700 HP, and the same navigation hash;
  demolition and reconstruction produced `#2`.
- `scripts/project.sh record --scenario mt-zergling --duration 40 --no-video
  --video-layout combined --barracks-production` passed in
  `run-data/artifacts/20261017T022610Z-46cf99fb8def/verification.json` with
  334 matching shared snapshots and no mismatches. Manual screenshots in that
  directory show the full building on both clients, its information window,
  and a native Train Marine request.
- A longer manual graphical session under
  `run-data/artifacts/20261017T022016Z-6066e1aa2b90/` captured the full
  Barracks, the information window, native queue progress, and a completed
  Marine beside it. The server log records a native train call and both actor
  bindings. That recorder was interrupted before writing `verification.json`,
  so the shorter completed capture above is the two-client sync record.
- `run-data/generated-assets/starcraft/barracks/rotation-0.png` through
  `rotation-3.png` show the new art in all four OpenRCT2 park rotations when
  rendering an older Barracks save with the refreshed local object installed.

### Training animation

- `scripts/project.sh test` passed after adding the animation banks and native
  bridge binding. The Barracks plugin test checks training, completion, and
  target removal; the object test checks all 388 image entries and the 12-tile
  footprint.
- `tests/test_barracks_production_live.sh` passed in
  `run-data/barracks-production-live-1792205081/verification.json`: one genuine
  Marine completed training and accepted a movement order. The cancellation
  variant passed in `run-data/barracks-production-live-1792205306/verification.json`.
- `scripts/project.sh record --scenario mt-zergling --duration 50
  --video-layout combined --barracks-production --barracks-training-probe`
  passed in `run-data/artifacts/20261017T024533Z-a5287501a5a3/` with a
  combined video, timed screenshots from both clients, and 435 matching shared
  world snapshots. The building crop changes during training on both clients
  and returns to the same idle image in later samples.
- The final automated graphical check used the same command with `--duration 45
  --no-video`. Its `run-data/artifacts/20261017T024931Z-7db9ab1fa81b/verification.json`
  reports construction, native training, Marine completion and movement,
  multiple Barracks frames on both clients, and 397 matching shared snapshots.
