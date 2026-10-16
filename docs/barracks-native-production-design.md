# Native Barracks production discovery

## Verified behavior in the pinned engines

OpenBW supports a functional Terran Barracks. In a two-participant Mt. Zergling
run, a test-only BWAPI `Game::createUnit` call for Terran player 1 created the
same completed 1000 HP Barracks in both participants. A synchronized grant of
500 minerals and one test Supply Depot changed supply from 10/0 to 10/16.
`Unit::train(Terran_Marine)` then returned true, deducted 50 minerals, reserved
two half-supply units, and started a 360-frame native queue. The Marine became
complete at frame 809 after the queue began near frame 449. It was assigned
the shared actor ID `openbw:3001` and bound in both participants. Evidence is
in `run-data/barracks-native-completion-1792192837/server.log`.

`Unit::train` cannot succeed in the current scenario without setup: the
Terran player starts with zero minerals and no supply provider (10/0 supply
with five initial Marines). The Barracks itself supplies no capacity. A Marine
requires a completed Barracks, 50 minerals, free supply, and an available
queue slot. OpenBW enforces these in `unit_can_build`, `build_queue_push`, and
the normal train action; no independent resource or production simulation is
needed.

Native placement at the saved park Barracks position initially failed even
though BWAPI reported walkable and buildable ground. Diagnostics in
`run-data/barracks-native-trace3-1792192609/server.log` found OpenBW's
`can_place_building` rejecting unexplored Terran tiles (`explored=255`, owner
mask 2). This affects an ordinary StarEdit `Game::createUnit` action at a park
site outside native Marine vision. A temporary local diagnostic change that
skipped only that fog check let the real Barracks appear at the exact saved
park coordinates on both participants while the park navigation mask remained
active; see `run-data/barracks-native-mask-probe-1792192984/server.log`.
Patch `0005-editor-building-fog-openbw.patch` now makes the pinned engine's
editor placement path ignore fog while preserving ordinary SCV construction.

OpenBW emits the new Marine's creation event when training starts, while the
unit is incomplete and has only partial HP. The existing actor registry
published and bound `openbw:3001` near frame 448, roughly 360 frames before
completion. A production integration must defer actor registration until
`Unit::isCompleted()` on both participants. The first local change for this
is in the adapter/controller; its live regression remains pending.

## Authority and lifecycle

| Responsibility | Authority |
| --- | --- |
| Placement, visible scenery, saved generation | OpenRCT2 |
| Ordered placement and removal revision | Go world bridge |
| Building HP, destruction, queue, Marine creation | OpenBW |
| Park ID to native unit link, request deduplication | Go world bridge |
| Construction and train controls | OpenRCT2 plugin |

The existing civilian target proxy must be replaced for a Barracks. Keeping
it alongside the native building produces two HP sources and two native
obstacles. The publisher adapter can create the real Barracks for the entity's
native Terran owner during the existing target-reconciliation step, which
already follows confirmation of both navigation participants. It can report
the real native unit ID and HP using `entity.state`; the controller can find
that synchronized unit and issue `Unit::train`. A snapshot or retry must first
search for the same owner/type/position before creating anything, then bind
the persistent park ID and generation to the observed native ID. Demolition
must retire the native building through the same ordered `world.patch` path.

The park-derived 4×3 mask remains the pathfinding authority before native
creation. The exact-site experiment showed that the native building can be
placed over that mask after the fog check is bypassed. Navigation after
creation, combat demolition, and removal still need live verification to
exclude duplicate obstacle effects. A reliable train request also needs a
server-validated RCT2 commander, an idempotent request ID, native owner and
operational-state checks, and a status query for retries. The information
window should read queue and HP reports from OpenBW rather than keeping its
own production state.

## Current production gate

Native training is supported and the real building lifecycle is wired. The
scenario still lacks Terran minerals and supply, and the player-facing train
request and queue status are not yet wired. The native test fixtures prove
engine mechanics; they do not make the Train Marine control functional. The
production tab remains disabled until command, status, and retry checks pass.
