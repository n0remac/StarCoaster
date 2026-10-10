# Passthrough RTS Bridge

This project is a proof of concept for showing one genuine OpenBW-simulated Zergling inside a shared OpenRCT2 park. A headless OpenBW/BWAPI module owns the unit's movement; an OpenRCT2 multiplayer server distributes its state to two modified graphical clients, which render an independently illustrated stand-in creature in the park scene.

Start with the [Rev 2 implementation specification](docs/specification.md) and [bootstrap guide](docs/bootstrap.md). The [bridge protocol](bridge-protocol/README.md) has the first schema and fixture. The earlier Recoil/Minecraft proposal and Raspberry Pi assessment are kept in the [documentation archive](docs/archive/README.md) for historical reference.

The repository contains pinned upstream checkouts under `upstream/`, build scripts, and an initial BWAPI module that publishes actual unit snapshots. OpenRCT2 rendering and multiplayer synchronization have not been implemented. The runtime movement proof still requires compatible StarCraft MPQs and a map; OpenRCT2 gameplay requires RCT2 assets.
