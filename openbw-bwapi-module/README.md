# BridgeAIModule

This shared BWAPI `AIModule` is loaded by the OpenBW fork's `BWAPILauncher`. It uses the public BWAPI calls to create one `Zerg_Zergling`, issue alternating `Unit::move` orders, read `getPosition`, `getAngle`, `isMoving`, `getID`, and `getFrameCount`, then publish complete v1 snapshots over a nonblocking TCP listener bound to `127.0.0.1`.

Build it after the pinned BWAPI fork:

```bash
scripts/build-bwapi.sh
scripts/build-bridge-module.sh
```

The module uses `BRIDGE_PUBLISH_PORT` (default `39999`), `BRIDGE_MAP_ID` (default `demo-flat`), and `BRIDGE_SPAWN_X/Y` plus `BRIDGE_TARGET_X/Y` (defaults `320,480` and `640,480`). The `scripts/run-bwapi.sh` launcher prepares the runtime directory from user-supplied game data. `scripts/receive-snapshots.py` is the M0 movement smoke receiver.

The socket holds at most one pending full snapshot and drops a new snapshot when the receiver is slow. A later full snapshot repairs that loss. It never calls BWAPI from another thread. No StarCraft assets are shipped here.

`BRIDGE_SCENARIO=battle` runs the opt-in Marine-versus-Zergling combat feasibility probe on the pinned `testmap1.scm` map. Its [battle gate record](../docs/battle-feasibility-resolution-2026-10-10.md) documents genuine two-sided OpenBW combat and the map configuration that made hostility repeatable. It does not yet publish battle snapshots. Run `scripts/test-battle-feasibility.py` to check the gate; a one-sided fight fails by design.
