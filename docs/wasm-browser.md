# StarCoaster browser client

The browser target uses the pinned OpenRCT2 Emscripten build and the existing StarCoaster patch reconciler. The browser bundle is private: its `assets.zip` contains the same patched `g2.dat`, StarCraft sprite and building art, and staged OpenRCT2 resources as the native build. On the private Pi host, the launcher fetches RCT2 data from the Pi's locally licensed installation and stores it in the browser's IndexedDB. No asset selection on the laptop is needed.

## Build and stage

```sh
scripts/project.sh prepare-wasm-arm64                  # once, on the Pi build drive
OPENRCT2_WASM_LOCAL=1 scripts/project.sh build-wasm    # separate WASM CMake tree
scripts/project.sh test-wasm                           # artifact, socket, browser checks
scripts/project.sh deploy-wasm                         # atomic private bundle update
scripts/project.sh start --scenario frontier-outpost --browser
```

`start --browser` combines the native build, WASM build, private staging, scenario launch, and local browser server for development. The browser opens at its main menu; the explicit live test opts into joining the development host. To use an existing build, set `BRIDGE_SERVE_WASM=1` and run `scripts/project.sh play frontier-outpost`; the scenario launcher passes `RCT2_DATA_DIR` to the browser server. `scripts/project.sh serve-wasm --bundle run-data/wasm-deploy/current --rct2-data-path /path/to/licensed/RCT2` serves the app without starting a scenario. On the Pi with a workstation-built bundle, use `scripts/project.sh start --scenario frontier-outpost --browser-bundle /path/to/copied-bundle`. To update the browser bundle during a game, build and deploy it separately; `deploy-wasm` changes a symlink and leaves the OpenRCT2 server, Go bridge, and OpenBW processes running. Reload an existing browser tab to use new files.

The build writes `build/openrct2-wasm/` and `build/wasm-client/`. The bundle contains a versioned `manifest.json` recording the pinned OpenRCT2 commit, patch digest, native bridge version 5, asset version 4, plugin API version 124, generated declaration digests, and browser artifact digests. `scripts/verify-wasm-bundle.py` checks artifact integrity. Generated building objects and `assets.zip` have fixed ZIP timestamps; repeated packaging must produce identical hashes. `build/` and `run-data/` are ignored; never commit the bundle, ZIP files, game data, or extracted images.

## Managed Pi game and updates

The Pi user service in `deploy/starcoaster-game.service` now starts the private browser server without selecting a park. Install it once with `scripts/install-pi-game-service.sh`, then run `scripts/update-pi-game.sh --force` for the first deployment. The installer creates an ignored private park library and a bare Git repository at `run-data/pi-push.git` with a `post-receive` hook. The browser server listens on loopback port 8091; a native multiplayer host uses loopback port 11753 when one is running. Keep the existing private Tailscale Serve route on port 10001; do not enable Funnel for it.

The browser starts at OpenRCT2's normal main menu, with the native New Game and Load Game interfaces. Its packaged StarCoaster plugin is hash checked and installed in the browser's persistent OpenRCT2 user directory. On a managed Pi host, selecting a stock scenario or save requests a new authoritative generation. The browser uploads a selected save to a private temporary directory when needed, waits for OpenRCT2, OpenBW, and Go readiness, and joins through the existing `/ws` multiplayer gateway without reloading the page. No session token or extra login is required after opening the private Tailscale URL. Explicit scenario sessions and the `starcoaster-test-join` URL parameter remain available for development.

The browser control routes are `/private/park-session` for status and `/private/park-session/{load,upload,cancel,title}` for changes. Changes require a matching origin and are available to clients that can reach the private Tailscale URL; `/ws` remains the ordinary OpenRCT2 multiplayer transport. Scenario names are matched against the Pi's installed `RCT2_DATA_DIR/Scenarios` and private library, never interpreted as client paths. Save uploads are limited to 64 MiB, accept the supported `.park`, `.sc6`, `.sc4`, `.sv6`, and `.sv4` formats, and pass OpenRCT2 preflight before the old game is stopped. An invalid replacement leaves the current generation running. A native client launched through `scripts/project.sh launch` detects the local supervisor; a remote native client needs `STARCOASTER_CONTROL_URL` and `STARCOASTER_MULTIPLAYER_HOST` configured.

For an idle Pi browser run, start the installed `starcoaster-game.service` or run `RCT2_DATA_DIR=/path/to/rct2 STARCRAFT_DATA_DIR=/path/to/starcraft python3 scripts/park_session_supervisor.py --parks run-data/pi-park-library --runtime run-data/park-supervisor` after the native and WASM builds. Select New Game in OpenRCT2, choose a stock scenario, and wait for the automatic join. The private browser service stays up during preparation and map transitions. `WASM_NORMAL_HANDOFF=1 WASM_LIVE_URL=http://127.0.0.1:8091/ node browser/live-test.mjs` drives the first-game path in Chromium; add `WASM_LIVE_CAMERA=1 WASM_DEFENSE_CONFIGURE=1 WASM_DEFENSE_BUILD=1 WASM_DEFENSE_MANUAL=1 WASM_AUTO_ORDER=1` to verify Barracks construction, OpenBW Marine training, Defense control, and a viewport order.

To exercise Load Game and Quit to menu in the graphical browser, set `WASM_HANDOFF_LOAD_SAVE_FILE` to a local `.park` autosave and `WASM_HANDOFF_RETURN_TITLE=1` alongside `WASM_NORMAL_HANDOFF=1`. The probe selects New Game, uploads the save through OpenRCT2's Load Game picker, waits for a distinct authoritative generation and scenario status, then returns the supervisor to idle. A Pi run passed this flow without a token; its ignored log is `build/tokenless-browser-save-title-retry.log`, with screenshots under `build/wasm-live-test/`. The rebuilt native client also selected Electric Fields from the normal menu, joined the authoritative host, and returned to the title screen without a token; its ignored log and captures are `build/tokenless-native-owner.log` and `run-data/handoff-graphical-20261019/native-tokenless-*.png`.

A dense stock scenario reproduced two native limits during preflight. `Six Flags Great Adventure.SC6` is 256 × 256 and exports 65,536 terrain tiles, 29,873 entities, 1,457 world snapshot chunks (24,542,537 JSON bytes, largest 86,271 bytes), and 131,072 collision bytes in 22 chunks. OpenBW first failed with `too many regions (nooks and crannies)` because its region allocation was capped below the IDs reserved by its own map representation. The native region cap now follows that representation's reserved index. After that fix, the producer could outrun the OpenBW socket consumer during initial synchronization; bounded per-frame reads and normal TCP backpressure removed the disconnect without dropping collision or scenery data. `python3 tests/test_dense_stock_handoff_live.py` completed native preflight in 105.227 seconds; its ignored report and detailed log are under `run-data/dense-stock-handoff-1792457269/`. Maps larger than the current 256 × 256 OpenBW representation still receive an explicit unsupported-map error.

From a development machine with SSH access to the Pi, add the private push remote and send `main`:

```sh
git remote add pi ssh://pi@raspberrypi.tail628049.ts.net/media/pi/media1/rts-bridge/run-data/pi-push.git
git push pi main
```

For a single `git push origin main` to update GitHub and the Pi from a clone,
configure both push destinations once in that clone:

```sh
git config remote.origin.pushurl git@github.com:n0remac/StarCoaster.git
git config --add remote.origin.pushurl ssh://pi@raspberrypi.tail628049.ts.net/media/pi/media1/rts-bridge/run-data/pi-push.git
git push origin main
```

Push URLs are local Git configuration; repeat this setup in each clone that
should deploy. A GitHub-only push does not reach the private Pi hook.

The receive hook runs the update once after each push to the Pi's `main`. It
fast-forwards a clean checkout, builds the native engines and ARM64 WASM bundle
from the configured licensed installations, runs `scripts/project.sh test` and
`scripts/project.sh test-wasm`, atomically deploys the verified private bundle,
and restarts `starcoaster-game.service`. It records the deployed commit in
ignored `run-data/pi-deployed-revision` only after the service and browser
manifest remain healthy for 30 seconds. The push command waits for this work
to finish; a failed build or test leaves the running game in place, and the
next push or `scripts/update-pi-game.sh --from-push` retries it. The update
refuses local uncommitted changes or diverged history; inspect ignored
`build/pi-update-service.log` to resolve either case. Existing browser tabs
need a reload after deployment.

Use `systemctl --user status starcoaster-game.service` for live status, `build/pi-update-service.log` for update output, and `build/wasm-playable-session.log` for explicit scenario startup details. The Pi needs the local ARM64 WASM toolchain prepared with `scripts/project.sh prepare-wasm-arm64`.

On amd64 Linux, `build-wasm` uses OpenRCT2's pinned `ghcr.io/openrct2/openrct2-build:26-emscripten` image. The image contains Emscripten builds of ICU, libzip, and zstd under `/ext`. On ARM64, `prepare-wasm-arm64` installs pinned Emscripten 5.0.0, ICU, libzip, zstd, zlib, and OpenSSL under ignored `build/` on the attached USB drive. `BRIDGE_BUILD_JOBS=1` can reduce peak memory. The Pi 5 has compiled and linked the network-enabled graphical client with this toolchain. If another Pi lacks sufficient build resources, build on an amd64 Linux checkout of this commit, copy only `build/wasm-client/` to the Pi, and run `scripts/project.sh deploy-wasm /path/to/copied-bundle`. Deployment checks the browser bundle against the Pi's native source and staged assets. The Pi remains the game host.

## Private access

The browser server binds `127.0.0.1:8091` and forwards `/ws` only to `127.0.0.1:11753`. It requires a same-origin browser WebSocket request and never accepts an arbitrary TCP destination. The native OpenRCT2 host already binds loopback. Keep ports 40010, 11753, and the OpenBW sockets private. Startup refuses a listener targeted by an active public Tailscale Funnel route.

After confirming Tailscale access controls admit only intended players, use [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve) on the Pi:

```sh
sudo tailscale serve --bg --yes --https=10001 127.0.0.1:8091
tailscale serve status
```

Open the displayed private `https://…ts.net:10001/` address in desktop Chromium. The server sends `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, and `application/wasm` for WASM files. HTTPS and WSS share one origin. Do not use Tailscale Funnel for this bundle.

The Pi server exposes an allowlisted `/private/rct2/manifest.json` and `/private/rct2/files/` route only when a licensed RCT2 directory is configured. The launcher verifies each downloaded file's size and SHA-256, then persists it in that browser origin's IndexedDB. The first private visit transfers about 686 MB automatically; later visits reuse the stored files. The StarCraft graphics are already in the private `assets.zip`, so neither game's art needs to be selected on the laptop. No RCT2 files are put in the WASM bundle. A development server without a configured RCT2 directory still offers local folder or ZIP import. Missing assets, failed downloads, incompatible versions, and IndexedDB failures appear in the startup status and console. The HTML and launcher script use `Cache-Control: no-store`; if an older open tab still displays the import prompt, reload it once with Ctrl+Shift+R.

## Verification status

`test-wasm` runs gateway tests, a Chromium socket probe, bundle validation, browser initialization, and missing/incompatible asset checks. It reports **BLOCKED** if there is no compiled WASM bundle. For the private Pi route, set `WASM_PRIVATE_RCT2=1`, `WASM_RCT2_DIR` to the licensed Pi directory, `WASM_TEST_URL` to the Tailscale HTTPS link, and `WASM_TEST_PROFILE` to an ignored USB-backed Chromium profile before running `node browser/test.mjs`; the test checks that startup succeeds without an import prompt. A repeated run with the same profile checks IndexedDB reuse. Set `WASM_PARK_FILE` for the separate local park callback check. For a repeatable command demonstration, prepare `scenarios/wasm-mixed-client/` as described in its README, then run `BRIDGE_SERVE_WASM=1 BRIDGE_LAUNCH_CLIENT=0 scripts/project.sh play wasm-mixed-client`. The live test opens with its test-only join parameter; start it before a graphical native client to give it the scenario's existing commander role. Set `WASM_LIVE_URL` to the private HTTPS origin and `WASM_LIVE_PROFILE` to the same profile, then set `WASM_LIVE_CAMERA=1` and `WASM_AUTO_ORDER=1`. The automation selects a visible Marine and right-clicks a destination through the existing viewport controls. Disconnect and rerun against the same host to check reconnect; do not restart `play` between browser runs. The live test records screenshots and runtime data under `build/wasm-live-test/`; the park callback check writes `build/wasm-browser-test/park.png` when it completes. Licensed files and captures stay under ignored directories.

The constrained `/ws` gateway preserves OpenRCT2's original TCP packets and authentication. The Emscripten socket probe exercises nonblocking `connect`, `select`, `getsockopt`, and bidirectional binary traffic. The patch to the shared socket abstraction accepts a connection that completes immediately in Emscripten. `DISABLE_NETWORK=OFF` is the default; use `OPENRCT2_WASM_NETWORK=0` only for a diagnostic offline build. Browser clients receive the existing server-distributed remote plugin. Its readiness handshake can replay the last actor snapshot when a late client joins after actor updates have stopped.

On the Pi 5, a network-enabled 17.1 MB WASM executable and a 70.2 MB private asset ZIP built successfully. Chromium authenticated over private HTTPS/WSS, downloaded the park and remote plugin, and rendered native Marine and Zerg sprites, health bars, buildings, scenery, and the existing RTS UI. In the mixed-client run, a browser viewport selection and right-click produced an accepted `unit.move` in OpenBW; browser and native OpenRCT2 clients displayed Marine `openbw:1000` at the same resulting coordinates. In a same-session reconnect run, the browser issued another accepted move after rejoining, and a further move while the native client was connected. The browser recorded 1.1–1.5 second command-to-actor motion latency and roughly 24–28 animation frames per second on the Pi. Evidence is in ignored USB-backed `build/wasm-mixed-command-proof/`, `build/wasm-reconnect-proof/`, and `build/wasm-private-wss-proof/`. Cold Pi Chromium indexing of 2,540 OpenRCT2 objects took about three minutes; desktop Chromium is the deployment target. The linker still reports a `RideMusicGetTrackOffsetLength_Default` function-signature warning inherited from two upstream call sites; normal park and live rendering continued, but ride audio needs a focused check.

The browser also opened the existing Barracks inspector and trained a Marine through the native OpenBW production path. OpenBW accepted `unit.train`, and the browser received the synchronized accepted result. The server replays cached native building and resource states when a late browser plugin signals readiness; the production check waits until the inspector enables its command before clicking. The training request counter is seeded from the clock within the native 32-bit request field, so a reconnect does not reuse the previous command ID. Evidence is in ignored `build/wasm-production-proof/passed/` and `build/wasm-browser-production-diagnostic.log`.

A browser construction run then used the existing StarCraft toolbar to select a Barracks and click a valid park site. OpenRCT2 accepted the scenery placement, the Go bridge published park revision 2, and OpenBW linked a new Terran Barracks proxy at that revision. This run used the same Pi host after the training client disconnected. Screenshots, browser runtime data, and the native patch log are in ignored `build/wasm-construction-proof/`.

A later browser reconnect issued the existing synchronized `largesceneryremove` action against the Armory through a test-only shortcut. OpenRCT2 accepted the action, the Go bridge published park revision 7, and OpenBW retired the Armory target as `manual_removed`. The shortcut only drives the existing native game action for verification; it is not part of the player UI. Evidence is in ignored `build/wasm-demolition-proof/`. The versioned bundle was rebuilt and deployed between these runs while the native OpenRCT2 and OpenBW processes stayed active. Private HTTPS continued to serve the updated manifest and WASM with the required isolation headers.

One heavily reused Pi Chromium profile stalled at module initialization after an earlier bundle update. A fresh USB-backed profile passed graphical startup, then joined the same live native session for demolition. The cause of the reused-profile stall is not isolated. After private Pi provisioning was added, a fresh Chromium profile loaded 2,465 RCT2 files over the exact Tailscale HTTPS origin with no local import prompt; a repeated run reused them. A live run on that origin loaded the remote RTS plugin, received a seven-actor snapshot including Marine `openbw:1000`, and logged no browser errors. Logs are in ignored USB-backed `build/wasm-private-https-browser.log`, `build/wasm-private-https-repeat.log`, and `build/wasm-private-https-starcraft-graphics.log`; screenshots and runtime data are in `build/wasm-live-test/`. Browser startup, renderer, and cache behavior should also be checked on the desktop Chromium deployment target before relying on in-place upgrades for active browser tabs.

An optional Chromium input probe can be run with `WASM_LIVE_CAMERA=1 WASM_CONTROL_PROBE=1 node browser/live-test.mjs` against the prepared mixed-client scenario. It drives rectangle selection, Shift selection, Alt park interaction, attack-move, stop, and hold through the existing plugin controls. This probe has **not passed** on the Pi: one run reached all six actor screen positions but stopped on a test log parser error, and later runs stalled before a native snapshot or reported `No data received recently from connection` after the server granted operator permissions. The parser is fixed and the probe now fails early on a WebSocket disconnect. Logs are under ignored `build/wasm-browser-controls*.log`, `build/wasm-controls-session*.log`, and `build/wasm-controls-server*.log`. Repeat this probe in desktop Chromium before claiming those controls verified. The separately recorded browser single selection, right-click move, construction, production, and demolition checks passed.
