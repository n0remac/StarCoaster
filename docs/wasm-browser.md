# StarCoaster browser client

The browser target uses the pinned OpenRCT2 Emscripten build and the existing StarCoaster patch reconciler. The browser bundle is private: its `assets.zip` contains the same patched `g2.dat` and staged OpenRCT2 resources as the native build, which may include art extracted from a player's licensed StarCraft installation. RCT2 game data is imported by each player in the browser and stored in IndexedDB.

## Build and stage

```sh
scripts/project.sh start --scenario frontier-outpost --headless # native stack and local assets
scripts/project.sh build-wasm                          # separate WASM CMake tree
scripts/project.sh test-wasm                           # gateway and artifact checks
scripts/project.sh deploy-wasm                         # atomic private bundle update
scripts/project.sh serve-wasm --bundle run-data/wasm-deploy/current
```

`start --browser` combines the native build, WASM build, private staging, scenario launch, and local browser server. It requires a working WASM toolchain. On the Pi with a workstation-built bundle, use `scripts/project.sh start --scenario frontier-outpost --browser-bundle /path/to/copied-bundle`. To update the browser bundle during a game, build and deploy it separately; `deploy-wasm` changes a symlink and leaves the OpenRCT2 server, Go bridge, and OpenBW processes running. An existing browser tab must be reloaded to use new files.

The build writes `build/openrct2-wasm/` and `build/wasm-client/`. The bundle contains a versioned `manifest.json` recording the pinned OpenRCT2 commit, patch digest, native bridge version 5, asset version 4, plugin API version 124, generated declaration digests, and browser artifact digests. `scripts/verify-wasm-bundle.py` checks artifact integrity. `build/` and `run-data/` are ignored; never commit the bundle, ZIP files, game data, or extracted images.

On amd64 Linux, `build-wasm` uses OpenRCT2's pinned `ghcr.io/openrct2/openrct2-build:26-emscripten` image. The image contains Emscripten builds of ICU, libzip, and zstd under `/ext`. On ARM64, set `OPENRCT2_WASM_LOCAL=1` and provide equivalent cross-compiled dependencies through `OPENRCT2_WASM_DEPS`; `BRIDGE_BUILD_JOBS` can reduce peak memory. If the Pi cannot compile the client, run the same command on an amd64 Linux checkout of this commit, copy only `build/wasm-client/` to the Pi, and run `scripts/project.sh deploy-wasm /path/to/copied-bundle`. Deployment checks the browser bundle against the Pi's native source and staged assets. The Pi remains the game host.

## Private access

The browser server binds `127.0.0.1:8080` and forwards `/ws` only to `127.0.0.1:11753`. It requires a same-origin browser WebSocket request and never accepts an arbitrary TCP destination. The native OpenRCT2 host already binds loopback. Keep ports 40010, 11753, and the OpenBW sockets private.

After confirming Tailscale access controls admit only intended players, use [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve) on the Pi:

```sh
tailscale serve --bg --https=443 127.0.0.1:8080
tailscale serve status
```

Open the displayed private `https://…ts.net/` address in desktop Chromium. The server sends `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, and `application/wasm` for WASM files. HTTPS and WSS share one origin. Do not use Tailscale Funnel for this bundle.

The local RCT2 import expects a ZIP containing `Data/ch.dat` or `RCT/Data/ch.dat`. No RCT2 files are put in the bundle. Missing assets, failed downloads, incompatible manifest versions, and IndexedDB failures appear in the browser's startup status and console.

## Verification status

`test-wasm` runs the gateway test and static launcher check. It reports **BLOCKED** if there is no compiled WASM bundle; this is not a successful browser test. The gateway test uses a local TCP echo server to verify binary forwarding, response headers, and origin rejection. A graphical and mixed-client run still requires a successful WASM build, licensed RCT2 and StarCraft files, working browser networking, and Chromium capture. The initial build keeps upstream `DISABLE_NETWORK=ON`; remote plugin transfer, actor rendering, browser commands, and reconnect have not passed until networking is enabled and live checks are recorded.

[Emscripten documents](https://emscripten.org/docs/porting/networking.html#emulated-posix-tcp-sockets-over-websockets) that its WebSocket-backed POSIX TCP sockets are incomplete, and OpenRCT2's native socket implementation uses nonblocking `connect`, `getsockopt`, and `select`. Test those calls against `/ws` before enabling multiplayer. If the emulation fails, adapt the implementation behind OpenRCT2's existing `ITcpSocket` interface while preserving its packet format. Do not route multiplayer through the Go bridge.

On the current Raspberry Pi 5, `build-wasm` cannot enter the upstream container because it has no ARM64 image. A local Debian Emscripten installation was attempted on 2026-10-18 but stopped when the root partition had about 467 MB free against an estimated 1.4 GB installed size; the interrupted package was removed and `dpkg` repaired. The Pi also lacks the cross-compiled ICU, libzip, and zstd tree expected by the pinned OpenRCT2 build. The supported next build attempt is an amd64 Linux workstation using the upstream image, followed by `--browser-bundle` on the Pi. No WASM executable, browser screenshot, or mixed-client verification artifact exists yet.
