# StarCoaster development guide

StarCoaster is a scenario-driven playable game. Start gameplay work in a package under `scenarios/`; reuse the existing objective, wave, native spawn, reinforcement, and command systems before adding bridge or launcher infrastructure. Use `example-defense` as a package example, not as a required mission design. See `.agents/skills/starcoaster-scenario/SKILL.md` for the supported format and its current generator limits.

OpenRCT2 owns the park, scenery, rides, multiplayer state, and rendering. OpenBW owns unit movement, pathfinding, health, and combat. The Go world bridge coordinates snapshots and commands; adapters and test probes must not duplicate either engine's authority.

## Source map

- `scenarios/`: packaged gameplay configuration and mapping rules.
- `openrct2-plugin/`, `openrct2-patches/`: park synchronization, player controls, and native rendering.
- `openbw-bwapi-module/`: native actors, navigation, and combat bridge.
- `cmd/world-bridge/`, `internal/world/`: transport, world model, spawn queue, and scenario runtime.
- `scripts/`: consolidated CLI, build, park, launcher, and capture implementations; `tests/`: regressions.
- `bridge-protocol/`: versioned wire contracts; `docs/archive/`: historical reports. `upstream/`, `build/`, and `run-data/` hold local inputs or generated outputs.

## Canonical workflow

```sh
scripts/project.sh start --scenario example-defense  # fetch, build, stage, play
scripts/project.sh build                             # rebuild an existing checkout
scripts/project.sh validate-scenario example-defense
scripts/project.sh play example-defense --plan       # inspect resolved paths
scripts/project.sh park example-defense              # force-generate park data
scripts/project.sh play example-defense              # play an existing build
scripts/project.sh test                              # offline regressions
scripts/project.sh test-live                         # licensed native regressions
scripts/project.sh record --scenario example-defense --duration 85
```

`start`, `park`, and `record` default to `frontier-outpost`; `play` requires an ID. `play` regenerates stale park data and the native map. The CLI resolves packages through `scripts/scenario_package.py` and launches gameplay through `scripts/run-world-session.sh`. Use `scripts/project.sh --help` and subcommand help for current options. Live commands require built engines and locally licensed RCT2 and StarCraft data.

Use player-facing scenario configuration and the normal `start`/`play` path for features. Keep fault hooks, spawn probes, and diagnostic scripts in tests and verification workflows; do not surface them as player controls. Preserve park footprints, spawn tiles, chokepoints, collision masks, and native routes when changing geometry.

Commit coherent increments as work proceeds, with documentation commits separate from unrelated implementation changes. Run relevant offline checks before affected live or graphical checks; select them with `.agents/skills/starcoaster-verify/SKILL.md`. Use `.agents/skills/starcoaster-park-design/SKILL.md` for layout work and `.agents/skills/starcoaster-demo/SKILL.md` for captures. Report commands and pass/fail results, artifact paths, and remaining limits; state missing live dependencies plainly.

Never commit user-supplied RCT2 or StarCraft data, extracted sprites, proprietary graphics, local captures, or bundled engine builds. Follow `docs/licensing.md` and inspect staged paths before each commit.
