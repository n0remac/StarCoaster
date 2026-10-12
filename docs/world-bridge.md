# World bridge startup mode

`world.v1` is the generic startup path. It discovers the loaded OpenRCT2 park on the authoritative server, transfers a complete revisioned snapshot through the Go bridge, and creates OpenBW target proxies at a simulation frame boundary. It uses a reusable 128×128 OpenBW base map. The old patrol, siege, frontier, and park assault demos remain available as regression fixtures.

## Start

Build the pinned OpenRCT2 and BWAPI integrations as described in [bootstrap](bootstrap.md), then build the Go service:

```bash
/usr/local/go/bin/go build -o build/world-bridge ./cmd/world-bridge
scripts/build-bridge-module.sh
RCT2_DATA_DIR=/path/to/rct2 STARCRAFT_DATA_DIR=/path/to/starcraft \
  scripts/run-world-session.sh /path/to/saved-park.park
```

The launcher uses `BRIDGE_SCENARIO=world` only to select the generic adapters. It does not create matching rides, park objects, proxy IDs, or a park-specific map. `scripts/create-world-base-map.py` produces the reusable `world-base-v4.scm` once. Its Zerg and Terran human slots run synchronized BWAPI adapters; a third computer slot owns park targets so either faction can attack them. The Go service listens on loopback ports 40010 for the OpenRCT2 server plugin, 40011 for the OpenBW publisher, and 40012 for the Terran unit controller. The existing actor snapshot transport and native renderer remain available in the same plugin.

`BRIDGE_MAX_TARGETS` controls attempted native proxies (default 512, accepted range 1–1500). This is an attempt limit, not a guarantee that every placement succeeds. `BRIDGE_DISABLE_ASSAULT_AI=1` pauses the example Zergling controller for isolated tests; native StarCraft unit behavior remains active. The launcher leaves both engines running if the Go bridge exits, so restarting `build/world-bridge` reconnects the same session.

## Contract and authority

The [world.v1 schema](../bridge-protocol/world.v1.schema.json) defines the common envelope. Each state operation carries a protocol version, session ID, operation ID, authority, revision, and payload. Snapshot chunks have consecutive indexes and acknowledgments. The bridge rejects duplicate chunks, out of order chunks, invalid geometry, stale revisions, and unknown destruction identities. The complete snapshot replaces the bridge registry atomically. A bridge restart causes both adapters to reconnect and rebuild from the current OpenRCT2 park.

OpenRCT2 publishes terrain cells, rides, shops, facilities, paths, walls, scenery, guests, and staff. Multi-tile scenery and ride tracks receive one logical ID with multiple geometry cells. Wall collision rectangles are thin segments. Tile object keys carry a generation number, so removing and rebuilding at the same location yields a new ID. Terrain and mobile actors are described but are not destructible combat targets. Mapping rules in `internal/world/mapping.go` supply generic destructibility, health, targetability, collision, and owner defaults; the Go service accepts additional JSON rules with `--rules` (see the [example overrides](../bridge-protocol/world-mapping.example.json)). Armor, damage scale, and destruction effect overrides are represented in the model but are not yet applied by OpenBW or OpenRCT2.

The bridge fits park coordinates into the base map and converts OpenBW actor coordinates back into park pixels. OpenBW creates civilian combat proxies through its native `createUnit` path, associates successful creations with logical IDs, applies configured HP, and uses native StarCraft attacks and engine damage. A second BWAPI player adapter applies authenticated Marine move, attack, attack-move, hold, and stop orders on its simulation frame. Preplaced actor IDs are shared across player processes by a deterministic initial-position registry; park-target links carry their logical ID and proxy location, and ambiguous local matches are rejected. The OpenRCT2 server checks the original object identity and footprint before issuing the relevant native demolition action. Only confirmed park removal advances the world revision and sends obstacle removal acknowledgment. OpenRCT2 multiplayer distributes those native changes and synchronized actor render actions to clients.

`world.ready` reports counts by reason and up to 256 example IDs for objects that could not receive a combat proxy. This includes traversable paths, objects beyond the configured target attempt limit, and failed native placements. The bridge retains their entity and geometry descriptors instead of silently dropping them. The actor snapshot payload allows 256 units; it reports total and omitted counts and is disposable independently of reliable world operations.

## Current limits

The startup path is usable for compatible parks and static terrain. OpenBW stores the discovered collision rectangles separately from target IDs, but this mode reports `navigation: metadata_only`: the native path regions and local collision are not rebuilt from them. The civilian proxy retains its built-in hitbox, so the combat target and physical obstacle do not match a large ride's footprint. The reusable map terrain stays fixed. `entity.upsert`, `entity.remove`, `entity.transform`, and `navigation.terrain.update` are defined in the protocol and rejected with `live_update_unsupported` until both engines can commit them together. Continuous guest/staff transfers are deferred. A failed native demolition remains failed; an authoritative resync can recreate a target for a later attempt.

OpenBW builds its path regions from map walkability during map initialization in `upstream/openbw/bwgame.h::regions_create`. The BWAPI game wrapper currently exposes walkability as a read-only query. Replacing the region graph and invalidating active paths after world.v1 snapshot arrival requires an isolated engine and BWAPI patch; this adapter does not claim the carousel, wall-gap, or blocked-corridor navigation tests. See [adapter status and measurements](openbw-adapter-status.md).

### Troubleshooting

- `no_enemy_player` or zero targets: regenerate `world-base-v4.scm`; older base maps have no third target-owner slot.
- `proxy_not_created`: OpenBW rejected a native civilian placement. Inspect `world.ready.unsupported_reasons` and lower or raise `BRIDGE_MAX_TARGETS` only after checking the specific park geometry.
- `navigation=metadata_only`: park obstacle rectangles are registered but OpenBW movement still follows the reusable base map.
- `invalid_target` on a Marine order: the controller could not uniquely associate that logical target with a local native proxy, or the target was already removed.
- After a bridge restart, wait for a fresh `WORLD_READY` line before sending new commands. The adapters reconnect and reconcile from OpenRCT2's current snapshot.

## Verification

Run unit and adapter checks:

```bash
/usr/local/go/bin/go test ./...
node tests/test_world_plugin.js
node tests/test_plugin_snapshots.js
node tests/test_park_assault_plugin.js
cmake --build build/bridge-module --parallel 2
```

A live run on `frontier-outpost.park` discovered 4,426 entities and 65,536 terrain cells without scenario configuration. With `BRIDGE_MAX_TARGETS=128`, OpenBW confirmed 113 native park targets; the remaining eligible objects were explicitly reported as unsupported by configured capacity or native placement. Native Marine combat destroyed ride 1, OpenRCT2 confirmed its removal, and two clients showed the same resulting ride set. Restarting only the Go service rebuilt the current park snapshot and returned to `world.ready` with 113 targets. A separated-army fixture delivered 100 mixed actor states to each of two clients without the old 32-unit limit.

The unrelated OpenRCT2 `EverythingPark.park` test save also bootstrapped through the same launcher: 23,097 discovered entities, 65,536 terrain cells, 3,987 registered obstacle descriptors, and 113 mapped combat targets. `world.ready` reported 10,537 unsupported destructible entities by reason, so this run demonstrates discovery and explicit capacity reporting rather than complete combat coverage of that large park.
