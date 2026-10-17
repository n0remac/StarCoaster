# Barracks reliability checkpoint

The park owns the visible Barracks and its stable ID. OpenRCT2 saves both the
large scenery object and its generation counter in park storage. The bridge
derives the same 4×3 collision footprint on each snapshot or ordered patch.
OpenBW owns the real Terran Barracks' current HP and the navigation mask. The
plugin stores the most recently reported native HP in park storage so a later
park save can seed native building recovery. A newly constructed Barracks has
1000 HP; old 40 HP proxy saves migrate proportionally.

## Occupied placement recovery

The plugin's cursor check uses the latest actor snapshot. A Marine can still
enter the site before the native patch applies. Both OpenBW participants check
the candidate mask at staging and at the scheduled application frame. If
either rejects the patch with `occupied_construction_geometry`, the bridge
cancels staging and reports the patch as unsynchronized. The plugin then
removes the exact Barracks footprint through OpenRCT2's normal large scenery
action, retrying a failed removal on later ticks. It does not publish a new
snapshot while that removal is pending. Once the scenery is gone, it sends a
full snapshot through the existing bridge protocol. A fresh placement at the
same site gets a new generation. If the park never permits removal, the
plugin remains paused and logs `WORLD_BARRACKS_ROLLBACK_ERROR`; an operator
must resolve that OpenRCT2 action failure before synchronization resumes.

Barracks owner is derived from the observed native Terran Marine owner when
available. Existing parks start with the current scenario's player 1 owner
until a Marine snapshot arrives. RCT2 construction permissions still decide
who may place or demolish scenery. Production requests require the connected
Terran commander in OpenRCT2 and the linked native Terran owner in OpenBW.

## Checks

| Command | Result |
| --- | --- |
| `scripts/project.sh test` | Passed: Go, C++, 87 Python tests (one skipped), and plugin JavaScript tests. |
| `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft tests/test_barracks_overlap_live.sh` | Passed: `run-data/barracks-overlap-live-1792195130/verification.json`. OpenRCT2 accepted scenery over a moving Marine, OpenBW rejected revision 2, the plugin removed it, and both participants returned to the original hash `6782e549dd7cb935` with 4254 entities. |
| `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft tests/test_barracks_save_load_live.sh` | Passed: `run-data/barracks-save-load-live-1792195203/verification.json`. A real `.park` save/load retained ID `openrct2:large_scenery:248:3200:3328:1216:0#1`, 1000 HP, real `Terran_Barracks` type, and mask `ee9230f1842ece7d`; demolition and reconstruction produced `#2`. |
| `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft tests/test_barracks_bridge_restart_live.sh` | Passed: `run-data/barracks-bridge-restart-1792195397/verification.json`. Go restarted with the same park session and revision 2; both native participants retained one `openbw:8` Barracks at 1000 HP. |

The save/load run starts fresh OpenBW processes; the bridge restart run keeps
both engines alive. Damaged-HP save/load still needs a dedicated live check.
The verified 1000 HP save/load case establishes identity, native recreation,
and navigation recovery, rather than restoration of partial damage.
