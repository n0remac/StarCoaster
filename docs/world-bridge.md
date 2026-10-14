# Packaged world bridge

`world.v1` is the generic startup path. It discovers the loaded OpenRCT2 park on the authoritative server, transfers a complete revisioned snapshot through the Go bridge, and creates OpenBW target proxies at a simulation frame boundary. It uses a reusable 256×256 OpenBW base map. Parks up to 256×256 tiles retain 1:1 horizontal coordinates and are centered with offsets `(256-width)/2` and `(256-height)/2`, rounded down. Larger parks fail explicitly. Frontier Outpost, Example Defense, and Midway Junction use this one runtime path.

## Start

Build and launch a package through the developer CLI:

```bash
scripts/project.sh start --scenario frontier-outpost
scripts/project.sh play example-defense
```

`scripts/scenario_package.py` resolves the package and prepares its park and
native map; `scripts/run-world-session.sh` starts the common runtime. It sets
`BRIDGE_SCENARIO=world` for the native module. Its Zerg and Terran human slots
run synchronized BWAPI adapters; a third computer slot owns park targets so
either faction can attack them. The Go service listens on loopback ports 40010
for the OpenRCT2 server plugin, 40011 for the OpenBW publisher, and 40012 for
the Terran unit controller. The native actor renderer receives synchronized
snapshots on both OpenRCT2 clients.

For a native size and capacity check, run `STARCRAFT_DATA_DIR=/path/to/StarCraft python3 tests/test_world_256_native_live.py` after building the patched engines. The probe loads both OpenBW participants, moves a Marine near the far edge, and applies a 65,536-tile blocked mask. Its ignored `run-data/world-256-native-*/verification.json` records the observed position and mask initialization time. The mask uses shared immutable VF4 variants, so confirmed demolition can restore the original tile index without consuming one variant per blocked map tile.

Terrain heights use OpenRCT2 world Z units: one `baseHeight` step is 8 units and one land slope step is 16 units. Each `world.v1` terrain cell carries its base `height`, raw surface `slope`, `water`, `surface`, and `walkable` values. `ground_paths` records the path base height and nullable native slope direction on the same tile. A missing `slope` or `ground_paths` in an older flat fixture means flat ground without a path. OpenRCT2's slope bits determine four quarter heights in north, east, south, west order; shared edge quarters must agree for a connected route. A flat 16-unit height difference is a cliff, while a side slope can join those heights. Water blocks traversal. Ambiguous diagonal slope values and path surfaces that do not follow the ground are reported as `unsupported_terrain`; overlapping path layers are outside this milestone.

After regenerating Frontier, `RCT2_DATA_DIR=/path/to/RCT2 python3 tests/test_terrain_export_live.py` compares the plugin's full saved-park terrain snapshot with OpenRCT2's exported tile elements. The verification JSON and OpenRCT2 log remain under ignored `run-data/terrain-export-*/`.

`BRIDGE_MAX_TARGETS` controls attempted native proxies (default 512, accepted range 1–1500). This is an attempt limit, not a guarantee that every placement succeeds. `BRIDGE_DISABLE_ASSAULT_AI=1` pauses the example Zergling controller for isolated tests; native StarCraft unit behavior remains active. The launcher leaves both engines running if the Go bridge exits, so restarting `build/world-bridge` reconnects the same session.

## Contract and authority

The [world.v1 schema](../bridge-protocol/world.v1.schema.json) defines the common envelope. Each state operation carries a protocol version, session ID, operation ID, authority, revision, and payload. Snapshot chunks have consecutive indexes and acknowledgments. The bridge rejects duplicate chunks, out of order chunks, invalid geometry, stale revisions, and unknown destruction identities. The complete snapshot replaces the bridge registry atomically. A bridge restart causes both adapters to reconnect and rebuild from the current OpenRCT2 park.

OpenRCT2 publishes terrain cells, rides, shops, facilities, paths, walls, scenery, guests, and staff. Multi-tile scenery and ride tracks receive one logical ID with multiple geometry cells. Wall collision rectangles are thin segments. Tile object keys carry a generation number, so removing and rebuilding at the same location yields a new ID. Terrain and mobile actors are described but are not destructible combat targets. Mapping rules in `internal/world/mapping.go` supply generic destructibility, health, targetability, collision, and owner defaults; the Go service accepts additional JSON rules with `--rules` (see the [example overrides](../bridge-protocol/world-mapping.example.json)). Armor, damage scale, and destruction effect overrides are represented in the model but are not yet applied by OpenBW or OpenRCT2.

The bridge centers parks of at most 256×256 tiles in the native map at one OpenRCT2 tile per OpenBW build tile and converts OpenBW actor coordinates back into park pixels. OpenBW creates civilian combat proxies through its native `createUnit` path, associates successful creations with logical IDs, applies configured HP, and uses native StarCraft attacks and engine damage. A second BWAPI player adapter applies authenticated Marine move, attack, attack-move, hold, and stop orders on its simulation frame. Preplaced actor IDs are shared across player processes by a deterministic initial-position registry; park-target links carry their logical ID and proxy location, and ambiguous local matches are rejected. The OpenRCT2 server checks the original object identity and footprint before issuing the relevant native demolition action. Only confirmed park removal advances the world revision and sends obstacle removal acknowledgment. OpenRCT2 multiplayer distributes those native changes and synchronized actor render actions to clients.

Runtime OpenBW Marines use `actor.spawn`, participant-specific `actor.bind`, and `actor.despawn` beside disposable combat snapshots. The Go actor registry requires both native bindings before routing a command. On publisher reconciliation it forwards deaths missed during a disconnection to the controller and park. OpenRCT2 uses the existing native renderer and synchronized snapshot action; click selection, drag selection, and squad orders accept a bound runtime ID. Despawn clears selection and saved group references immediately, while the next full combat snapshot removes the native render entry.

## Runtime unit spawning

The Frontier squad window has a **Spawn Marine** placement tool and a 1–5 count selector. The current Terran commander clicks a park tile to send a synchronized OpenRCT2 action. The server checks commander authority and session before forwarding the request. The bridge validates bounds, scenario state and capacity, transforms the park point into OpenBW pixels, and journals the request ID and per-unit results. Native ownership is selected from the active OpenBW player configuration, never from the client payload. Native placement checks map bounds, walkability, static obstacles and blocking units.

The bridge issues one native creation at a time, including within a five-Marine batch. It waits for the actual OpenBW creation event, canonical `actor.spawn`, and publisher and controller `actor.bind` acknowledgments before marking that unit `ready` and issuing the next. Failed units retain a reason and do not roll back successful siblings. The player sees `queued`, `issued`, `created`, `ready`, `rejected`, `failed`, or `uncertain` status. The same queue accepts trusted scenario Zergling waves through optional `spawn_waves` configuration; OpenRCT2 clients cannot request enemy ownership. The example [Zerg wave fixture](../tests/fixtures/frontier-outpost-zerg-wave.json) adds five native Zerglings.

Requests use session-unique, retry-stable IDs. Repeating the same request returns its recorded result; reusing an ID with different parameters is rejected. The bridge persists outcomes at `run-data/spawn-queue.json` by default. A bridge restart reconciles native actors and an in-flight creation before resuming the queue. It retries an uncertain command only if the same OpenBW publisher explicitly reports that it never received it. Client disconnects do not cancel or repeat native work. The queue admits at most 64 pending units, at most five per request and one creation awaiting identity at a time. The `--max-live-actors` bridge option defaults to 240, leaving room below the 256-unit combat snapshot ceiling. The park and native map remain static during spawning; no production building or economy cost is implemented.

`world.ready` reports counts by reason and up to 256 example IDs for objects that could not receive a combat proxy. This includes traversable paths, objects beyond the configured target attempt limit, and failed native placements. The bridge retains their entity and geometry descriptors instead of silently dropping them. The actor snapshot payload allows 256 units; it reports total and omitted counts and is disposable independently of reliable world operations.

## Current limits

The Go bridge derives one native 8-pixel navigation mask from the park snapshot. It blocks centered-map padding, water, missing terrain cells, and existing solid-object rectangles. Adjacent surface tiles connect only when both native quarter heights on their shared edge agree; a cliff blocks both full tiles beside that edge (64 pixels total), since narrower barriers let native path smoothing cross. A valid slope stays traversable, and elevated interior tiles stay open. OpenBW still performs pathfinding, collision, and combat. An entirely absent terrain export is treated as legacy flat ground inside park bounds. Partial exports block missing cells.

The mask is packed one bit per walk cell and sent in bounded hex chunks to both OpenBW participants. Each calculates the same FNV-1a hash before applying it to native VF4 walkability and rebuilding path regions. Startup `world.ready` waits for matching applied hashes from both participants and all target-link acknowledgements. A confirmed demolition causes the bridge to derive a new full mask, preserving permanent cliffs, and schedules both native updates at the same simulation frame. The civilian proxy retains its built-in hitbox, so the combat target and physical obstacle do not match a large ride's footprint. Live terrain construction remains unsupported: `entity.upsert`, `entity.remove`, `entity.transform`, and `navigation.terrain.update` are defined in the protocol and rejected with `live_update_unsupported`. Continuous guest/staff transfers are deferred. A failed native demolition remains failed; an authoritative resync can recreate a target for a later attempt.

OpenBW builds its path regions in `upstream/openbw/bwgame.h::regions_create`. The native patches replace the walkability mask, invalidate active paths, and rebuild regions when park geometry changes. The [first playable verification](archive/first-playable-verification.md) reports measured movement through the park and identifies any still failing demolition routes.

### Troubleshooting

- `no_enemy_player` or zero targets: regenerate `world-base-v5-256.scm`; older base maps have no third target-owner slot.
- `proxy_not_created`: OpenBW rejected a native civilian placement. Inspect `world.ready.unsupported_reasons` and lower or raise `BRIDGE_MAX_TARGETS` only after checking the specific park geometry.
- `navigation=metadata_only`: a native mask update failed or was unavailable; Frontier Outpost does not start in this state.
- `invalid_target` on a Marine order: the controller could not uniquely associate that logical target with a local native proxy, or the target was already removed.
- After a bridge restart, wait for a fresh `WORLD_READY` line before sending new commands. The adapters reconnect and reconcile from OpenRCT2's current snapshot.

## Verification

Run unit and adapter checks:

```bash
/usr/local/go/bin/go test ./...
node tests/test_world_plugin.js
cmake --build build/bridge-module --parallel 2
```

A live run on `frontier-outpost.park` discovered 4,426 entities and 65,536 terrain cells without scenario configuration. With `BRIDGE_MAX_TARGETS=128`, OpenBW confirmed 113 native park targets; the remaining eligible objects were explicitly reported as unsupported by configured capacity or native placement. Native Marine combat destroyed ride 1, OpenRCT2 confirmed its removal, and two clients showed the same resulting ride set. Restarting only the Go service rebuilt the current park snapshot and returned to `world.ready` with 113 targets. A separated-army fixture delivered 100 mixed actor states to each of two clients without the old 32-unit limit.

For runtime actor recovery, `tests/test_actor_lifecycle_live.sh` runs two fresh Frontier sessions with licensed local assets. Each starts with six Marines, verifies a seventh native Marine and both participant bindings, observes matching client snapshots, reconnects a client, restarts only the Go bridge, issues native move and attack orders, and confirms death and post-death command rejection. The [shared actor verification report](archive/shared-actor-verification.md) records the actual runs and limits.

`tests/test_unit_spawn_live.sh` uses the OpenRCT2 synchronized spawn action to create five native Marines and checks eleven distinct Marine IDs on two clients. Its `BRIDGE_SPAWN_RECOVERY=1` mode reconnects a client, restarts the Go bridge, kills one runtime Marine with a test-only native hook and requests a replacement. `BRIDGE_TEST_DISCONNECT_SPAWN_INDEX=2` interrupts a batch after native issue to exercise uncertain-command reconciliation. `tests/test_unit_spawn_zerg_live.sh` verifies a trusted five-Zergling wave, native movement and attack frames. The [unit spawn verification report](archive/unit-spawn-verification.md) records commands, run artifacts and limits.

The unrelated OpenRCT2 `EverythingPark.park` test save also bootstrapped through the same launcher: 23,097 discovered entities, 65,536 terrain cells, 3,987 registered obstacle descriptors, and 113 mapped combat targets. `world.ready` reported 10,537 unsupported destructible entities by reason, so this run demonstrates discovery and explicit capacity reporting rather than complete combat coverage of that large park.
