# Documentation

| Document | Purpose | Status |
| --- | --- | --- |
| [Passthrough RTS Bridge specification](specification.md) | OpenBW/BWAPI × OpenRCT2 architecture, feasibility gate, milestones, and acceptance criteria | Current — Rev 2 |
| [Bootstrap guide](bootstrap.md) | Pinned checkouts, build commands, data prerequisites, and current proof status | In progress |
| [Park assault](park-assault.md) | Frontier Outpost fixture, 20-Zergling navigation and three-target live siege | Current |
| [World bridge](world-bridge.md) | Generic park startup, protocol, limits, and troubleshooting | In progress |
| [OpenBW adapter status](openbw-adapter-status.md) | Historical capacity measurements and current native patch note | Historical measurements |
| [First playable verification](first-playable-verification.md) | Frontier Outpost live gameplay, navigation, and regression results | In progress |
| [Asset and source inventory](licensing.md) | License evidence and data handling for pinned dependencies | Initial review |
| [Historical archive](archive/README.md) | Superseded Recoil/Minecraft proposal and Raspberry Pi assessment | Archived |

The first implementation gate is a headless `BWAPILauncher` session whose custom BWAPI module creates, moves, and publishes the actual simulated unit. The OpenRCT2 renderer work follows that proof.
