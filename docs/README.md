# Documentation

| Document | Purpose | Status |
| --- | --- | --- |
| [Passthrough RTS Bridge specification](specification.md) | OpenBW/BWAPI × OpenRCT2 architecture, feasibility gate, milestones, and acceptance criteria | Current — Rev 2 |
| [Bootstrap guide](bootstrap.md) | Pinned checkouts, build commands, data prerequisites, and current proof status | In progress |
| [Park assault](park-assault.md) | Frontier Outpost fixture, 20-Zergling navigation and three-target live siege | Current |
| [Asset and source inventory](licensing.md) | License evidence and data handling for pinned dependencies | Initial review |
| [Historical archive](archive/README.md) | Superseded Recoil/Minecraft proposal and Raspberry Pi assessment | Archived |

The first implementation gate is a headless `BWAPILauncher` session whose custom BWAPI module creates, moves, and publishes the actual simulated unit. The OpenRCT2 renderer work follows that proof.
