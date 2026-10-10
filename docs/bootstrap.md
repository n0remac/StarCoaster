# Bootstrap and current status

All source repositories live under `upstream/` in this project directory. Their exact revisions are recorded in [`dependencies.lock.json`](../dependencies.lock.json), and `scripts/check-dependencies.py` checks them. Upstream checkouts and build output are excluded from the bridge Git repository.

## Build order

The machine needs CMake, Ninja, GCC 12+, Python 3, and the OpenRCT2 development libraries listed in the [OpenRCT2 Linux build guide](https://github.com/OpenRCT2/OpenRCT2/wiki/Building-OpenRCT2-on-Linux). On this Pi, the dependencies were installed through `apt-get` on 2026-10-10:

```bash
sudo apt-get install --no-install-recommends -y \
  git python3 ninja-build cmake ccache libsdl2-dev libicu-dev pkg-config libcurl4-openssl-dev \
  libcrypto++-dev libfontconfig1-dev libfreetype6-dev libpng-dev \
  libssl-dev libzip-dev build-essential nlohmann-json3-dev \
  libflac-dev libvorbis-dev libzstd-dev
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

Once RCT2 data and a park file are available, start a stock headless host with:

```bash
RCT2_DATA_DIR=/path/to/your/rct2 scripts/run-openrct2-host.sh /path/to/park.park
```

`OPENRCT2_PORT` defaults to `11753`. The server's user data and future remote plugin directory are kept under ignored `run-data/openrct2-server/`.

## OpenBW runtime proof

The runtime needs three **user-supplied** StarCraft data archives: `StarDat.mpq`, `BrooDat.mpq`, and `Patch_rt.mpq`. The pinned BWAPI checkout includes a `ZergTest.scm` map that the launcher uses by default; `BRIDGE_MAP_FILE` can select another `.scm` or `.scx` map. The project does not download or commit the MPQs. `scripts/run-bwapi.sh` accepts the alternate README spelling `Stardat.mpq` / `Broodat.mpq` and creates ignored symlinks with the [exact names used by the pinned OpenBW loader](https://github.com/OpenBW/openbw/blob/4b046d5f65302b10cb0a745f0fecd37ec85b20a8/data_loading.h#L1322-L1324) in `run-data/openbw/`. The [BWAPI fork README](https://github.com/OpenBW/bwapi/blob/develop-openbw/README.md) names MPQs from StarCraft 1.16.1 or 1.18. Blizzard's [current free StarCraft installation](https://us.support.blizzard.com/en/article/troubleshooting-starcraft-or-brood-war-patches) is available through Battle.net, but [Blizzard support says the post-1.16.1 game data was repackaged](https://us.forums.blizzard.com/en/starcraft/t/missing-files-for-campaign-editor/3655); the current download alone does not provide the MPQs this fork expects.

In one terminal:

```bash
STARCRAFT_DATA_DIR=/path/to/your/starcraft scripts/run-bwapi.sh
```

In another terminal:

```bash
scripts/receive-snapshots.py --seconds 30
```

The receiver passes only after it sees the published unit position change. `BRIDGE_SPAWN_X`, `BRIDGE_SPAWN_Y`, `BRIDGE_TARGET_X`, `BRIDGE_TARGET_Y`, `BRIDGE_PUBLISH_PORT`, and `BRIDGE_MAP_ID` can override the defaults. Pick two clear walkable coordinates on the selected map; the default points `(320, 480)` and `(640, 480)` are illustrative and remain unverified on `ZergTest.scm`.

OpenBW's checkout has no top-level license file. The separate BWAPI fork carries LGPL-3.0 licensing, but that does not settle OpenBW source or binary redistribution. Neither game data nor proprietary art belongs in the bridge repository.

## Verified on this Pi (2026-10-10)

- Pinned OpenBW/BWAPI configured and built in Release mode with its UI disabled. The build includes `BWAPILauncher` and the supplied `ExampleAIModule`.
- `BridgeAIModule.so` compiled and exported the `gameInit` and `newAIModule` entry points expected by the BWAPI example's factory pattern.
- The receiver passed a fixture stream sent in split TCP writes, confirming newline framing and movement detection in the test tool.
- OpenRCT2 configured and completed its full Release build with GUI, networking, and scripting enabled. Both `openrct2` and `openrct2-cli` report v0.5.5 on Linux AArch64, network version `0.5.5-2`, and plugin API version `124`.
- OpenRCT2's project asset packs were staged locally in `build/openrct2-stage/` without writing to `/usr/local`.

## What is not yet proven

- The launcher still needs to load the custom module and simulate actual movement. The older MPQs are needed for that proof; the bundled BWAPI test map and default spawn/target points have not yet been validated together.
- [OpenRCT2 needs user-supplied RCT2 or RCT Classic game assets](https://docs.openrct2.io/en/latest/faq/installing.html) to run. Its native rendering hook and server plugin are future milestones.
