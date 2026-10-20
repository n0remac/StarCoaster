# StarCoaster

StarCoaster is a playable RTS encounter inside a real OpenRCT2 park. Its packaged missions include Frontier Outpost, Example Defense, and Midway Junction. The player selects Marines, calls in up to five reinforcements per Spawn Marine request, and gives move, attack, attack move, hold, and stop orders in OpenRCT2. OpenBW runs unit movement and combat; the OpenRCT2 server owns the park and native demolition; the Go bridge synchronizes both engines and two clients.

The native `scripts/project.sh launch` command and private browser app start at OpenRCT2's standard main menu. New Game and Load Game use OpenRCT2's normal interfaces. On a managed Pi host, selecting a stock scenario or save prepares a fresh authoritative OpenRCT2, OpenBW, and Go session; the graphical client joins it through OpenRCT2 multiplayer without asking for a session token. Explicit `play` commands remain available for packaged missions and development.

## Build and play

Provide your own licensed RCT2 and classic StarCraft data, then set `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR`. A fresh clone also needs the pinned upstream checkouts from `python3 scripts/fetch-upstream.py`. See the [bootstrap guide](docs/bootstrap.md) for system packages and local sprite options.

The startup script defaults to `~/games/rct2` and `~/games/starcraft`, so with
those installations you can run `./scripts/start.sh`. Set the variables below
when your game data is elsewhere.

```sh
export RCT2_DATA_DIR=/path/to/your/rct2
export STARCRAFT_DATA_DIR=/path/to/your/starcraft
scripts/project.sh start --scenario frontier-outpost # full bootstrap
scripts/project.sh start --scenario example-defense
scripts/project.sh start --scenario midway-junction
./scripts/start.sh --scenario example-defense --client
scripts/project.sh build                          # rebuild an existing checkout
scripts/project.sh play frontier-outpost         # existing build
scripts/project.sh play example-defense
scripts/project.sh play midway-junction
scripts/project.sh launch                        # native OpenRCT2 main menu
scripts/project.sh serve-wasm                    # private browser menu, no initial park
scripts/project.sh play example-defense --plan   # inspect paths without launching
scripts/project.sh park example-defense          # generate park, fixture, navigation
scripts/project.sh park midway-junction
```

`start` fetches the pinned upstream sources, extracts Marine and Zergling sprites
from your local StarCraft archives, builds both engines and the Go bridge,
stages OpenRCT2 assets under `build/`, and launches the selected scenario. The
`play` command uses an existing build and generates a stale park and its native
map before starting the world session. `park [ID]` force-generates only the park,
fixture, and navigation data. These commands default to Frontier Outpost where
an ID is optional.
It selects `BRIDGE_SPRITE_SOURCE=starcraft-local` by default. Set
`BRIDGE_SPRITE_SOURCE=alien-scout` explicitly to use the original placeholder art.
Use `start --headless` for the server stack or `start --client` to require a
graphical client. Press Ctrl+C to stop the session. System dependencies must
already be installed; see the bootstrap guide. You can also run
`scripts/start.sh` directly. The separate `build` and `park` commands
remain available. Run
`scripts/install-openrct2-local.sh` after building OpenRCT2 when using those
steps manually.

The launcher starts the OpenRCT2 host, OpenBW publisher and controller, and Go bridge. Set `BRIDGE_LAUNCH_CLIENT=1` with a graphical `DISPLAY` to join the local game. Frontier Outpost starts at `run-data/frontier-playable/save/frontier-outpost-playable.park`. Generated parks, extracted art, logs, and recordings stay under ignored `run-data/`.

For normal menu selection on the Pi, run the managed service described in the [browser workflow](docs/wasm-browser.md), or start `scripts/park_session_supervisor.py --parks run-data/pi-park-library --runtime run-data/park-supervisor` after building and staging. Keep `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR` set. The service starts idle and keeps the private browser origin available while games change. `scripts/project.sh launch` detects the local supervisor; for a remote native client, configure `STARCOASTER_CONTROL_URL` and the multiplayer host address explicitly. The supervisor accepts `.park`, `.sc6`, `.sc4`, `.sv6`, and `.sv4` files from its private library and resolves stock `.SC6` scenarios from the installed RCT2 directory. A selected save is uploaded into an isolated temporary directory and validated with OpenRCT2 before activation.

The packaged scenario definitions under `scenarios/frontier-outpost/`,
`scenarios/example-defense/`, and `scenarios/midway-junction/` select the park,
mapping, starting actors, objectives, and automatic waves. Frontier has a ready
wave, a timed southern wave, and a final wave after the southern one clears.
Example Defense has eastern and western waves. Midway Junction uses an independent
64 × 64 layout with a Ferris wheel objective and east, north, and south attacks.
Manual Marine reinforcements work in all three scenarios. The launcher installs the
bridge plugin for both the server and graphical client so native units appear
in the player view.

Click or drag to select Marines while using the normal OpenRCT2 cursor to open
rides, shops, guests, staff, and vehicles. Hold Alt when clicking a park object
beneath a Marine. Right-click gives a squad order when Marines are selected;
Alt-right-click uses OpenRCT2's usual context interaction. Construction and
reinforcement placement tools retain their clicks. The Select button or
Ctrl+Shift+U cancels the active tool and returns to ordinary park interaction
with unit selection available.

## Test and record

```sh
scripts/project.sh test
scripts/project.sh test-live
scripts/project.sh record --duration 85
scripts/project.sh record --scenario example-defense --duration 85
scripts/project.sh record --scenario midway-junction --duration 120
```

`test` runs Go, C++, Python, and JavaScript regressions. `test-live` exercises native movement, demolition, Frontier's scenario runtime, recovery, and dynamic spawning. The Frontier scenario runtime test is Frontier-specific; run `python3 tests/test_midway_scenario_live.py --mode victory` and `--mode defeat` for Midway's outcomes and two-client checks. Use `NAV_SCENARIO=midway-junction tests/test_frontier_native_navigation_live.sh` for its gate route. Live tests require built engines and game data. `record` launches two graphical clients and publishes screenshots, video, logs, and verification results to the [artifact viewer](docs/test-viewer.md). Frontier recordings retain their specialized visual checks; the other packages use scenario identity, native readiness, and client snapshot checks. Use `--help` on the recorder for capture settings. The [Midway Junction verification report](docs/midway-junction-verification.md) records its geometry, gameplay, and graphical results. The [unit spawn report](docs/archive/unit-spawn-verification.md) records reinforcement and recovery evidence; the [shared actor report](docs/archive/shared-actor-verification.md) and [first playable report](docs/archive/first-playable-verification.md) record earlier baselines.

For a lighter capture, use `scripts/project.sh record --video-layout single --video-fps 15 --video-width 800`. The [recording benchmark](docs/recording-performance-v0.2.md) compares 15 and 30 FPS against gameplay without video; the [park design report](docs/park-design-v0.2.md) records the four camera views and geometry checks.

The [world geometry milestone](docs/world-geometry-milestone.md) documents 256×256 maps, terrain-derived navigation, the raised Frontier ridge, live reproduction commands, performance, and limits. The [v0.2 final verification](docs/archive/final-verification-v0.2.md) records the prior build, unit, integration, native navigation, lifecycle, and graphical capture baseline.

## Project map

- `openrct2-plugin/`, `openrct2-patches/`: park discovery, multiplayer controls, rendering, and demolition.
- `openbw-bwapi-module/`: native actor simulation adapter and navigation updates.
- `cmd/world-bridge/`, `internal/world/`: synchronization, world model, and scenario outcome.
- `scenarios/`: packaged missions; `scripts/`: builds, park generation, captures, and diagnostics; `tests/`: regressions.
- `bridge-protocol/`: wire schemas; `docs/archive/`: historical specifications and experiments.

The [world bridge guide](docs/world-bridge.md) and [licensing inventory](docs/licensing.md) cover design details and remaining limits. Earlier demonstrations are in [the archive](docs/archive/README.md). Original CC0 placeholder art is tracked; proprietary game files, extracted sprites, and locally built asset packs are never committed.

The [browser client workflow](docs/wasm-browser.md) builds the same patched OpenRCT2 graphical client for WebAssembly and stages a private, versioned bundle on the Pi. `scripts/project.sh build-wasm`, `test-wasm`, `deploy-wasm`, and `serve-wasm` are the dedicated commands. The Pi 5 has built the network-enabled client on its attached USB drive; Chromium has loaded an RCT2 park and joined a native Pi-hosted StarCoaster game with the existing remote RTS plugin. The private Pi host automatically serves licensed RCT2 data and staged StarCraft graphics to the browser, with no laptop asset import. Browser Marine movement and Barracks training reached OpenBW, and native and browser clients displayed the same moved actor after a reconnect. See the workflow guide for private HTTPS access, test commands, and captured evidence.
