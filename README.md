# StarCoaster

StarCoaster is a playable RTS encounter inside a real OpenRCT2 park. Six OpenBW Marines start on the raised ridge in a deterministic 64 × 64 Frontier Outpost. Twelve Zerglings start on the opposite side, and five more spawn automatically when the world is ready. The player selects Marines, calls in up to five reinforcements through the squad window's Spawn Marine tool, and gives move, attack, attack move, hold, and stop orders in OpenRCT2. OpenBW runs unit movement and combat; the OpenRCT2 server owns the park and native demolition; the Go bridge synchronizes both engines and two clients.

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
./scripts/start.sh --scenario example-defense --client
scripts/project.sh build                          # rebuild an existing checkout
scripts/project.sh play frontier-outpost         # existing build
scripts/project.sh play example-defense
scripts/project.sh play example-defense --plan   # inspect paths without launching
scripts/project.sh park example-defense          # generate park, fixture, navigation
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

The packaged scenario definitions under `scenarios/frontier-outpost/` and
`scenarios/example-defense/` select the park, mapping, starting actors, objectives,
and automatic waves. Frontier has a ready wave, a timed southern wave, and a final
wave after the southern one clears. Example Defense has eastern and western waves.
Manual Marine reinforcements work in both scenarios. The launcher installs the
bridge plugin for both the server and graphical client so native units appear
in the player view.

## Test and record

```sh
scripts/project.sh test
scripts/project.sh test-live
scripts/project.sh record --duration 85
scripts/project.sh record --scenario example-defense --duration 85
```

`test` runs Go, C++, Python, and JavaScript regressions. `test-live` additionally exercises the Frontier ridge and 256×256 native map, generic park demolition with two clients, Frontier victory, shared-runtime-Marine recovery, scenario waves and restart, and dynamic five-Marine and Zergling spawning. Live tests require built engines and game data. `record` launches two graphical clients and publishes screenshots, video, logs, and verification results to the [artifact viewer](docs/test-viewer.md). Frontier recordings retain their specialized visual checks; Example Defense uses scenario identity, native readiness, and client snapshot checks. Use `--help` on the recorder for capture settings, including `--no-video` and the test-only `--ridge-probe`, `--ridge-assault`, and `--world-256` runs. Ridge probes require Frontier; `--world-256` is a separate fixture and cannot be combined with `--scenario`. The [unit spawn report](docs/archive/unit-spawn-verification.md) records reinforcement and recovery evidence; the [shared actor report](docs/archive/shared-actor-verification.md) and [first playable report](docs/archive/first-playable-verification.md) record earlier baselines.

For a lighter capture, use `scripts/project.sh record --video-layout single --video-fps 15 --video-width 800`. The [recording benchmark](docs/recording-performance-v0.2.md) compares 15 and 30 FPS against gameplay without video; the [park design report](docs/park-design-v0.2.md) records the four camera views and geometry checks.

The [world geometry milestone](docs/world-geometry-milestone.md) documents 256×256 maps, terrain-derived navigation, the raised Frontier ridge, live reproduction commands, performance, and limits. The [v0.2 final verification](docs/archive/final-verification-v0.2.md) records the prior build, unit, integration, native navigation, lifecycle, and graphical capture baseline.

## Project map

- `openrct2-plugin/`, `openrct2-patches/`: park discovery, multiplayer controls, rendering, and demolition.
- `openbw-bwapi-module/`: native actor simulation adapter and navigation updates.
- `cmd/world-bridge/`, `internal/world/`: synchronization, world model, and scenario outcome.
- `scenarios/`: packaged missions; `scripts/`: builds, park generation, captures, and diagnostics; `tests/`: regressions.
- `bridge-protocol/`: wire schemas; `docs/archive/`: historical specifications and experiments.

The [world bridge guide](docs/world-bridge.md) and [licensing inventory](docs/licensing.md) cover design details and remaining limits. Earlier demonstrations are in [the archive](docs/archive/README.md). Original CC0 placeholder art is tracked; proprietary game files, extracted sprites, and locally built asset packs are never committed.
