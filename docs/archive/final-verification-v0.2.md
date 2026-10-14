> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# StarCoaster v0.2 final verification

The consolidation build and all required automated gates passed on the Raspberry Pi with locally installed RCT2 and StarCraft data. The final commands were:

| Gate | Result | Evidence |
| --- | --- | --- |
| `scripts/project.sh build` | Pass | Pinned OpenRCT2, OpenBW, BWAPI, bridge module, and Go bridge built. Optional DiscordRPC headers were unavailable; OpenRCT2 built without them. |
| `scripts/project.sh test` | Pass | Go packages; CTest 3/3; Python 46/46; all five JavaScript plugin suites. |
| `scripts/project.sh test-live` | Pass | Native park navigation 6/6 in `run-data/frontier-native-nav-1791848422/`; generic two-client ride removal in `run-data/world-live-1791848476/`; two Frontier victory, reconnect, and restart cycles in `run-data/frontier-lifecycle/`. |
| Park geometry and four views | Pass | Deterministic wall/path checks run in the Python suite. Both graphical clients saved screenshots at all four OpenRCT2 camera rotations in `run-data/artifacts/20261012T233122Z-01c58848c6db/`. |
| Gameplay capture | Pass with scope noted below | The same artifact holds an 85-second, 15 FPS, 1600 × 500 H.264 video, 12 screenshots, logs, metadata, and verification JSON. |

The live navigation check observed blocked corridors before demolition, routes through the intended opening, Marines crossing the removed wall, all six Marines moving without stalls, and a Marine entering the removed carousel footprint. The generic live check confirmed OpenRCT2 ride removal and agreement between both clients. Each lifecycle cycle reached authoritative victory with six Marines and zero Zerglings, then client B rejoined the same session with six unique actors. The restart used a new session ID. The graphical recording reached authoritative defeat after combat and carousel demolition; its 459 shared client snapshots matched with zero mismatches.

The 15/30 FPS benchmarks in [recording performance](../recording-performance-v0.2.md) showed no material loss of simulation tick progress relative to capture off. Combined 30 FPS used 97.7% of one CPU core, so the Pi default remains 15 FPS. Single-client capture and two-client combined/separate capture use the same `VideoRecorder` and keep validated media and logs in the artifact viewer.

## Remaining limits

- The new v0.2 combat video is `capture_only` in `verification.json`: it shows native combat, carousel demolition, defeat, and matching clients, but does not repeat the drag-selection and wall-demolition control sequence. The earlier [first-playable demonstration](first-playable-verification.md) has `demonstration_complete: true`; the v0.2 native live test independently rechecks wall demolition and traversal on the polished park.
- The generic live demolition fixture limits discovery to 32 proxies so its one-ride regression has a bounded command queue. Broader proxy capacity and multi-proxy shared health remain outside this milestone.
- Arbitrary park terrain and height combinations, longer thermal recording behavior, and remote access to the local artifact viewer were not verified. The artifact files are preserved under ignored `run-data/`.
