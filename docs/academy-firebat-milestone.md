# Academy and Firebat milestone

## Playable path

Mt. Zergling now offers Barracks and Academy construction through the existing
StarCraft scenery catalog. The Academy occupies 3×2 park tiles, synchronizes
one completed native Terran Academy with 600 HP, and has a building inspection
window without production controls. Barracks offer native Marine and Firebat
training. The Firebat button reports the latest OpenBW availability reason;
OpenBW checks the command again when it executes. The scenario starts with
500 minerals and 250 gas. Both resources and supply are reported from OpenBW.

Completed Firebats use the shared actor identity, selection, orders, combat
snapshot, health bar, and lifecycle systems. Their independent sprite bank is
prepared from locally licensed StarCraft data. The installer creates both
large-scenery objects and installs the Marine, Zergling, and Firebat banks for
server and graphical clients. Extracted art and staged objects remain outside
Git.

## Verification

| Command or check | Result | Evidence |
| --- | --- | --- |
| Native Academy prerequisite probe | Pass: no Academy rejects Firebat; a completed Academy unlocks it; 50 minerals and 25 gas are charged; removal relocks it on both participants | `run-data/firebat-native-tech-1792216955/` |
| Native two-Academy probe | Pass: 2 → 1 Academies retains unlock; 1 → 0 removes it | `run-data/firebat-academy-count-1792221654/` |
| Native Firebat splash probe | Pass: one native attack damaged two Zerglings on the same frame on both participants | `run-data/firebat-splash-1792220863/` |
| Academy construction and recovery probes | Pass: one native Academy, 600 HP, save/load retained 372 HP and identity, reconstruction advanced generation; Go reconnect retained identity and HP | `run-data/academy-save-load-live-1792220077/`, `run-data/academy-bridge-restart-1792220446/` |
| Zero-gas native production probe | Pass: insufficient gas rejected without mineral charge | `run-data/firebat-insufficient-gas-1792220547/` |
| Academy occupied-geometry probe | Pass: both native participants rejected placement over a Marine; OpenRCT2 rolled back and restored the navigation hash | `run-data/academy-overlap-live-1792223440/` |
| Firebat production and mixed orders | Pass: two Firebats charged once each, duplicate request did not charge, all five selected Marines/Firebats moved in native snapshots | `run-data/firebat-production-live-1792223599/` |
| Go bridge restart during Firebat production | Pass: queued Firebat completed, resources and Academy prerequisite persisted, second Firebat trained, mixed orders and removal relock worked | `run-data/firebat-bridge-restart-1792223499/` |
| `scripts/project.sh validate-scenario mt-zergling` | Pass | Scenario validator |
| `scripts/project.sh test` | Pass: Go, 3 C++ tests, 99 Python tests (1 skipped), JavaScript | Offline suite |
| `scripts/project.sh test-live-construction` | Pass: all 15 live construction and objective cases | `run-data/live-construction-*/`, `run-data/live-objective-manual-1792224554/` |
| Barracks production, save/load, bridge restart, and overlap live scripts | Pass: existing Marine lifecycle, saved generation, reconciliation, and rollback behavior retained | `run-data/barracks-production-live-1792224590/`, `run-data/barracks-save-load-live-1792224642/`, `run-data/barracks-bridge-restart-1792224779/`, `run-data/barracks-overlap-live-1792224831/` |
| `python3 tests/test_marine_controls_live.py` | Pass: native movement redirect in 1,052 ms | `run-data/marine-controls-live-1792224889/` |
| `python3 tests/test_mt_zergling_gameplay_live.py` | Pass: park actions and four manual waves with valid routes | `run-data/mt-zergling-gameplay-live-1792224917/` |
| `scripts/project.sh record --scenario mt-zergling --academy-firebat-probe --duration 210 --video-layout combined` | Pass: all nine graphical Academy/Firebat checks; 2,008 of 2,008 shared snapshots matched | `run-data/artifacts/20261017T084015Z-e16b50b42148/` |

The two-client graphical capture at
`run-data/artifacts/20261017T084015Z-e16b50b42148/` passed all nine Academy
and Firebat checks: graphical placement and inspection, Firebat availability,
training, completion, mixed viewport selection and orders, combat, death
frames, and Academy demolition relock. Its combined video and staged
screenshots show the native game rendered in both clients. The capture matched
all 2,008 shared combat snapshots with zero mismatches. The test-only recorder
uses the ordinary player actions to place and inspect buildings, train a
Firebat, box-select a mixed squad, move and attack-move it, order the Marines
away after the first combat shot, request a Zergling wave, and demolish the
Academy. The Firebat died through normal native combat at 2 HP on both
participants. No native death hook was enabled in the final capture.

## Limits

The Academy is an OpenRCT2 park construction action; SCV construction and
native StarCraft building costs remain outside this milestone. Same-session
Go bridge recovery preserves active native production, but active queues are
not restored after a full native-engine restart. OpenRCT2 park saves retain
Academy scenery and HP for reconstruction; neither original StarCraft art
nor licensed game data is committed.
