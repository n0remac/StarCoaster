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

The launcher uses `BRIDGE_SCENARIO=world` only to select the generic adapters. It does not create matching rides, park objects, proxy IDs, or a park-specific map. `scripts/create-world-base-map.py` produces the same reusable StarCraft base map once. The Go service listens on loopback ports 40010 for the OpenRCT2 server plugin and 40011 for OpenBW. The existing actor snapshot transport and native renderer remain available in the same plugin.

## Contract and authority

The [world.v1 schema](../bridge-protocol/world.v1.schema.json) defines the common envelope. Each state operation carries a protocol version, session ID, operation ID, authority, revision, and payload. Snapshot chunks have consecutive indexes and acknowledgments. The bridge rejects duplicate chunks, out of order chunks, invalid geometry, stale revisions, and unknown destruction identities. The complete snapshot replaces the bridge registry atomically. A bridge restart causes both adapters to reconnect and rebuild from the current OpenRCT2 park.

OpenRCT2 publishes terrain cells, rides, shops, facilities, paths, walls, scenery, guests, and staff. Multi-tile scenery and ride tracks receive one logical ID with multiple geometry cells. Wall collision rectangles are thin segments. Tile object keys carry a generation number, so removing and rebuilding at the same location yields a new ID. Terrain and mobile actors are described but are not destructible combat targets. Mapping rules in `internal/world/mapping.go` supply generic destructibility, health, targetability, collision, and owner defaults; the Go service accepts additional JSON rules with `--rules` (see the [example overrides](../bridge-protocol/world-mapping.example.json)). Armor, damage scale, and destruction effect overrides are represented in the model but are not yet applied by OpenBW or OpenRCT2.

The bridge fits park coordinates into the base map and converts OpenBW actor coordinates back into park pixels. OpenBW creates civilian combat proxies through its native `createUnit` path, matches asynchronous creations to logical IDs on later frames, applies configured HP, and uses native Zergling attacks and engine damage. The OpenRCT2 server checks the original object identity and footprint before issuing the relevant native demolition action. Only confirmed park removal advances the world revision and sends obstacle removal acknowledgment. OpenRCT2 multiplayer distributes those native changes and synchronized actor render actions to clients.

`world.ready` reports counts by reason and up to 256 example IDs for objects that could not receive a combat proxy. This includes traversable paths, objects beyond the current 128 target capacity, and overlapping placement. The bridge retains their entity and geometry descriptors instead of silently dropping them.

## Current limits

The startup path is usable for compatible parks and static terrain. OpenBW stores the discovered collision rectangles separately from target IDs, but this mode reports `navigation: metadata_only`: the native path regions and local collision are not rebuilt from them. The reusable map terrain stays fixed. `entity.upsert`, `entity.remove`, `entity.transform`, and `navigation.terrain.update` are defined in the protocol and rejected with `live_update_unsupported` until both engines can commit them together. Continuous guest/staff transfers are deferred. A failed native demolition remains failed; an authoritative resync can recreate a target for a later attempt.

## Verification

Run unit and adapter checks:

```bash
/usr/local/go/bin/go test ./...
node tests/test_world_plugin.js
node tests/test_plugin_snapshots.js
node tests/test_park_assault_plugin.js
cmake --build build/bridge-module --parallel 2
```

A live run on `frontier-outpost.park` discovered 4,426 entities and 65,536 terrain cells without the scenario configuration. OpenBW confirmed 115 target proxies; the remaining targetable objects were explicitly reported as unsupported by capacity or placement. Native combat and OpenRCT2 actions confirmed removals for rides, large scenery, and small scenery. Restarting only the Go service rebuilt the same park session at revision 2. Two headless OpenRCT2 clients later joined with identical ride sets, and 83 common actor snapshots matched in tick, identity, and coordinates.

The unrelated OpenRCT2 `EverythingPark.park` test save also bootstrapped through the same launcher: 23,097 discovered entities, 65,536 terrain cells, 3,987 registered obstacle descriptors, and 113 mapped combat targets. `world.ready` reported 10,537 unsupported destructible entities by reason, so this run demonstrates discovery and explicit capacity reporting rather than complete combat coverage of that large park.
