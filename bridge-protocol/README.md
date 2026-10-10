# Bridge protocol v1

The POC publisher sends one UTF-8 JSON object per line over a TCP connection bound to `127.0.0.1`. Each line is a **full** snapshot, capped at 4096 bytes in the POC. The [schema](units.snapshot.v1.schema.json) and [fixture](fixtures/one-unit.ndjson) define the current wire shape.

`x` and `y` are OpenBW map pixel coordinates. The OpenRCT2 adapter alone converts them to park world coordinates. `facing` is one unsigned byte for a full circle: 0 is east, increasing according to the BWAPI angle after normalization. The adapter must calibrate the axis handedness before choosing a sprite frame.

`session` changes on each launcher run; `seq` starts at 1 for that session. Receivers reject stale or repeated sequence numbers within a session. `map_id` must match the configured park mapping. A snapshot with `units: []` removes all actors from the previous full snapshot. The server validates all fields and world bounds before issuing a synchronized OpenRCT2 action.

The first BWAPI module publishes on every third simulation frame. The resulting rate depends on the simulator's frame speed. This cadence is tied to `bw_tick`, so pausing the simulation does not generate repeated snapshots for the same tick.

The schema limits the POC to one actor. A later protocol revision can raise that limit after profiling.
