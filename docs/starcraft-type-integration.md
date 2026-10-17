# StarCraft type integration

The supported type catalog is `bridge-protocol/starcraft-types.json`. It lists
only types that StarCoaster can synchronize and render. BWAPI's full type
catalog is broader and does not automatically become playable. Run
`python3 scripts/generate-starcraft-types.py` after changing the catalog;
`--check` verifies the generated Go and plugin definitions plus native type
resolution. Do not put prices, supply costs, build times, or technology rules
in the catalog. OpenBW owns those rules.

## Add a building

1. Add a stable ID, BWAPI name, scenery object ID, display name, footprint,
   production list, and optional animation to the catalog. A future Supply
   Depot would declare its own footprint and scenery ID; this milestone does
   not register or place one.
2. Add the native BWAPI mapping in
   `openbw-bwapi-module/src/WorldStarcraftTypes.h`. The existing target
   lifecycle creates or recovers the declared native type. Ordinary rides and
   scenery remain neutral target proxies.
3. Add an art preparation function and `BUILDING_OBJECTS` entry in
   `scripts/install-starcraft-construction-object.py`. The shared archive
   assembler handles tile layout and image banks. Preserve image indexes for
   existing objects; the Barracks has four preview images followed by 48
   images per frame and an eight-frame light-only training bank. Optional
   `animation` metadata declares a training trigger, frame count, and ticks
   per frame; the native renderer tracks animated tiles by scenery object.
4. Install the object on both OpenRCT2 clients through the normal local asset
   workflow. The plugin's construction catalog, placement footprint,
   recognition, and inspection window read the generated definitions.

## Add a unit

1. Add the stable ID, BWAPI name, race, ownership, visual ID, commands, and
   display name to the catalog. Marine, Zergling, and Firebat are currently
   registered. Firebat production declares the Barracks as producer and uses
   OpenBW's native Academy requirement.
2. Add BWAPI resolution in `WorldStarcraftTypes.h`. Mark the unit controllable
   only if both the native controller and plugin can issue its intended
   commands. Runtime actors receive canonical IDs from native creation events
   after completion. Static Marine and Zergling positional IDs remain stable.
3. Add a sprite preparation profile in `scripts/prepare-starcraft-sprites.py`.
   Frame groups, directions, timing, and death poses belong to that profile;
   they need not match the Marine. Add a bank in
   `scripts/install-bridge-sprites.py` and a visual mapping in the native
   OpenRCT2 renderer patch. `--only-unit` stages one existing unit bank without
   reading the other unit's source images.
4. If a building produces it, add its ID to that building's production list.
   The plugin makes a button and sends `unit.train` with `unit_type`.
   OpenRCT2 checks player authority and request shape, Go checks the confirmed
   building link and supported producer/unit pair, and OpenBW calls BWAPI
   `canTrain` and `train`. BWAPI decides costs, supply, requirements, queue
   capacity, and timing. Missing `unit_type` in world.v1 means Marine for old
   callers.

## Lifecycle and verification

The park owns visible scenery and persistent IDs. The bridge links a confirmed
park structure to a native building and forwards its HP and queue. OpenBW owns
native creation, combat, production, destruction, and player resources.
Demolition retires the native building; native destruction follows the ordered
park removal process. Save/load and bridge reconnection reuse links and
restore HP. A trainee is not selectable until BWAPI reports completion and
both native participants bind the actor. Retried commands retain their
session and command IDs so the same request cannot train twice.

Run `scripts/project.sh test` for every catalog or pipeline change. For a new
building, add registry, object layout, native lifecycle, overlap, demolition,
save/load, and bridge restart checks. For a new unit, add sprite layout,
spawn, actor identity/binding, movement, death, reconciliation, and production
checks. Run focused licensed live checks and a two-client recording before
claiming graphical behavior. Local extracted sprites, game data, captures,
and engine builds remain under ignored paths and must not be committed.
