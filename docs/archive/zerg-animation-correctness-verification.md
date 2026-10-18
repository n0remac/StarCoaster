# Zerg sprite animation correctness verification

Implementation commit: `8967758`. The authored declarations were checked against
`scripts/iscript.bin` from the local `Patch_rt.mpq`, with image-to-script IDs from
`arr/images.dat` in the local `BrooDat.mpq`. The pinned OpenBW opcode table was
used to trace the original play-frame commands. The scripts are Zergling 31,
Hydralisk 18, and Ultralisk 29.

| Unit | Idle bank | Walk banks | Attack banks | Death GRP frames |
| --- | ---: | --- | --- | --- |
| Zergling | 5 | 6–11, 5 | 0–4, 5 recovery | 289–295 |
| Hydralisk | 5 | 6–11, 5 | 0–4, 3–0 recovery, 5 idle | 204–211 |
| Ultralisk | 9 | 0–9 | 14, 13, 12, 11, 12, 13, 14 | 255–264 |

The renderer loops live motions and holds the last death pose. The declarations
use one renderer tick per Zergling and Hydralisk walk or attack pose, two for
the Ultralisk attack, and two for each death pose. The original `iscript` waits
are one tick for the first two units and two ticks for the Ultralisk attack and
all three deaths. Old, unused G2 paths remain generated for compatibility.

## Verification

| Command or check | Result |
| --- | --- |
| `python3 scripts/generate-starcraft-types.py --check` | Passed |
| `python3 scripts/prepare-starcraft-sprites.py --unit {zergling,hydralisk,ultralisk}` | Passed for each unit |
| `BRIDGE_SPRITE_SOURCE=starcraft-local scripts/apply-openrct2-patches.sh` | Passed; installed sprites and regenerated the native visual registry |
| `python3 scripts/zerg-animation-contact-sheets.py` | Passed; 12 PNGs generated |
| `scripts/project.sh test` | Passed: Go, C++, 115 Python tests (one skipped), and plugin checks |
| `BRIDGE_SPRITE_SOURCE=starcraft-local scripts/project.sh build` | Passed |
| `BRIDGE_SPRITE_SOURCE=starcraft-local scripts/install-openrct2-local.sh` | Passed |
| `tests/test_world_live.sh` | Passed; two clients agreed after native carousel removal |
| `tests/test_unit_spawn_zerg_live.sh` | Passed; Zergling movement and attack on two clients |
| `tests/test_actor_lifecycle_live.sh` | Passed twice; combat, death, reconnect, and bridge restart |
| `scripts/project.sh record --scenario frontier-outpost --duration 110 --video-layout combined --mixed-zerg-camera --mixed-zerg-heavy-defense` | Passed |

The original 1,092 G2 paths retained their exact indices; the path prefix SHA-256
is `4904158f6f070aea1d855f36c807a5fe868b68d4c6c4ba6440425325514991dc`.
The regenerated table has 1,219 entries. No entity IDs or combat code changed.

Local contact sheets are in
`run-data/artifacts/zerg-animation-contact-sheets/`. The two-client video is
`run-data/artifacts/20261018T000219Z-0e19a6ae83d9/combined.mp4`, with its
`verification.json` alongside it. The 109.6-second, 1920 × 600 video records
all three Zerg kinds attacking and dying. The capture report records 579
matching snapshot sequences, no mismatches, both camera angles, and native
Hydralisk and Ultralisk damage samples. Sampled video frames show attack
motion near 35 seconds and death art near 65 seconds.

These ignored local artifacts contain licensed game art and are not committed.
The full `scripts/project.sh test-live` suite was not run; the focused native
combat, actor lifecycle, and two-client synchronization checks above passed.
