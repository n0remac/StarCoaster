# Medic, Supply Depot, Factory, Vulture, and combat effects plan

## Starting point and boundaries

The shared type catalog currently contains Barracks, Academy, Marine, Firebat,
and Zergling. Barracks production, native availability, building identity,
ordered park patches, two-participant synchronization, actor bindings, and
licensed-art installation already exist. Reuse those paths. OpenRCT2 owns
construction and drawing; OpenBW owns prerequisites, supply, training, energy,
healing, movement, and damage. Do not simulate those rules in Go or JavaScript.

The current Firebat visual bank includes attack poses but does not draw a
separate flame effect. The combat snapshot carries attack-frame counts, not
native effects or healing state. A visible healing animation therefore needs
effect evidence from native OpenBW and an OpenRCT2 effect renderer.

Continue the established construction scope: players place buildings through
OpenRCT2, without SCV build orders or StarCraft construction costs. Native
training and supply rules remain fully authoritative. Keep the existing
scenario Supply Depot fixture as initial capacity unless a scenario change is
explicitly needed; a player-built Depot must add capacity exactly once.

## Phase 0: native feasibility and visual-source audit

Before adding gameplay types, run focused two-participant native probes using
the pinned engines and locally licensed data:

1. Create and remove a completed Terran Supply Depot. Record both players'
   native supply totals, including the case where units already use the extra
   capacity. Repeat with two Depots and with the Mt. Zergling fixture present.
2. Check `Terran_Medic.requiredUnits()`, the Barracks' `canTrain`, and native
   training before and after Academy creation/removal. Verify resource and
   supply charges, completion, and the two-Academy case.
3. Check Factory `canTrain(Terran_Vulture)`, native training, charges, queue,
   completion, and Factory removal. Test a Factory created through `Game::createUnit`,
   matching current construction. Distinguish producer mismatch from resources,
   supply, queue, and invalid building state.
4. Damage a friendly Marine or Firebat. Test Medic idle, follow, move,
   attack-move, hold, and direct heal behavior through the actual BWAPI order
   interface. Record target HP, Medic energy, order, and both participants'
   frame-by-frame agreement. Check that a Medic does not heal a mechanical
   Vulture or an enemy. Decide from this evidence whether an explicit
   `unit.heal` command is required in addition to automatic healing.
5. During a real Firebat attack and a real Medic heal, inspect native bullets,
   orders, sprite/image state, and frame timing. Resolve the classic flame and
   healing artwork via `images.dat`/`images.tbl` and inspect its GRP/iscript
   layout. In particular, do not assume that images named `Unused_Heal_*` are
   the visible Medic effect. Capture source-frame contact sheets and offsets
   under ignored `run-data/`.

Gate: both native participants agree on prerequisites, supply, healing, and
combat events. If the pinned engine lacks an expected behavior, document it
and make the smallest native correction before adding bridge-side behavior.
Commit the probes separately.

## Phase 1: catalog and constructible buildings

Add `terran_supply_depot` and `terran_factory` to
`bridge-protocol/starcraft-types.json` and the native mapping in
`WorldStarcraftTypes.h`; regenerate the Go and JavaScript definitions. Derive
footprints and maximum HP from the pinned native types, then verify them
against the scenery images. Depot has no production list; Factory produces
`terran_vulture`. Barracks gains `terran_medic` alongside Marine and Firebat.

Extend `scripts/install-starcraft-construction-object.py` with Depot and
Factory image profiles, reusing its metadata resolver and shared multi-tile
assembler. Extract original licensed art locally; inspect overlay frames,
rotations, preview size, and per-tile alignment. Stage every supported object
for the server and both graphical clients. Keep extracted art and `.parkobj`
files outside Git.

Use the existing construction toolbar and `largesceneryplace` action. Each
new object must pass park clearance, permissions, native occupied-geometry
checks, ordered world-patch synchronization, and generation-aware native
identity binding. Verify inspection, HP changes, demolition, reconstruction,
save/load, and Go bridge reconnect. Confirm the Depot's supply effect comes
from its single completed native building, and that demolition changes native
capacity. Keep the scenario fixture separate from a player-built Depot so
reconciliation cannot duplicate either.

Gate: placed Depot and Factory each correspond to exactly one correctly owned
native building on both participants, with correct footprint and HP. Commit
building catalog/lifecycle and artwork installer work in coherent increments.

## Phase 2: native production and actor control

Register `terran_medic` and `terran_vulture` as supported player actors. Use
the existing typed `unit.train` path and reusable native availability report.
The Barracks presents Train Medic; the Factory presents Train Vulture. OpenBW
performs the final `canTrain` and `train` checks and spends minerals, gas, and
supply. Display native availability reasons and current resources in the
existing UI. No local balances, timers, or duplicated tech rules.

Extend actor creation, canonical identity, participant binding, snapshots,
death, selection, movement, hold, stop, and recovery for both types. Verify
mixed Marine/Firebat/Medic/Vulture selection. Medic enemy attack clicks must
not become a fake damage order; route support behavior through native orders.
If the feasibility probe shows explicit healing is needed, add a typed
`unit.heal` command with friendly target validation and native order
execution, while keeping ordinary move and attack-move available. Vulture
movement and weapon behavior remain native. Spider Mines and Medic abilities
other than Healing are outside this increment.

Gate: Academy loss blocks new Medic orders, Factory loss blocks new Vulture
orders, duplicate requests do not charge or create units twice, and mixed
groups receive valid native orders on both participants. Commit production
and actor support separately.

## Phase 3: unit art and native-timed effects

Extend `scripts/prepare-starcraft-sprites.py` and
`scripts/install-bridge-sprites.py` with independent Medic and Vulture visual
banks. Inspect each actual GRP's frame count, directions, death art, offsets,
and any attached image layers. Register idle, walk, relevant action, and death
states in the OpenRCT2 visual registry without changing existing sprite IDs.

Add a small typed visual-effect stream or snapshot section sourced from native
events. For Firebat flames, use the native attack/bullet event and heading to
start the extracted directional flame frames at the correct muzzle and frame;
for Healing, use the native heal order and actual HP/energy activity to show
the extracted Medic effect at the correct unit and frame. Record source and
target actor IDs, position, native tick, effect kind, and a stable event ID so
reconnects and retries cannot duplicate effects. If BWAPI does not expose an
exact visual overlay, derive only the display timing from proven native state;
OpenBW still performs every damage and healing calculation.

Render effects with correct foreground/background ordering, tile invalidation,
rotation, and lifetime on both OpenRCT2 clients. Inspect still and frame-by-frame
captures of Firebat flame bursts, Medic healing pulses, Vulture attacks,
movement in several directions, overlap with park structures, and deaths.
Never accept an attack pose alone as proof of the flame, or HP recovery alone
as proof of the healing effect.

Gate: the actual flame and healing artwork appears during real native actions,
and both clients agree on the triggering state. Commit sprite preparation,
effect protocol, and renderer patches in reviewable increments.

## Phase 4: recovery, regressions, and graphical acceptance

Add focused native/live tests for Depot supply gain/loss, Factory and Medic
prerequisites, Vulture and Medic production, Medic energy and friendly-only
healing, new building identity/HP/save/load/reconnect, two-client agreement,
occupied-geometry rollback, duplicate commands, and effect event timing.
Test a Go bridge restart with native engines still running, then a full engine
restart from saved park state. Preserve the documented limit that active
queues are not restored after a full engine restart unless this is separately
implemented and proved.

Run `scripts/project.sh validate-scenario mt-zergling`,
`scripts/project.sh test`, affected `test-live-construction` cases, existing
Barracks/Academy/Firebat regressions, actor lifecycle and mixed controls, and
Mt. Zergling gameplay. Run live tests sequentially because they share ports.

Extend the existing `scripts/project.sh record` probe. In one real two-client
Mt. Zergling session, build a Depot and Factory, train a Vulture and Medic,
show the Depot changing supply, heal an injured Marine/Firebat with a visible
effect and measured native energy/HP change, show Firebat flame frames during
native splash combat, and move a mixed squad around scenery. Capture building
previews/inspection, availability changes, production charges, actor bindings,
native logs, frame-level effect screenshots, combined video, and
`verification.json` with zero shared-state mismatches. Keep captures ignored.

Finish with a milestone report listing each command's result, artifact paths,
and remaining limits. Do not call the visual effects verified based only on
headless tests or logs. Commit documentation separately.
