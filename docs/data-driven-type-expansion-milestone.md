# Data-driven StarCraft type expansion

The supported-type catalog now generates Go, JavaScript, direct BWAPI C++
registrations, and wire-schema unit enumerations. `starcraft-visuals.json` declares
source images, frame banks, direction mappings, anchors, render bounds, building
art, and stable G2 bank order. The OpenRCT2 painter consumes generated visual
descriptors. New conventional ground units no longer need a handwritten painter
branch or a new `SpriteIds.h` entry. Firebat flame and Medic healing remain
specialized effect renderers; neither implements gameplay damage or healing.

## Armory and Goliath proof

- Terran Armory uses the original local StarCraft image resolved through
  `IMAGEID_Armory`. The shared assembler creates its 3×2 large-scenery object.
  Native OpenBW reports 750 HP. Save/load retained its park ID, native link,
  damaged 427/750 health, and navigation hash; demolition and rebuilding
  advanced the generation. A same-session bridge restart reused the native
  building at 427 HP. In a separate live variant, a Zergling wave reduced a
  35-HP Armory to zero. The ordered combat-demolition patch removed it from
  the park and relocked future Goliath training.
- Factory production lists Goliath from the catalog. The UI test confirms its
  button displays the native `Requires Armory` reason and enables when the
  native availability report changes. The live controller rejected training
  without Armory, accepted it after construction, and charged 100 minerals,
  50 gas, and four raw supply units. A duplicate request made no second charge.
- The completed 125-HP Goliath received one canonical actor ID and bindings
  on both OpenBW participants. Mixed movement and native attack orders worked.
  The live park run recorded an attack frame and Zergling HP loss. Armory
  demolition relocked future Goliath training.
- Goliath's body and turret come from separate local GRPs. Its turret uses the
  reusable target-facing attachment layer. Existing sprite IDs remain stable;
  its additional banks are appended in catalog-defined `g2_order`.

## Implementation commits

| Phase | Commits | Main files |
| --- | --- | --- |
| Catalog and native feasibility | `fd4d4a6`, `5344c98` | `starcraft-types.json`, type generator, generated Go/C++/JS and schemas, native prerequisite probe |
| Declarative art and rendering | `0c1fd3d`, `886c17d`, `2ae7678` | `starcraft-visuals.json`, sprite preparation and installer, building-object assembler, OpenRCT2 visual registry patches |
| Armory/Goliath and startup | `95d602b`, `9e80847`, `020c16c` | type catalog, `start.sh`, `project.sh`, native actor-capacity handling |
| Live gameplay, recovery, and capture | `80ebebf`, `77da546`, `db0fbf7`, `3450319`, `02465db`, `2a034ff`, `9766b11` | live probes, save/load and bridge-restart tests, recorder, UI test, generic native HP fixture, combat destruction |
| Regression fixes and documentation | `437acb3`, `4ecbc14`, `643eb28`, `24fde1b`, `5747767`, `f06aecf` | Firebat and actor test timing, Medic/Vulture script mode, workflow and milestone reports |

## Verification evidence

| Check | Result | Local evidence |
| --- | --- | --- |
| `python3 scripts/generate-starcraft-types.py --check` | Pass | Generated definitions agree |
| `scripts/project.sh test` | Pass | Go, three C++ tests, 103 Python tests (one skip), JavaScript plugin tests |
| `BRIDGE_SPRITE_SOURCE=starcraft-local scripts/project.sh build` | Pass | OpenRCT2 and native Bridge module built with original local art |
| `scripts/project.sh validate-scenario mt-zergling` | Pass | Scenario configuration valid |
| `scripts/project.sh test-live-construction` | Pass, 15 scripts | `run-data/type-expansion-live-construction.log` |
| `tests/test_goliath_native_live.sh` | Pass, 14 checks | `run-data/goliath-native-1792256508/` |
| `tests/test_armory_goliath_gameplay_live.sh` | Pass, 13 checks | `run-data/armory-goliath-gameplay-1792253495/` |
| `tests/test_armory_save_load_live.sh` | Pass with 427 HP | `run-data/armory-save-load-live-1792255067/` |
| `tests/test_armory_bridge_restart_live.sh` | Pass with 427 HP | `run-data/armory-bridge-restart-1792255162/` |
| `tests/test_armory_combat_destruction_live.sh` | Pass, 13 checks | `run-data/armory-combat-destruction-1792257398/` |
| Academy save/load and bridge restart regressions | Pass | `run-data/academy-save-load-live-1792256721/`, `run-data/academy-bridge-restart-1792253180/` |
| `node tests/test_barracks_plugin.js` | Pass | Armory menu and Factory Goliath control assertions |
| `python3 -m py_compile scripts/record-scenario.py`; `node --check scripts/armory-goliath-camera.js`; `node --check scripts/live-armory-goliath-probe.js`; `node --check scripts/live-firebat-gameplay-probe.js` | Pass | Capture and live-probe syntax |
| Barracks, Academy, Firebat, Medic/Vulture, and actor lifecycle regressions | Pass after test timing and file-mode fixes | `run-data/type-expansion-regressions/`, `run-data/firebat-production-live-1792255818/`, `run-data/actor-lifecycle-1792256373/` |
| Firebat zero-gas and native technology probes | Pass | `run-data/firebat-insufficient-gas-1792256565/`, `run-data/firebat-native-tech-1792256623/` |
| Two-client graphical recording | Pass | `run-data/artifacts/20261017T161643Z-1a7b92f39a4b/` |

The graphical artifact contains `combined.mp4` (179 seconds), screenshots at
11 points per client, logs, and `verification.json`. I inspected the Armory,
Factory, and Depot at four park rotations, the Goliath body and turret, its
health bar, navigation among trees, and a combat frame with Zerglings. The
verification file reports 1,463 matching shared snapshot sequences and no
mismatches. The recording driver issued the same authenticated training action
as the Factory button; the button itself was exercised by the JavaScript UI
test, not by a mouse click in the video.

The specialized live commands passed individually after the harness fixes:

- `tests/test_barracks_production_live.sh`,
  `tests/test_barracks_save_load_live.sh`,
  `tests/test_barracks_bridge_restart_live.sh`, and
  `tests/test_barracks_overlap_live.sh`.
- `tests/test_academy_construction_live.sh`,
  `tests/test_academy_overlap_live.sh`,
  `tests/test_academy_save_load_live.sh`, and
  `tests/test_academy_bridge_restart_live.sh`.
- `tests/test_firebat_production_live.sh`,
  `tests/test_firebat_splash_live.sh`,
  `tests/test_firebat_academy_count_live.sh`,
  `tests/test_firebat_bridge_restart_live.sh`,
  `tests/test_firebat_insufficient_gas_live.sh`, and
  `tests/test_firebat_native_tech_live.sh`.
- `tests/test_medic_vulture_native_live.sh`,
  `tests/test_medic_vulture_gameplay_live.sh`,
  `tests/test_actor_lifecycle_live.sh`, and
  `tests/test_goliath_native_live.sh`.

Their per-command logs and the initial failures are under
`run-data/type-expansion-regressions/`; final passing Firebat and actor
lifecycle artifacts are listed in the table. `scripts/project.sh
test-live-construction` completed all 15 construction regressions with exit
code zero. The final `scripts/project.sh test` rerun passed after all test
changes. JavaScript and Python syntax checks for the new recording/probe
scripts also passed.

The first graphical capture exposed a probe timing race before the Factory's
native state reached the plugin. A later recording process was interrupted
before finalization. The synchronized-state gate fixed the timing race, and
the completed recording above passed. The pre-Academy Firebat probe had the
same timing assumption; it now waits for the Barracks' native state. The Medic/
Vulture native script was missing its executable bit. The actor lifecycle
checker assumed the second client always saw the pre-spawn roster, although a
late join can begin at seven units. Those test harness issues were fixed and
all three checks passed on rerun.

An initial OpenRCT2 build was interrupted by edits to a patch source while
the linker ran; the clean rebuild and later `project.sh build` both passed.
Early headless Armory/Goliath probe revisions failed their checker before the
final synchronized-state and whole-wave damage checks passed twice. The first
combat-destruction variant expected a Marine attack, but native Zerglings
destroyed the low-HP Armory first; its final checker follows the observed
native death and ordered park removal, and the complete command passed.

## Current limits

The shared actor path covers conventional ground units. Air movement,
transports, siege or morph modes, specialized spells, harvesting, and
non-Terran construction still need reusable capabilities. Packaged scenario
starting armies and wave objectives retain their Marine/Zergling format.
Full native engine restart reconstructs supported buildings from park state;
active production queues do not persist across that restart. Licensed source
graphics, extracted sprites, engine builds, and captures remain outside Git.
