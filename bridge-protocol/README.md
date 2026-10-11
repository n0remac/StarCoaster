# Bridge protocol v1

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
