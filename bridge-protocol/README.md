# Bridge protocol v1

The publisher sends one UTF-8 JSON object per line over a TCP connection bound to `127.0.0.1`. Each line is a **full** snapshot, capped at 16384 bytes including the JSON but excluding the newline. A 32-unit packet with 32-byte IDs and signed decimal 32-bit coordinates fits under 8 KiB; the larger cap leaves room for envelope fields. The [schema](units.snapshot.v1.schema.json) and [fixture](fixtures/one-unit.ndjson) define the wire shape. Every receiver rejects an invalid array as a whole, including duplicate IDs.

`x` and `y` are OpenBW map pixel coordinates. The OpenRCT2 adapter alone converts them to park world coordinates. `facing` is one unsigned byte for a full circle: 0 is east, increasing according to the BWAPI angle after normalization. The adapter must calibrate the axis handedness before choosing a sprite frame.

`session` changes on each launcher run; `seq` starts at 1 for that session. Receivers reject stale or repeated sequence numbers within a session. `map_id` must match the configured park mapping. A snapshot with `units: []` removes all actors from the previous full snapshot. The server validates all fields and world bounds before issuing a synchronized OpenRCT2 action.

The first BWAPI module publishes on every third simulation frame. The resulting rate depends on the simulator's frame speed. This cadence is tied to `bw_tick`, so pausing the simulation does not generate repeated snapshots for the same tick.

Protocol v1 supports up to 32 actors. The default demo still publishes one Zergling; `BRIDGE_DEMO_UNITS=8` opts into the squad patrol.

## Ride siege snapshot v2

The separate [scenario snapshot v2 schema](scenario.snapshot.v2.schema.json) adds a `targets` array to the live actor snapshot. The current allowlist contains exactly `carousel-1` with a stable `proxy_unit_id`, `hp`, `max_hp`, and `intact`, `damaged`, or `destroyed` state. The bridge emits one full snapshot every third BW frame, including Zergling positions and the terminal destroyed state in subsequent packets. The server validates the session, monotonically increasing sequence and BW tick, stable proxy identity, and nonincreasing HP before coordinating one native ride demolition. The original v1 `units.snapshot` protocol and patrol demos remain available.
