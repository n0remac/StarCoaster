# StarCoaster

StarCoaster is a playable RTS encounter inside a real OpenRCT2 park. Six OpenBW Marines defend Frontier Carousel against twelve Zerglings in a deterministic 64 × 64 Frontier Outpost. The player selects Marines, calls in up to five reinforcements through the squad window's Spawn Marine tool, and gives move, attack, attack move, hold, and stop orders in OpenRCT2. OpenBW runs unit movement and combat; the OpenRCT2 server owns the park and native demolition; the Go bridge synchronizes both engines and two clients.

## Build and play

Provide your own licensed RCT2 and classic StarCraft data, then set `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR`. A fresh clone also needs the pinned upstream checkouts from `python3 scripts/fetch-upstream.py`. See the [bootstrap guide](docs/bootstrap.md) for system packages and local sprite options.

The startup script defaults to `~/games/rct2` and `~/games/starcraft`, so with
those installations you can simply run `./scripts/start.sh`. Set the variables
below when your game data is elsewhere.

```sh
export RCT2_DATA_DIR=/path/to/your/rct2
export STARCRAFT_DATA_DIR=/path/to/your/starcraft
scripts/project.sh start
```

`start` fetches the pinned upstream sources, builds both engines and the Go bridge,
stages OpenRCT2 assets under `build/`, regenerates Frontier Outpost from the current
sources, and launches the session. It reuses existing build output on later runs.
Use `start --headless` for the server stack or `start --client` to require a
graphical client. Press Ctrl+C to stop the session. System dependencies must
already be installed; see the bootstrap guide. You can also run
`scripts/start.sh` directly. The separate `build`, `park`, and `run` commands
remain available; run `scripts/install-openrct2-local.sh` after building OpenRCT2
when using those steps manually.
The direct `run` command reuses the generated park unless it is missing or its
generator inputs have changed.

The launcher starts the OpenRCT2 host, OpenBW publisher and controller, and Go bridge. Set `BRIDGE_LAUNCH_CLIENT=1` with a graphical `DISPLAY` to join the local game. Frontier Outpost starts at `run-data/frontier-playable/save/frontier-outpost-playable.park`. Generated parks, extracted art, logs, and recordings stay under ignored `run-data/`.

## Test and record

```sh
scripts/project.sh test
scripts/project.sh test-live
scripts/project.sh record --duration 85
```

`test` runs Go, C++, Python, and JavaScript regressions. `test-live` additionally exercises native navigation, generic park demolition with two clients, Frontier victory, shared-runtime-Marine recovery, and dynamic five-Marine and Zergling spawning. Live tests require built engines and game data. `record` launches two graphical clients and publishes screenshots, video, logs, and verification results to the [artifact viewer](docs/test-viewer.md). Use `--help` on the recorder for capture settings. The [unit spawn report](docs/unit-spawn-verification.md) records reinforcement and recovery evidence; the [shared actor report](docs/shared-actor-verification.md) and [first playable report](docs/first-playable-verification.md) record earlier baselines.

For a lighter capture, use `scripts/project.sh record --video-layout single --video-fps 15 --video-width 800`. The [recording benchmark](docs/recording-performance-v0.2.md) compares 15 and 30 FPS against gameplay without video; the [park design report](docs/park-design-v0.2.md) records the four camera views and geometry checks.

The [v0.2 final verification](docs/final-verification-v0.2.md) records passing build, unit, integration, native navigation, lifecycle, and graphical capture results with artifact paths and remaining limits.

## Project map

- `openrct2-plugin/`, `openrct2-patches/`: park discovery, multiplayer controls, rendering, and demolition.
- `openbw-bwapi-module/`: native actor simulation adapter and navigation updates.
- `cmd/world-bridge/`, `internal/world/`: synchronization, world model, and scenario outcome.
- `scenarios/`: Frontier configuration; `scripts/`: builds, park generation, demos, and captures; `tests/`: regressions.
- `bridge-protocol/`: wire schemas; `docs/archive/`: historical specifications and experiments.

The [world bridge guide](docs/world-bridge.md), [park assault guide](docs/park-assault.md), and [licensing inventory](docs/licensing.md) cover design details and remaining limits. Original CC0 placeholder art is tracked; proprietary game files, extracted sprites, and locally built asset packs are never committed.
