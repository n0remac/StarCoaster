> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Playable startup patch upgrade verification

The missing-unit startup failure was reproduced on 2026-10-13 with the local
licensed RCT2 and StarCraft data. The OpenBW checkout still contained the older
navigation implementation, which allocated a native VF4 overlay for every
blocked tile. The padding around the centered 64×64 park exhausted the 0x8000
tile-index limit. Both participants rejected the mask with
`native_navigation_update_failed`, and the park reported `WORLD_NOT_READY`.

The build previously checked only for the `set_park_navigation` function name,
so subsequent `scripts/start.sh` runs kept rebuilding the older implementation.
`scripts/apply-bwapi-patches.py` now checks each complete engine patch, applies
missing patches, and upgrades the known older overlay through
`0004-native-navigation-upgrade-openbw.patch`. The result is the existing
current `0002-native-navigation-openbw.patch`, which shares immutable overlay
variants. Unrelated source edits are preserved; unexpected conflicts stop the
build. Engine authority and scenario unit counts are unchanged.

## Commands and results

The tests used `RCT2_DATA_DIR=/home/cameron/games/rct2` and
`STARCRAFT_DATA_DIR=/home/cameron/games/starcraft`. The unit gate used
`GOCACHE=$PWD/build/go-cache`. Xvfb was unpacked into
`/tmp/starcoaster-xvfb` for the graphical tests, with its `usr/bin` directory
added to `PATH`; no system package was installed.

| Command | Result | Evidence under `run-data/` |
| --- | --- | --- |
| Headless `the former Frontier shortcut` before the upgrade | Reproduced failure | `startup-diagnosis/before-upgrade.log` |
| `python3 -m unittest discover -s tests -p test_bwapi_patches.py -v` | PASS, 3 tests | Fresh application, repeated builds, legacy upgrade, preservation of unrelated edits, and conflicting edits |
| `scripts/build-bwapi.sh` | PASS, old navigation upgraded and engine rebuilt | `startup-diagnosis/build-bwapi.log` |
| `scripts/project.sh test` | PASS | `startup-diagnosis/unit-tests.log`; Go, 3 C++ tests, 53 Python tests (2 skipped), JavaScript |
| `tests/test_playable_start_live.sh` | PASS | `playable-start-1791946452/verification.json` and `screen.png` |
| `PLAYABLE_FULL_START=1 tests/test_playable_start_live.sh` | PASS, full `scripts/start.sh --client` chain | `playable-start-1791946508/verification.json`, `screen.png`, and `session.log` |
| `tests/test_frontier_ridge_live.sh` | PASS, all 6 checks | `frontier-ridge-1791946519/verification.json` |
| `tests/test_frontier_native_navigation_live.sh` | PASS, all 6 checks | `frontier-native-nav-1791946554/verification.json` |
| `python3 tests/test_world_256_native_live.py` | PASS | `world-256-native-1791946650/verification.json` |

The full startup regenerated layout version 4 and showed all six Marines,
twelve starting Zerglings, and five automatic wave units in client snapshots.
The screenshot was reviewed and shows both armies. Both native participants
accepted the same navigation hash. The scale probe applied a fully blocked
65,536-tile native mask in 0.555 seconds.

`startup-diagnosis/regressions.json` records the live command exit codes and
durations. The two skipped Python tests require an optional retained squad
capture that is absent here. This run checked one graphical startup client;
the complete multiplayer and actor lifecycle suite was not rerun. Game data,
engine binaries, generated parks, and captures remain ignored local artifacts.

## StarCraft artwork startup correction

`scripts/start.sh` also left `BRIDGE_SPRITE_SOURCE` unset, so the OpenRCT2 build
selected the original handmade pack even when local StarCraft frames existed.
Startup now defaults to `starcraft-local` and prepares both units from the
supplied MPQs before building and installing `g2.dat`. Archive spelling aliases
and relative game-data paths work during extraction. Selecting StarCraft art
requires the Marine manifest, preventing a mixed pack with placeholder Marines.
An explicit `BRIDGE_SPRITE_SOURCE=alien-scout` still selects the original art.

| Command | Result | Evidence under `run-data/` |
| --- | --- | --- |
| `scripts/project.sh test` with the same local Go cache | PASS; 55 Python tests, 2 optional capture tests skipped, plus Go/C++/JavaScript | `starcraft-startup/unit-tests.log` |
| `PLAYABLE_FULL_START=1 tests/test_playable_start_live.sh` with the same game-data paths and temporary Xvfb | PASS, all 12 checks | `playable-start-1791948565/verification.json`; launcher output in `starcraft-startup/full-start.log` |

The full startup log confirms extraction of 56 Marine and 136 Zergling frames,
selection of `starcraft-local`, regeneration of `g2.dat`, and installation of
that rebuilt pack. All 192 staged source frames match the extracted PNGs. Idle
Marine and Zergling sprites exported from the installed `g2.dat` match their
palette-quantized local source images pixel for pixel; the exported files are
`compiled-marine.png` and `compiled-zergling.png` in the run directory.
The reviewed `screen.png` shows StarCraft Marines and Zerglings, and the client
observed all 23 expected units. This verification checks artwork selection and
startup; the prior navigation tests above were not repeated for the asset change.
