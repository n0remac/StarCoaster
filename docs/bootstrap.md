# Bootstrap and current status

All source repositories live under `upstream/` in this project directory. Their exact revisions are recorded in [`dependencies.lock.json`](../dependencies.lock.json), and `scripts/check-dependencies.py` checks them. Upstream checkouts and build output are excluded from the bridge Git repository.

## Build order

The machine needs CMake, Ninja, GCC 12+, Python 3, and the OpenRCT2 development libraries listed in the [OpenRCT2 Linux build guide](https://github.com/OpenRCT2/OpenRCT2/wiki/Building-OpenRCT2-on-Linux). On this Pi, the dependencies were installed through `apt-get` on 2026-10-10:

```bash
sudo apt-get install --no-install-recommends -y \
  git python3 ninja-build cmake ccache libsdl2-dev libicu-dev pkg-config libcurl4-openssl-dev \
  libcrypto++-dev libfontconfig1-dev libfreetype6-dev libpng-dev \
  libssl-dev libzip-dev build-essential nlohmann-json3-dev \
  libflac-dev libvorbis-dev libzstd-dev xvfb scrot
```

From the project root:

```bash
scripts/fetch-upstream.py
scripts/check-dependencies.py
scripts/build-bwapi.sh
scripts/build-bridge-module.sh
scripts/build-openrct2.sh
scripts/install-openrct2-local.sh
```

`BRIDGE_BUILD_JOBS=2` is the default to limit memory use on the Pi. Build trees stay in `build/` on the attached drive. The OpenRCT2 build keeps networking, scripting, and its GUI enabled because the proof of concept requires both a headless server and graphical clients.
The local install stages OpenRCT2's project object and media packs in `build/openrct2-stage/usr/local/share/openrct2/`; it does not install into the system `/usr/local` tree and it does not provide the proprietary RCT2 assets.
`scripts/build-openrct2.sh` applies the reviewable native patch from `openrct2-patches/` and copies the original creature frames from `assets/alien-scout/` into the pinned checkout before building. The native build provides a render-only actor registry and script binding. The server-distributed plugin in `openrct2-plugin/` receives BWAPI snapshots and calls the binding through synchronized custom actions.

The locally built OpenRCT2 v0.5.5 uses the user-supplied RCT2 graphics at `/home/pi/games/rct2/Data/g1.dat` on this Pi. The apt-installed OpenRCT2 v0.4.3 does not have the native bridge patch or matching plugin API. To start a host manually:

```bash
RCT2_DATA_DIR=/path/to/your/rct2 scripts/run-openrct2-host.sh /path/to/park.park
```

`OPENRCT2_PORT` defaults to `11753`. The demo host listens on localhost and does not advertise to the public master server. Its user data and remote plugin directory are kept under ignored `run-data/openrct2-server/`.

## OpenBW runtime proof

The runtime needs three **user-supplied** StarCraft data archives: `StarDat.mpq`, `BrooDat.mpq`, and `Patch_rt.mpq`. The pinned BWAPI checkout includes a `ZergTest.scm` map that the launcher uses by default; `BRIDGE_MAP_FILE` can select another `.scm` or `.scx` map. The project does not download or commit the MPQs. `scripts/run-bwapi.sh` accepts the alternate README spelling `Stardat.mpq` / `Broodat.mpq` and creates ignored symlinks with the [exact names used by the pinned OpenBW loader](https://github.com/OpenBW/openbw/blob/4b046d5f65302b10cb0a745f0fecd37ec85b20a8/data_loading.h#L1322-L1324) in `run-data/openbw/`. The [BWAPI fork README](https://github.com/OpenBW/bwapi/blob/develop-openbw/README.md) names MPQs from StarCraft 1.16.1 or 1.18. Blizzard's [current free StarCraft installation](https://us.support.blizzard.com/en/article/troubleshooting-starcraft-or-brood-war-patches) is available through Battle.net, but [Blizzard support says the post-1.16.1 game data was repackaged](https://us.forums.blizzard.com/en/starcraft/t/missing-files-for-campaign-editor/3655); the current download alone does not provide the MPQs this fork expects.

For the repeatable headless movement gate on this Pi:

```bash
STARCRAFT_DATA_DIR=/home/pi/games/starcraft scripts/test-bwapi-headless.py --seconds 20
```

It checks the launcher log for a registered unit and accepted `Unit::move`, checks that the receiver saw changing positions, and saves both logs under ignored `run-data/headless-test/`. To run the launcher and receiver manually, use two terminals. In the first:

```bash
STARCRAFT_DATA_DIR=/path/to/your/starcraft scripts/run-bwapi.sh
```

In another terminal:

```bash
scripts/receive-snapshots.py --seconds 30
```

The receiver passes only after it sees the published unit position change. `BRIDGE_SPAWN_X`, `BRIDGE_SPAWN_Y`, `BRIDGE_TARGET_X`, `BRIDGE_TARGET_Y`, `BRIDGE_PUBLISH_PORT`, `BRIDGE_FRAME_MS`, and `BRIDGE_MAP_ID` can override the defaults. The default points `(320, 480)` and `(640, 480)` were validated on `ZergTest.scm` on this Pi. The headless launcher has no frame pacing of its own; the module waits 42 ms per frame by default and sends one snapshot every three frames, about 8 Hz.

For a headless server plus two headless client integration run:

```bash
STARCRAFT_DATA_DIR=/home/pi/games/starcraft scripts/test-two-clients-headless.py --seconds 65
```

The test uses OpenRCT2's upstream `EverythingPark.park`, the locally built v0.5.5 binaries, `/usr/share/openrct2` as its default headless data path, and separate ignored user directories for both clients. Set `RCT2_DATA_DIR=/home/pi/games/rct2` to use the supplied game graphics here. It compares each common action's OpenRCT2 tick, unit ID, and position across all three participants; logs are retained in `run-data/headless-multiplayer/`. The native patch adds a network tick to the headless client title scene so its join handshake can complete. This headless test does not render a screenshot.

For two live graphical clients on virtual displays, using the game files already present on this Pi:

```bash
python3 scripts/capture-live-demo.py --seconds 65
```

This requires `xvfb` and `scrot`. It starts the real BWAPI launcher, an OpenRCT2 host using the upstream `BigMapTest.sv6` park, and two modified graphical clients on X displays `:91` and `:92`. A local camera helper centres the viewport on the unit for the capture; it changes no shared park state. Screenshots and logs are saved in ignored `run-data/visual-demo/`. To capture a second client with an independently rotated camera, use `DEMO_OUTPUT_DIR=run-data/visual-demo-rotation python3 scripts/capture-live-demo.py --seconds 12 --rotate-client-b`.

OpenBW's checkout has no top-level license file. The separate BWAPI fork carries LGPL-3.0 licensing, but that does not settle OpenBW source or binary redistribution. Neither game data nor proprietary art belongs in the bridge repository.

## Verified on this Pi (2026-10-10)

- Pinned OpenBW/BWAPI configured and built in Release mode with its UI disabled. The build includes `BWAPILauncher` and the supplied `ExampleAIModule`.
- `BridgeAIModule.so` compiled and exported the `gameInit` and `newAIModule` entry points expected by the BWAPI example's factory pattern.
- `BWAPILauncher` loaded the module with the user-provided MPQs, registered a genuine Zergling as unit ID `16`, accepted `Unit::move`, and reported positions changing from `(320, 480)` to `(640, 480)` and back. A 15-second paced run yielded 115 unit snapshots and six accepted waypoint orders with no move errors.
- The receiver passed a fixture stream sent in split TCP writes, confirming newline framing and movement detection in the test tool.
- OpenRCT2 configured and completed its full Release build with GUI, networking, and scripting enabled. Both `openrct2` and `openrct2-cli` report v0.5.5 on Linux AArch64, network version `0.5.5-2`, and plugin API version `124`.
- OpenRCT2's project asset packs were staged locally in `build/openrct2-stage/` without writing to `/usr/local`.
- The v0.5.5 headless OpenRCT2 host opened the upstream `EverythingPark.park` test park and listened on localhost. The user-provided RCT2 data now allows graphical clients to render the park.
- The M1 native paint hook compiled. `g2.dat` contains all 12 original alien scout sprites; the alien scout is visible in the live graphical clients and changes position between screenshots.
- The server's remote plugin connected to the live BWAPI publisher and applied synchronized custom actions to the native presentation registry. Two headless clients joined; 143 shared action logs had exactly matching OpenRCT2 tick, unit ID, and coordinates on server and clients.
- A repeatable 65-second headless run passed with 515 shared snapshots and zero tick/identity/position differences across the server and both clients.
- Stopping and restarting `BWAPILauncher` produced synchronized actor removal on the server and a headless client, followed by a new session epoch and fresh actor snapshots.
- A 65-second run with two graphical clients passed on `BigMapTest.sv6`: server and clients shared 514 matching snapshots with no reported desync. Screenshots show the moving actor on both clients. A shorter run passed with client B's camera rotated independently, with 155 matching snapshots.

## What is not yet proven

- Occlusion against scenery and terrain height transitions have not yet been visually validated. The stable screenshot test uses a broad grass area.
- `EverythingPark.park` produced an OpenRCT2 random-state desync warning in a graphical run. The live bridge passed on `BigMapTest.sv6`; the cause of the `EverythingPark` warning has not been isolated.
