> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# v0.2 codebase audit

The active Frontier path is `scenarios/former root scenario configuration`, `scripts/former Frontier launcher`, `scripts/former Frontier recorder`, `openrct2-plugin/rts-bridge.js`, `openbw-bwapi-module/src/WorldAdapter.h`, and `cmd/world-bridge/`. `scripts/project.sh` delegates build, park generation, launch, recording, and test commands to those tools. The Go bridge coordinates synchronization; OpenRCT2 and OpenBW retain their own state authority.

`tests/` retains Go, C++, JavaScript, and Python regressions for protocol state, combat, snapshots, wall navigation, render fixtures, and artifacts. The opt-in live gates are the native route, generic two-client demolition, and Frontier lifecycle checks. The unused `world-command-probe.js` and `world-unit-count-probe.js` were removed after confirming their behaviors remain covered by `tests/test_world_plugin.js` and the live checks. The generic target probe remains because `tests/test_world_live.sh` invokes it.

Earlier patrol, ride siege, park assault, sprite extraction, and battle replay tools remain in `scripts/` because phase reports and regressions still invoke them. `former prototype capture driver` is large but routes to separate video, artifact, visual, navigation, and verification modules; a deeper split would touch these historical workflows without improving the Frontier entry point. The v0.1 specifications live in `docs/archive/`, while current commands and boundaries are in the root README and `AGENTS.md`.

Ignored `upstream/`, `build/`, `run-data/`, and `logs/` are dependencies or local output. The tracked source contains no game data or generated park files. See `docs/licensing.md` before adding assets.
