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
| Local TCP fixture to `scripts/receive-snapshots.py` | Passed: three framed snapshots were received, including a reported position change. **This was fixture data, not OpenBW simulation.** |
| `BWAPILauncher` with `/home/pi/games/starcraft` | Passed headlessly with the pinned `ZergTest.scm` map and custom module. BWAPI registered Zergling ID `16`; `Unit::move` succeeded and `getPosition` changed from `(320,480)` to `(640,480)` along the path. |
| Live `scripts/receive-snapshots.py` | Passed against the running launcher: one session, increasing sequence and tick, and changing unit positions. |
| `STARCRAFT_DATA_DIR=/home/pi/games/starcraft scripts/test-bwapi-headless.py --seconds 10` | Passed end to end. The harness launched BWAPI itself, found registered unit `16` and an accepted move in its log, and received positions `(320,480)`, `(337,480)`, `(355,480)`. Logs saved under ignored `run-data/headless-test/`. |
| 15-second paced BWAPI run | 115 logged unit snapshots, one unit ID, six accepted waypoint orders, zero move errors. Approximate publication rate: 7.7 snapshots/s. Full logs are under ignored `run-data/`. |
| Headless OpenRCT2 host | Loaded the upstream `EverythingPark.park` test park and listened on `127.0.0.1:11753`. This does not prove graphical rendering or the bridge action. |
| Combined headless run | BWAPI moved unit `16` while OpenRCT2 hosted the test park. One process sample showed about 38 MiB RSS for `BWAPILauncher` and 135 MiB RSS for the OpenRCT2 host; `vcgencmd` reported `throttled=0x0` and 46.1°C. This is a short feasibility sample, not a two-client load test. |
| M1 paint-probe build | Passed. The modified OpenRCT2 client compiled with a fixed world-paint actor and generated `g2.dat` with 182 images, including 12 original alien scout sprites. All 12 were exported back from `g2.dat` as nonblank 32×32 images. In-world appearance and occlusion remain unverified. |
| OpenRCT2 graphical screenshot command | Failed: `Unable to load g1 graphics`. The apt OpenRCT2 package is installed, but no RCT2 `g1.dat` was found. |

The fixture receiver prints `reported unit position changed (publisher not authenticated)`. That fixture result establishes TCP framing only. The separate live run establishes BWAPI creation, ordering, and movement. Representative live log lines:

```text
[bridge] registered unit id=16
[bridge] Unit::move id=16 target=640,480
[bridge] tick=3 seq=2 id=16 x=320 y=480 moving=1
[bridge] tick=9 seq=4 id=16 x=342 y=480 moving=1
session=abee1a6b88c4e8e97bb752e26b818af0 seq=21 tick=60 id=openbw:16 x=615 y=480 motion=walk
```

## Screenshot status

No screenshot was produced. The OpenRCT2 software screenshot command fails while loading `g1.dat`. A screenshot of the requested crossover also requires the native renderer and multiplayer plugin, which have not yet been implemented. The headless host and BWAPI movement proof are genuine, but neither creates an in-world actor image.

The apt-installed OpenRCT2 is v0.4.3 (plugin API 65). This project builds pinned OpenRCT2 v0.5.5 (plugin API 124), so the apt executable cannot serve as a matching graphical client for the native bridge fork.

## Inputs needed for the next runtime gate

- RollerCoaster Tycoon 2 or RCT Classic game files containing `Data/g1.dat`. The upstream OpenRCT2 checkout already supplies a park usable for a baseline test.

Keep these user-supplied files outside Git. The launch scripts stage paths under ignored `run-data/`. The StarCraft archives at `/home/pi/games/starcraft` were used locally and were not copied into Git.
