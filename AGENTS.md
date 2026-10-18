# StarCoaster development guide

StarCoaster is a scenario-driven playable game. Start gameplay work in a package under `scenarios/`; reuse the existing objective, wave, native spawn, reinforcement, and command systems before adding bridge or launcher infrastructure. Use `example-defense` as a package example, not as a required mission design. See `.agents/skills/starcoaster-scenario/SKILL.md` for the supported format and its current generator limits.

OpenRCT2 owns the park, scenery, rides, multiplayer state, and rendering. OpenBW owns unit movement, pathfinding, health, and combat. The Go world bridge coordinates snapshots, ordered live park revisions, native synchronization, and commands; adapters and test probes must not duplicate either engine's authority.

## Source map

- `scenarios/`: packaged gameplay configuration and mapping rules.
- `openrct2-plugin/`, `openrct2-patches/`: park synchronization, player controls, and native rendering.
- `openbw-bwapi-module/`: native actors, navigation, and combat bridge.
- `cmd/world-bridge/`, `internal/world/`: transport, world model, spawn queue, and scenario runtime.
- `scripts/`: consolidated CLI, build, park, launcher, and capture implementations; `tests/`: regressions.
- `browser/`, `cmd/wasm-server/`: browser launcher, private static hosting, and fixed OpenRCT2 WebSocket gateway. The WASM client uses the same patched pinned OpenRCT2 source.
- `bridge-protocol/entities/`: authoritative one-file StarCraft unit and building declarations. `bridge-protocol/starcraft-types.json`, `bridge-protocol/starcraft-visuals.json`, and generated Go/C++/JavaScript/protocol registries are derived; never edit them manually. `bridge-protocol/` also holds versioned wire contracts; `docs/archive/` holds historical reports. `upstream/`, `build/`, and `run-data/` hold local inputs or generated outputs.

## Canonical workflow

```sh
scripts/project.sh start --scenario example-defense  # fetch, build, stage, play
scripts/project.sh build                             # rebuild an existing checkout
scripts/project.sh generate                          # regenerate StarCraft catalogs and registries
scripts/project.sh validate-scenario example-defense
scripts/project.sh play example-defense --plan       # inspect resolved paths
scripts/project.sh park example-defense              # force-generate park data
scripts/project.sh play example-defense              # play an existing build
scripts/project.sh test                              # offline regressions
scripts/project.sh test-live                         # licensed native regressions
scripts/project.sh test-live-construction            # focused live construction regressions
scripts/project.sh record --scenario example-defense --duration 85
scripts/project.sh build-wasm                       # patched graphical WASM client
scripts/project.sh test-wasm                        # gateway and bundle checks
scripts/project.sh deploy-wasm                      # private versioned bundle staging
scripts/project.sh serve-wasm                       # local browser server
```

`start`, `park`, and `record` default to `frontier-outpost`; `play` requires an ID. `play` regenerates stale park data and the native map. The CLI resolves packages through `scripts/scenario_package.py` and launches gameplay through `scripts/run-world-session.sh`. Use `scripts/project.sh --help` and subcommand help for current options. Live commands require built engines and locally licensed RCT2 and StarCraft data.

The browser workflow and its verification limits are in `docs/wasm-browser.md`. Keep browser resources private, require local RCT2 import, and preserve the native OpenRCT2 multiplayer protocol and remote plugin path. A WASM build or offline park render does not complete browser gameplay verification; confirm a browser order executes in OpenBW and both client types display the same result.

Use player-facing scenario configuration and the normal `start`/`play` path for features. Keep fault hooks, spawn probes, and diagnostic scripts in tests and verification workflows; do not surface them as player controls. Preserve park footprints, spawn tiles, chokepoints, collision masks, and native routes when changing geometry.

Live park construction uses `world.patch` transactions against the last confirmed revision. OpenRCT2 detects and batches ordinary synchronized actions; Go validates and stages the entire mapped candidate; both OpenBW participants must stage, schedule, and report application at the same native frame before the bridge publishes synchronization. Treat `world.ack` as transport acceptance only. Route confirmed combat demolition through the same ordered revision lifecycle, and keep manual objective removal distinct from native combat destruction. Same-session snapshots recover from the current park without replaying scenario startup or resetting actors, target HP, or spawn journals. See `bridge-protocol/README.md` and `docs/live-construction-milestone.md` for the wire lifecycle, measured runs, and current limits.

Commit coherent increments as work proceeds, with documentation commits separate from unrelated implementation changes. Run relevant offline checks before affected live or graphical checks; select them with `.agents/skills/starcoaster-verify/SKILL.md`. Use `.agents/skills/starcoaster-park-design/SKILL.md` for layout work and `.agents/skills/starcoaster-demo/SKILL.md` for captures. Report commands and pass/fail results, artifact paths, and remaining limits; state missing live dependencies plainly.

Never commit user-supplied RCT2 or StarCraft data, extracted sprites, proprietary graphics, local captures, or bundled engine builds. Follow `docs/licensing.md` and inspect staged paths before each commit.
