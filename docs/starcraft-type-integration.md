# StarCraft type integration

`bridge-protocol/starcraft-types.json` declares the playable types. Its IDs are
stable wire IDs; order in the file never determines actor identity. Marine and
Zergling retain their legacy static identity bases. Runtime units receive
canonical IDs from native creation events after completion. OpenBW remains
authoritative for health, costs, supply, prerequisites, queues, movement,
damage, and abilities.

`bridge-protocol/starcraft-visuals.json` holds only art and rendering metadata:
GRP sources, image IDs, directional banks, timings, anchors, optional layers,
health-bar placement, and building art methods. The generator validates that
each registered type has a representable profile. Local extraction verifies
the original GRP against pinned StarCraft image metadata when an image ID is
declared.

## Add a conventional ground unit

1. Add a unit to `starcraft-types.json` with its stable ID, compile-time BWAPI
   type, race, ownership, visual ID, supported commands, and capabilities.
   Set `legacy_static_base` to zero for a new runtime actor. Add its ID to the
   native producer's `production` list. These fields declare support; they do
   not grant a new gameplay ability or override BWAPI's requirements.
2. Add a visual profile under `units` in `starcraft-visuals.json`. Provide the
   source GRP, expected dimensions and frame count, frame banks, animation
   timing, bounds, and health-bar offset. Idle and death are required. A state
   can name a deliberate fallback, as Vulture walk does. Independent art,
   such as Goliath's turret, belongs in `attachments`. `native_target` facing
   uses the target coordinates reported by OpenBW; without a target it uses
   the body's facing. Effects such as Firebat flame remain separate profiles.
   Assign a new, higher `g2_order` to keep earlier sprite banks stable even if
   catalog entries are rearranged.
3. Run `python3 scripts/generate-starcraft-types.py` and then `--check`.
   This updates Go, JavaScript, direct BWAPI C++ mappings, and the supported
   unit lists in the wire schemas. No handwritten C++ type mapping is needed.
4. Run `python3 scripts/prepare-starcraft-sprites.py --unit <asset>` with
   locally licensed StarCraft archives. The profile-driven extractor emits
   exact-palette PNGs and an ignored manifest under `run-data/generated-assets`.
   `scripts/install-bridge-sprites.py` adds a deterministic G2 bank, validates
   the manifest, and generates the OpenRCT2 paint descriptors. It preserves
   the existing Marine, Firebat, Medic, Vulture, Zergling, and flame IDs.
5. Build and test. `scripts/project.sh start` discovers every registered unit
   and effect asset, prepares it, and builds the generated registry. Missing
   licensed artwork fails explicitly. `BRIDGE_SPRITE_SOURCE=alien-scout` is the
   explicit placeholder option.

The Factory and Goliath are the worked example: the Factory's production list
includes `terran_goliath`; OpenBW requires a completed Armory and charges 100
minerals, 50 gas, and four raw supply units. Goliath has independent body and
turret GRPs. Its turret uses the reusable target-facing attachment layer and
the body uses the shared actor lifecycle, controls, and combat snapshot.

## Add a conventional building

1. Add its stable type ID, BWAPI type, scenery object ID, display name,
   footprint, maximum HP, and production list to `starcraft-types.json`.
2. Add a matching building-art profile to `starcraft-visuals.json`: native
   image ID, expected source dimensions and frame count, output size, preview
   layout, and supported art method. `static` uses the shared object assembler;
   `barracks_lights` preserves the Barracks' existing training light bank.
3. Generate definitions, run
   `scripts/install-starcraft-construction-object.py <data-root> --all`, and
   build. The toolbar, placement footprint, native building lifecycle,
   inspection, and production buttons use generated metadata. An empty
   production list has no Train controls.

Terran Armory is the worked example. Its source image resolves through
`IMAGEID_Armory` to `unit/terran/chemlab.grp`; the shared assembler creates a
3×2 object from its first static frame. Native BWAPI provides its 750 HP and
the Factory's Goliath prerequisite. The object ID is stable across saves.

## Verification and capability limits

Run `python3 scripts/generate-starcraft-types.py --check`,
`scripts/project.sh test`, and the relevant native tests before a two-client
graphical capture. `tests/test_goliath_native_live.sh` probes the pinned
Factory/Armory prerequisite on both OpenBW participants.
`tests/test_armory_goliath_gameplay_live.sh` drives real park placement,
training, binding, movement, and combat. Use
`scripts/project.sh record --scenario mt-zergling --armory-goliath-probe
--duration 180` for two graphical clients and ignored video and screenshots.
Inspect the rendered frames and `verification.json` before claiming visual
success. Never commit extracted graphics, licensed data, builds, or captures.

A genuinely new mechanic still needs a reusable native capability and wire
contract. The current ground-actor pipeline does not support air navigation,
transports, siege or morph modes, specialized spells beyond Medic healing,
resource collection, non-Terran construction economies, or full native
production-queue persistence after an engine restart. The bridge does not
simulate any of these StarCraft rules. Packaged starting armies and wave
objectives still use the Marine/Zergling scenario format; a new scenario
spawn type needs a backward-compatible scenario format and an explicit
`spawnable` declaration.
