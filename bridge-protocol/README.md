# Bridge protocol v1

## Live park patches

`world.patch` is one bounded authoritative construction batch from the
OpenRCT2 server. Its envelope revision equals `result_revision`, which must be
`base_revision + 1`. The payload carries a stable `patch_id`, complete entity
additions and modifications, entity IDs to remove, terrain replacements, and
exact operation counts. Total operations are limited to 4,096 and one wire
envelope is limited to 1 MiB. A truncated or oversized envelope cannot stage
a partial patch. The plugin falls back to a full snapshot when a batch exceeds
the envelope bound. Retrying a patch uses the same ID and content.

The bridge validates the whole patch against the confirmed registry, applies
the scenario mapping to changed entities, and derives candidate navigation
before it acknowledges transport receipt. `world.ack` means the patch was
accepted for staging only. `world.patch.status` reports `staged`, `scheduled`,
`synchronized`, `failed`, or `unsynchronized` with the patch ID and candidate
navigation hash. Only `synchronized` advances the OpenRCT2 plugin's published
baseline. The bridge keeps one staged patch per session; a conflicting patch
is rejected. Duplicate committed IDs with identical content are acknowledged
idempotently. Native application and final synchronization are separate from
this receipt step. `world.patch.query` retrieves a pending or completed
patch's status after a lost acknowledgement. An unresolved staged patch expires
after 30 seconds and triggers snapshot reconciliation.

After both native navigation applications, the bridge sends
`world.patch.targets` to the publisher with mapped additions, modifications,
and removals at the committed revision. OpenBW accepts the target definitions,
then resolves asynchronous proxy creation and sends `world.targets.status`
with the patch ID, target count, and unsupported reasons. The bridge publishes
`world.patch.status: synchronized` only after that report. `entity.state`
supplies a native binding; the bridge sends `entity.target` to the park server
when a live binding becomes usable, refreshing the versioned multiplayer
catalog. Controlled proxy replacement first emits `entity.retire`. Manual
demolition retires its binding without a combat destruction event. Navigation
remains active when a combat proxy is unsupported or cannot be placed.
The final patch status also reports `unsupported_total` and
`unsupported_reasons`. Target definitions and navigation use separate native
acknowledgements; an accepted target request is not a usable proxy until its
asynchronous association and health restoration finish.

Manual removals retire canonical IDs without setting a combat destruction
flag. A manually removed required objective records a distinct durable
`objective_removed` defeat. Combat demolition retains its distinct
`combat.result` confirmation, then stages a synthetic `combat:<event ID>`
one-removal patch in the same ordered revision stream. The dead proxy retires
at park confirmation; geometry commits only after both native participants
apply the patch. OpenRCT2 queues later construction and command requests until
that combat revision synchronizes. An interrupted transaction recovers from a
new authoritative park snapshot rather than presenting receipt as completion.

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

When reconciliation removes an actor known to the bridge, the bridge forwards
the missed `actor.despawn` to both adapters. OpenRCT2 clears selection and
control-group references on that lifecycle action; its next full combat
snapshot removes the native render entry. Commands for a runtime ID are
rejected until both participant bindings are confirmed, and after removal.

Runtime OpenBW actors include `creation_frame` in both bindings. The publisher
assigns a generation token when it observes the native creation event. The
controller matches a single native creation with that synchronized frame,
owner, and unit type before it sends its binding. Multiple candidates remain
unbound and uncommandable. The test fixture can request one extra native Marine
by setting `BRIDGE_TEST_SPAWN_MARINE_FRAME` for a world session. OpenBW's
multiplayer `createUnit` queues one synchronized creation action and returns no
immediate unit handle; the adapter waits for the actual event.

## Runtime spawn requests (v0.3.1)

`unit.spawn.request` carries a session-unique `request_id`, `unit_type`, count
(1–5), park pixel `x`/`y`, `formation: "compact"`, and authenticated `player_id`.
It carries no native owner. The bridge transforms coordinates and sends one
`unit.spawn.execute` at a time to the authoritative OpenBW publisher. The
execute payload has the request ID, zero-based unit index, type, and native
pixel coordinates. A later `unit.spawn.status` reports each unit as `queued`,
`issued`, `created`, `ready`, `rejected`, `failed`, or `uncertain`; created units
have canonical `openbw:*` actor IDs. `ready` requires both native bindings.
Failures can leave a partly completed batch. `unit.spawn.query` retrieves a
known status and `unit.spawn.cancel` cancels units still queued.

The Go bridge journals requests and outcomes under `run-data/spawn-queue.json`
by default. An issued creation becomes `uncertain` after publisher disconnect
or bridge restart and is not blindly retried. Once native world reconciliation
completes, the bridge sends `unit.spawn.reconcile` for the unresolved request
and index. The publisher replays its terminal result, reports `uncertain` while
the native creation is pending, or reports `not_received` only when that
request/index was absent from its same-session command journal. Only the
explicit `not_received` report permits a new native issue. A repeated request
with the same ID and parameters returns its existing status; changed parameters
are rejected. The current queue admits 64 pending units, limits batches to
five, and defaults to at most 240 live Marines and Zerglings below the 256
actor snapshot ceiling. The player-facing path accepts Marines only; trusted
`spawn_waves` scenario requests use the same queue for Zerglings. Player and
scenario requests have distinct authorization contexts.

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

Terrain `height`, `water`, and path `base_height` are OpenRCT2 world Z units, not base-height steps. The optional `slope` contains the native surface slope encoding; omitted means flat for older fixtures. Legacy `ground_paths` accepts one ground-following path. The additive `path_layers` field preserves up to 16 paths at distinct heights or occupied quarters, including raised and subsurface layers. Each layer includes `base_height`, nullable `slope_direction`, `clearance_height`, and `occupied_quadrants`. A tile cannot mix legacy and layered fields. Raised paths do not create native walking routes; the bridge blocks ground cells only when the approximated path slab intersects the shared 32-Z-unit unit clearance. Subsurface layers remain metadata.

`geometry.rects` always describes the logical structure footprint used by combat and lifecycle code. Optional `collision.mode` selects `legacy` (including an absent mode), `height_aware`, or `conservative`. `legacy` projects the 2D footprint. `height_aware` projects only validated physical or explicitly approximated `volumes`; an intentionally empty list means no represented ground obstruction. `conservative` may use documented volumes or fall back to the logical footprint. Each volume has a half-open X/Y rectangle, a half-open `[base_z, clearance_z)` interval in OpenRCT2 world Z units, a rotated four-bit quadrant occupancy mask, and a `physical` or `approximate` classification. Construction clearance is not automatically a solid collider. The bridge alone derives the native 8-pixel mask. See the [geometry contract](../docs/height-aware-navigation-contract.md) for supported types, boundaries, and fallbacks.

`navigation.mask.begin/chunk/end` transfers the bridge's single packed 8-pixel blocked-cell mask to each OpenBW participant. Bits are ordered by row, least-significant bit first; chunks contain up to 6,000 bytes encoded as lowercase hex. The 16-character hash is FNV-1a 64-bit over the packed bytes. Both participants respond with `navigation.mask.applied` only after native VF4 and path regions accept the exact mask. `world.ready` requires matching applied hashes. A nonzero `apply_frame` schedules a synchronized update after confirmed demolition; the new full mask retains permanent terrain barriers.

For live construction, `navigation.mask.begin` has `stage_only: true`. Each
participant validates the complete candidate and reports `navigation.mask.staged`
with its current simulation frame. When the hash is unchanged, the bridge sends
`navigation.revision.stage` instead of mask bytes. The bridge chooses a future
frame from both observed frames and elapsed staging time, then sends
`navigation.mask.schedule` to each participant. Both report
`navigation.mask.scheduled`; only a successful `navigation.mask.applied` at the
same requested frame and hash on both sides lets the bridge commit the Go
candidate and publish `world.patch.status: synchronized`. Late scheduling,
occupied new collision cells, or native application failure leaves the world
unsynchronized and triggers authoritative snapshot recovery. This path keeps
the OpenBW match and actor identities alive. `navigation.mask.cancel` clears
an unresolved staged or scheduled mask by revision and hash on both native
participants. A full snapshot mask supersedes older native staging during
recovery, including after a Go-only restart. A native proxy destroyed while
the bridge is disconnected is replayed after same-session reconciliation;
the old zero-HP target is not recreated at full health.

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

## Native Barracks production

A confirmed `terran_barracks` structure keeps its OpenRCT2 scenery ID and
`#generation`. `entity.state` links that ID to the real OpenBW Barracks native
unit and HP; there is no civilian target proxy. The controller receives the
same link. `building.state` flows from the controller through Go to the park
with `id`, `native_id`, `owner`, `health`, `queue`, `remaining_frames`,
`minerals`, `supply_used`, and `supply_total`. The optional `max_health` field
reports the native building maximum. It is observational native state, not a
second production queue. `player.resources` separately reports the native
owner's minerals and supply, even when no production building exists.

`combat.command` also accepts `verb: "unit.train"` with an empty `unit_ids`
array, a supported `unit_type`, and a persistent production building
`target_id`. Existing world.v1 requests without `unit_type` explicitly default
to `terran_marine`. OpenRCT2 authenticates the commander and deduplicates the
session/player/request ID. Go requires a live, linked registered producer in
the confirmed registry; the controller verifies the native owner, completion,
and BWAPI `canTrain` before invoking `train` with the requested native type.
The existing `combat.result` reports acceptance. Native trainee creation is
withheld from `actor.spawn` and `actor.bind` until completion; the normal actor
lifecycle then exposes the Marine to both clients. A demolition uses the
ordered `world.patch` removal path and invalidates production.
