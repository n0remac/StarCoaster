# Medic, Depot, Factory, and Vulture milestone

## Playable result

Mt. Zergling supports player-placed Terran Supply Depots and Factories through
the existing StarCraft construction toolbar. A Depot changes native supply
capacity. A Factory trains Vultures; a Barracks trains Medics after a completed
Academy exists. OpenBW performs prerequisite, resource, supply, queue, energy,
healing, movement, and combat calculations. The bridge carries native state and
orders; OpenRCT2 owns placement, inspection, and rendering.

Firebats draw the classic directional FlameThrower frames while native attack
frames advance. Medics draw the classic healing-gun frames when native healing
raises an injured friendly organic unit's HP and consumes Medic energy. The
FlameThrower source image's fire remap is baked into the locally generated
OpenRCT2 sprite bank. All extracted game art stays in ignored local directories.

## Verification

| Command | Result | Local evidence |
| --- | --- | --- |
| `scripts/project.sh validate-scenario mt-zergling` | Passed | Scenario validation output |
| `scripts/project.sh test` | Passed: Go, 3 C++ tests, 101 Python tests (1 skipped), plugin checks | `run-data/next-milestone-offline.log` |
| `tests/test_medic_vulture_native_live.sh` | Passed 14/14: both OpenBW participants, Academy gate, Depot supply, costs, completion, healing HP and energy | `run-data/medic-vulture-native-1792244405/` |
| `tests/test_next_buildings_live.sh` | Passed: Depot and Factory placement, ordered revisions, native links, geometry | `run-data/next-buildings-live-1792243138/` |
| `tests/test_medic_vulture_gameplay_live.sh` | Passed 14/14: training, retry deduplication, actor binding, mixed orders, demolition, synchronization | `run-data/medic-vulture-gameplay-1792247069/` |
| `tests/test_next_buildings_save_load_live.sh` | Passed: both building types retain identity and HP after full engine reload | `run-data/next-buildings-save-load-1792247172/` |
| `tests/test_next_tech_bridge_restart_live.sh` | Passed 7/7: same session, four buildings, resources, Medic and Vulture actors and bindings | `run-data/next-tech-bridge-restart-1792249363/` |
| `tests/test_next_buildings_overlap_live.sh` | Passed: Depot and Factory occupied-geometry rollback | `run-data/supply_depot-overlap-live-1792247824/`, `run-data/factory-overlap-live-1792247879/` |
| `tests/test_barracks_production_live.sh`, `tests/test_firebat_production_live.sh`, `tests/test_academy_overlap_live.sh` | Passed | `run-data/barracks-production-live-1792247547/`, `run-data/firebat-production-live-1792247598/`, `run-data/academy-overlap-live-1792247766/` |
| `scripts/project.sh record --scenario mt-zergling --duration 180 --medic-vulture-probe` | Passed: 1,428/1,428 shared snapshots matched, zero mismatches, all focused checks true | `run-data/artifacts/20261017T145841Z-658e23f7e631/` |

The native feasibility probe checked Medic production with and without an
Academy, Vulture production at a Factory, a Depot's supply gain and removal,
native resources and queue completion, friendly organic healing, and rejection
of enemy and mechanical healing. Both OpenBW participants agreed. Healing
required an explicit BWAPI Healing order, so the existing command path gained
typed `unit.heal` with native validation.

## Graphical capture

The focused recording uses a real graphical OpenRCT2 client pair. It places
the buildings, trains the units through the building UI, orders a mixed squad,
triggers a Zergling wave, and records native healing and Firebat attacks.
`verification.json` reports shared snapshot agreement; frame captures and the
combined video permit visual inspection of the effects. The final capture is
`run-data/artifacts/20261017T145841Z-658e23f7e631/`. Both
`client-a-flame-frame04.png` and `client-b-flame-frame04.png` visibly contain
the directional orange FlameThrower burst during a Zergling fight; the
adjacent frame 03 has no burst. The flame bank's white and orange pixels were
also counted in both frame 04 screenshots (40 white and 196/176 orange),
confirming the extracted sprite was drawn. The paired
`client-a-heal-frame06.png` and `client-b-heal-frame06.png` show the Medic's
gold healing-gun flash. The capture log shows the Firebat's HP rising; the
native feasibility test verifies Medic energy use. The combined `combined.mp4` shows construction,
production, mixed orders, healing, and the wave fight.

## Scope and limits

Construction remains an OpenRCT2 scenery action: SCV build orders, StarCraft
construction costs, mining, and gas harvesting are outside this milestone.
Spider Mines and Medic abilities other than Healing are not exposed. A full
engine restart reconstructs buildings and prerequisites from the saved park;
active native production queues are not restored by that path. A Go bridge
restart while both engines remain running retains those native queues.
The pinned Vulture body GRP has one directional bank, so its OpenRCT2 body
rotates during movement and attack; a separate Vulture projectile overlay is
not rendered. Its weapon and damage remain native OpenBW behavior.
