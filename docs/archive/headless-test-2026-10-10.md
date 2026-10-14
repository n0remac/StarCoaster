> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Headless test record — 2026-10-10

Machine: Raspberry Pi, Linux AArch64. Test root: `/media/pi/media1/rts-bridge`.

## Checks performed

| Check | Result |
| --- | --- |
| `python3 scripts/check-dependencies.py` | Passed. OpenBW `4b046d5f`, BWAPI `48124ba8`, OpenRCT2 `33aacdeb` match the lock file. |
| `build/openrct2/openrct2-cli --version` | Passed: v0.5.5, Linux AArch64, network `0.5.5-2`, plugin API `124`. |
| `build/openrct2/openrct2 --version` | Passed with the same build and API versions. |
| `nm -D build/bridge-module/BridgeAIModule.so` | Passed: `gameInit` and `newAIModule` are exported. |
| `ctypes.CDLL` load of `BridgeAIModule.so` | Passed: the shared library loads on this Pi. |
| Local TCP fixture to `scripts/former v1 snapshot receiver` | Passed: three framed snapshots were received, including a reported position change. **This was fixture data, not OpenBW simulation.** |
| `BWAPILauncher` with `/home/pi/games/starcraft` | Passed headlessly with the pinned `ZergTest.scm` map and custom module. BWAPI registered Zergling ID `16`; `Unit::move` succeeded and `getPosition` changed from `(320,480)` to `(640,480)` along the path. |
| Live `scripts/former v1 snapshot receiver` | Passed against the running launcher: one session, increasing sequence and tick, and changing unit positions. |
| `STARCRAFT_DATA_DIR=/home/pi/games/starcraft scripts/former native movement smoke test --seconds 10` | Passed end to end. The harness launched BWAPI itself, found registered unit `16` and an accepted move in its log, and received positions `(320,480)`, `(337,480)`, `(355,480)`. Logs saved under ignored `run-data/headless-test/`. |
| 15-second paced BWAPI run | 115 logged unit snapshots, one unit ID, six accepted waypoint orders, zero move errors. Approximate publication rate: 7.7 snapshots/s. Full logs are under ignored `run-data/`. |
| Headless OpenRCT2 host | Loaded the upstream `EverythingPark.park` test park and listened on `127.0.0.1:11753`. This does not prove graphical rendering or the bridge action. |
| Combined headless run | BWAPI moved unit `16` while OpenRCT2 hosted the test park. One process sample showed about 38 MiB RSS for `BWAPILauncher` and 135 MiB RSS for the OpenRCT2 host; `vcgencmd` reported `throttled=0x0` and 46.1°C. This is a short feasibility sample, not a two-client load test. |
| M1 paint-probe build | Passed. The modified OpenRCT2 client compiled with a world-paint actor and generated `g2.dat` with 182 images, including 12 original alien scout sprites. All 12 were exported back from `g2.dat` as nonblank 32×32 images. Live graphical clients now show the actor in the park; scenery occlusion remains unverified. |
| Real server bridge | Passed headlessly: the remote plugin connected only on the server to `127.0.0.1:39999`, accepted BWAPI snapshots, invoked the custom synchronized action, and the native binding logged OpenRCT2 application ticks and matching unit coordinates. |
| Two headless clients | Passed after a client-only title-scene network tick patch. Both loaded the remote plugin. Across 143 sequence numbers present on the server and both clients, `(OpenRCT2 tick, unit ID, x, y)` matched exactly with zero mismatches. This proves replicated presentation state, not scene pixels. |
| 65-second full headless run | `scripts/former headless multiplayer smoke test --seconds 65` passed with the real BWAPI launcher, one OpenRCT2 host, and two joined clients. Server: 542 applied snapshots; client A: 532; client B: 515. All 515 snapshots common to all three matched exactly in tick, unit ID, and position. Logs are under ignored `run-data/headless-multiplayer/`. |
| Publisher stop and restart | Passed with one joined headless client. Stopping `BWAPILauncher` produced a synchronized `despawn` at OpenRCT2 tick `3133934` on both server and client. Restart used a different session epoch (`fe0490...` to `f481ba...`) and applied new unit positions after the removal. Logs are under ignored `run-data/restart-test/`. |
| RCT2 graphics | Found user-supplied `/home/pi/games/rct2/Data/g1.dat`; graphical clients now load the park. |
| 65-second graphical capture | Passed with `scripts/former prototype capture driver --seconds 65` on `BigMapTest.sv6`. Server: 574 applied snapshots; client A: 557; client B: 514. All 514 common snapshots matched in OpenRCT2 tick, actor ID, x, and y. Neither client logged a desync. Six original 1280×800 screenshots were saved under ignored `run-data/visual-demo/`. Early and later frames show the creature at different screen positions. |
| Independent camera rotation | Passed with `--rotate-client-b` in a 12-second run. Both clients rendered the actor with different camera rotations; 155 common snapshots matched exactly. Screenshots saved under `run-data/visual-demo-rotation/`. |

The fixture receiver prints `reported unit position changed (publisher not authenticated)`. That fixture result establishes TCP framing only. The separate live run establishes BWAPI creation, ordering, and movement. Representative live log lines:

```text
[bridge] registered unit id=16
[bridge] Unit::move id=16 target=640,480
[bridge] tick=3 seq=2 id=16 x=320 y=480 moving=1
[bridge] tick=9 seq=4 id=16 x=342 y=480 moving=1
session=abee1a6b88c4e8e97bb752e26b818af0 seq=21 tick=60 id=openbw:16 x=615 y=480 motion=walk
```

## Screenshot status

The live capture uses two Xvfb displays and `scrot`, recording the actual modified OpenRCT2 client windows. The actor is visible in the park paint scene in [client A early](../../run-data/visual-demo/client-a-early.png), [client A later](../../run-data/visual-demo/client-a-later.png), and [client B later](../../run-data/visual-demo/client-b-later.png). [Client B with independent camera rotation](../../run-data/visual-demo-rotation/client-b-final.png) is also recorded. These screenshots are local, ignored files because they include RCT2 graphics supplied by the user. The broad grass test area does not yet prove scenery occlusion.

The apt-installed OpenRCT2 is v0.4.3 (plugin API 65). This project builds pinned OpenRCT2 v0.5.5 (plugin API 124), so the apt executable cannot serve as a matching graphical client for the native bridge fork.

## Remaining visual gate

Test the actor crossing a scenery object or height transition and verify its front/behind order. A graphical run on the more crowded `EverythingPark.park` showed an OpenRCT2 random-state desync warning; the cause needs isolation before using that park for acceptance. A smaller park rejected the default actor coordinates as out of bounds. The stable `BigMapTest.sv6` run passed without the warning.

Keep the user-supplied game files and screenshots containing RCT2 graphics outside Git. The launch scripts stage paths under ignored `run-data/`; the StarCraft archives at `/home/pi/games/starcraft` were not copied into Git.
