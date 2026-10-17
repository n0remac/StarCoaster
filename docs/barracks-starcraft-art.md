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

The Barracks uses one static source frame. Classic idle animation, shadow,
damage overlays, and team-colour remapping are not yet rendered.

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
