# OpenBW bridge module

`BridgeAIModule.cpp` loads in both OpenBW player slots through BWAPI. The
publisher observes native actor and target state; the Terran controller applies
Marine commands on the simulation thread. OpenBW owns movement, pathfinding,
health, and combat. The Go world bridge coordinates snapshots and commands.

Build through `scripts/project.sh build`, or run `scripts/build-bwapi.sh` and
`scripts/build-bridge-module.sh` after fetching the pinned upstream sources.
`scripts/run-bwapi.sh` stages the user's local StarCraft archives, map, and
module for one participant. `scripts/run-world-session.sh` starts both roles
with the packaged scenario's native map. `BRIDGE_FRAME_MS` controls OpenBW frame
pacing; `BRIDGE_WORLD_ROLE=controller` selects the Terran command role.

The module and its launcher do not bundle StarCraft data. See the
[bootstrap guide](../docs/bootstrap.md) and [licensing inventory](../docs/licensing.md).
