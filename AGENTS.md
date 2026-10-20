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
scripts/project.sh launch                            # native OpenRCT2 main menu
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

The native launcher and browser app enter OpenRCT2's standard main menu. The Pi browser service can remain idle with no initial park. Selecting New Game or Load Game now requests an authoritative session through the patched OpenRCT2 map-load callbacks. The supervisor resolves stock scenarios against its installed RCT2 data and accepts validated private save uploads, starts OpenBW and the Go bridge, then reports a new generation only after native readiness. The graphical client joins through OpenRCT2 multiplayer. The browser asks for the private session owner token on the first map selection; the token is generated in the supervisor's ignored runtime directory. Native clients need `STARCOASTER_CONTROL_URL` and `BRIDGE_SESSION_OWNER_TOKEN` when they are not launched by the local supervisor. Continue using explicit scenario `play` commands for packaged missions and focused regressions.

The browser workflow and its verification limits are in `docs/wasm-browser.md`. Keep browser resources private. The Pi-hosted browser server provisions RCT2 from its locally licensed `RCT2_DATA_DIR` over private Tailscale HTTPS, and the private WASM bundle contains staged StarCraft graphics; users do not import assets from their laptops. A development server without a configured RCT2 source retains local import. Never expose these resources through Tailscale Funnel or commit them. Preserve the native OpenRCT2 multiplayer protocol and remote plugin path. A WASM build or offline park render does not complete browser gameplay verification; confirm a browser order executes in OpenBW and both client types display the same result.

For browser asset changes, keep licensed RCT2 files outside `assets.zip`. The browser server inventories the configured RCT2 directory and serves only manifest-listed files; the launcher verifies their sizes and SHA-256 hashes before persisting them in IndexedDB. Test first-use provisioning and reuse on the private origin with `WASM_PRIVATE_RCT2=1`, `WASM_RCT2_DIR`, `WASM_TEST_URL`, and an ignored `WASM_TEST_PROFILE` when running `scripts/project.sh test-wasm`. For live Chromium checks, set `WASM_LIVE_URL` to that origin and `WASM_LIVE_PROFILE` to the same profile; the private origin provisions assets on first use, while other origins require an existing local import in that profile. Keep the native host running for live checks and browser reconnects.

On the Raspberry Pi, `/home/pi/Projects/rts-bridge` resolves to the attached USB drive at `/media/pi/media1/rts-bridge`. Keep Emscripten dependencies, CMake output, Chromium profiles, licensed test imports, captures, and runtime logs in ignored `build/` or `run-data/` there; `scripts/project.sh` also redirects temporary files to the drive. For a browser gameplay check, use `scripts/project.sh prepare-wasm-arm64`, `OPENRCT2_WASM_LOCAL=1 scripts/project.sh build-wasm`, `scripts/project.sh test-wasm`, and `scripts/project.sh deploy-wasm`. Run the managed Pi service with no initial park, then select a stock scenario through New Game and verify a browser order reaches OpenBW. `WASM_NORMAL_HANDOFF=1` enables the graphical first-game probe in `browser/live-test.mjs`; the explicit `BRIDGE_SERVE_WASM=1 BRIDGE_LAUNCH_CLIENT=0 scripts/project.sh play wasm-mixed-client` path remains useful for mixed-client regressions. Keep the host running across browser reconnect tests. Licensed graphical checks require locally installed RCT2 and StarCraft data; report skipped checks as blocked by missing data.

Use player-facing scenario configuration and the normal `start`/`play` path for features. Keep fault hooks, spawn probes, and diagnostic scripts in tests and verification workflows; do not surface them as player controls. Preserve park footprints, spawn tiles, chokepoints, collision masks, and native routes when changing geometry.

Live park construction uses `world.patch` transactions against the last confirmed revision. OpenRCT2 detects and batches ordinary synchronized actions; Go validates and stages the entire mapped candidate; both OpenBW participants must stage, schedule, and report application at the same native frame before the bridge publishes synchronization. Treat `world.ack` as transport acceptance only. Route confirmed combat demolition through the same ordered revision lifecycle, and keep manual objective removal distinct from native combat destruction. Same-session snapshots recover from the current park without replaying scenario startup or resetting actors, target HP, or spawn journals. See `bridge-protocol/README.md` and `docs/live-construction-milestone.md` for the wire lifecycle, measured runs, and current limits.

Commit coherent increments as work proceeds, with documentation commits separate from unrelated implementation changes. Run relevant offline checks before affected live or graphical checks; select them with `.agents/skills/starcoaster-verify/SKILL.md`. Use `.agents/skills/starcoaster-park-design/SKILL.md` for layout work and `.agents/skills/starcoaster-demo/SKILL.md` for captures. Report commands and pass/fail results, artifact paths, and remaining limits; state missing live dependencies plainly.

Never commit user-supplied RCT2 or StarCraft data, extracted sprites, proprietary graphics, local captures, or bundled engine builds. Follow `docs/licensing.md` and inspect staged paths before each commit.
