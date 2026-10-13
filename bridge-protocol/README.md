# Bridge protocol v1

## Shared actor lifecycle

`world.v1` carries reliable OpenBW actor lifecycle operations alongside disposable
`combat.snapshot` state. OpenBW publishes `actor.spawn` with a canonical
`openbw:<number>` ID, type, owner, engine creation `generation`, and park
`session`. The ID and generation come from the native simulation and do not
depend on position. A repeated identical spawn is idempotent; a conflicting
identity or an ID reused after removal is rejected. Existing preplaced actor
IDs remain valid without a lifecycle announcement.

The publisher and controller each send `actor.bind` with the same canonical ID,
session and generation, their `participant` role, and their own BWAPI
`native_id`. Local native IDs may differ. The bridge acknowledges each binding
with `world.ack`; the actor becomes commandable only after both unique bindings
are recorded. Duplicate bindings are idempotent. A conflicting binding or a
native ID already assigned to another actor is rejected. Disconnecting a
participant clears that participant's bindings and suspends commands until it
rebinds. `actor.despawn` is published by OpenBW, invalidates both bindings,
and leaves an ID tombstone for the rest of the session. Repeated despawns are
idempotent; stale sessions and generations are rejected.

On publisher reconnect or bridge restart, OpenBW sends `actor.reconcile` with
the complete living identity set, then republishes its bindings. The bridge
keeps identical identities and bindings, removes missing actors, and rejects
duplicates or conflicting generations. A new park session starts a fresh actor
scope. The bridge forwards lifecycle announcements to the controller and
completed bindings and despawns to the park. Each lifecycle operation uses the
normal `world.v1` envelope, operation ID, session and `world.ack`. Park world
revision remains unchanged by actor movement or lifecycle; combat snapshots
continue to carry position, facing, animation and health.

Runtime OpenBW actors include `creation_frame` in both bindings. The publisher
assigns a generation token when it observes the native creation event. The
controller matches a single native creation with that synchronized frame,
owner, and unit type before it sends its binding. Multiple candidates remain
unbound and uncommandable. The test fixture can request one extra native Marine
by setting `BRIDGE_TEST_SPAWN_MARINE_FRAME` for a world session. OpenBW's
multiplayer `createUnit` queues one synchronized creation action and returns no
immediate unit handle; the adapter waits for the actual event.

On world snapshot replay, OpenBW marks `world.ready.resuming` after it has
previously reached native readiness in that simulation. The bridge then checks
current native unit counts against the original map units plus reconciled
runtime identities. Initial readiness still requires the configured starting
counts exactly. This lets the bridge restart after a native spawn or death
without treating changed unit counts as a corrupt starting map.

The OpenRCT2 server replicates completed bindings and despawns through
`rtsbridge.actorLifecycle`. Clients render and accept selection for runtime
actor IDs only after an active binding reaches this action. A newly loaded
client sends `rtsbridge.clientReady`; the server then replays active bindings
and the complete versioned structure target catalog. Duplicate replay actions
are idempotent.

Structure targeting uses `rtsbridge.targetCatalog` actions with `session`,
monotonic `version`, zero-based `index`, total `chunks`, and a bounded `targets`
array. Each client stages chunks in order and replaces its active hit-test
catalog only when the final chunk is accepted. A missing, repeated, stale, or
conflicting chunk cannot expose a partial update. The server resends a complete
catalog for a joining client when its plugin reports readiness, and on actual
target changes; it does not broadcast the full catalog on a timer.

The new startup world API is documented in [world.v1](world.v1.schema.json) and the [world bridge guide](../docs/world-bridge.md). It runs alongside the older disposable combat snapshot messages described below.

The publisher sends one UTF-8 JSON object per line over a TCP connection bound to `127.0.0.1`. Each line is a **full** snapshot, capped at 32768 bytes including the JSON but excluding the newline. A 32-unit packet with 32-byte IDs and signed decimal 32-bit coordinates fits under 8 KiB; the larger cap also accommodates combat targets and events. The [schema](units.snapshot.v1.schema.json) and [fixture](fixtures/one-unit.ndjson) define the original wire shape. Every receiver rejects an invalid array as a whole, including duplicate IDs.

`x` and `y` are OpenBW map pixel coordinates. The OpenRCT2 adapter alone converts them to park world coordinates. `facing` is one unsigned byte for a full circle: 0 is east, increasing according to the BWAPI angle after normalization. The adapter must calibrate the axis handedness before choosing a sprite frame.

`session` changes on each launcher run; `seq` starts at 1 for that session. Receivers reject stale or repeated sequence numbers within a session. `map_id` must match the configured park mapping. A snapshot with `units: []` removes all actors from the previous full snapshot. The server validates all fields and world bounds before issuing a synchronized OpenRCT2 action.

The first BWAPI module publishes on every third simulation frame. The resulting rate depends on the simulator's frame speed. This cadence is tied to `bw_tick`, so pausing the simulation does not generate repeated snapshots for the same tick.

Protocol v1 supports up to 32 actors. The default demo still publishes one Zergling; `BRIDGE_DEMO_UNITS=8` opts into the squad patrol.

## Ride siege snapshot v2

The separate [scenario snapshot v2 schema](scenario.snapshot.v2.schema.json) adds a `targets` array to the live actor snapshot. The current allowlist contains exactly `carousel-1` with a stable `proxy_unit_id`, `hp`, `max_hp`, and `intact`, `damaged`, or `destroyed` state. The bridge emits one full snapshot every third BW frame, including Zergling positions and the terminal destroyed state in subsequent packets. The server validates the session, monotonically increasing sequence and BW tick, stable proxy identity, and nonincreasing HP before coordinating one native ride demolition. The original v1 `units.snapshot` protocol and patrol demos remain available.

## Mixed faction combat snapshot v3

The [v3 schema](scenario.snapshot.v3.schema.json) carries a full snapshot of up to twelve Marines and Zerglings every third OpenBW frame, about 8 Hz at the default frame delay. Each unit has a stable ID, type, owner, position, facing, health, animation state, attack frame counter, and current target. A destroyed unit stays in the snapshot with `hp: 0`, `alive: false`, and `motion: "death"` for sixteen BW frames before despawning. The `events` array carries uniquely identified damage, attack frame, death, and carousel destruction observations; clients deduplicate them by ID. Attack frames are read from BWAPI, and damage and death are read from OpenBW state.

`targets` is empty for the battle feasibility map and contains the same allowlisted carousel proxy for `frontier-defense`. The publisher and server cap each line at 32768 bytes and reject malformed arrays, duplicate unit or event IDs, invalid positions, stale sequences, and retired sessions. Unit HP may increase through OpenBW regeneration; carousel HP must not increase. The carousel is demolished once by the OpenRCT2 server after the proxy reaches zero HP.

Marine commands travel from an authenticated OpenRCT2 player through a synchronized action, then over a separate loopback socket to the Terran BWAPI endpoint. The Terran controller checks unit ownership and target type and replies `accepted` or `rejected` with a reason. OpenBW alone moves the unit or applies damage. The supported local OpenBW transport synchronizes the Zerg and Terran endpoints; the Zerg endpoint publishes authoritative snapshots.

## Park assault snapshot v3

The same [v3 schema](scenario.snapshot.v3.schema.json) also defines `map_id: "park-assault"`. This variant supports the bridge ceiling of 32 actors and three or more independent targets. Its full snapshots carry `map_revision`; each target retains its stable logical ID, OpenBW proxy ID, health, and state even after destruction. The scenario configuration supplies the actual OpenRCT2 ride IDs, object identities, occupied tiles, and the shared coordinate transform. The server rejects duplicate actors or targets, stale sessions and sequences, HP increases, proxy identity changes, and a map revision ahead of confirmed demolition. Successful native ride demolition sends a short `nav <session> <revision> <target>` control line back to the OpenBW planner. It never clears a footprint before the host verifies demolition. The worst-case 32-actor, three-target, 64-event test packet fits below the 32768-byte transport ceiling; the measured live 20-actor packet is about 3.8 KiB.
