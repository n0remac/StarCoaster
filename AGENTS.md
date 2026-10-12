# StarCoaster development guide

OpenRCT2 owns the park, scenery, rides, multiplayer state, and rendering. OpenBW owns unit movement, pathfinding, health, and combat. The Go world bridge coordinates snapshots and commands between them; do not duplicate either engine's authority in an adapter or test probe.

## Source map

- `openrct2-plugin/` and `openrct2-patches/`: park synchronization, player controls, and native rendering.
- `openbw-bwapi-module/`: OpenBW/BWAPI bridge, actor state, and native navigation.
- `cmd/world-bridge/`, `internal/world/`: Go transport, world model, scenario coordination.
- `scenarios/`: current gameplay configuration; `scripts/`: builds, launchers, park generation, captures; `tests/`: regressions.
- `bridge-protocol/`: versioned wire contracts. `docs/archive/`: historical specifications. `upstream/`, `build/`, and `run-data/` are local, ignored inputs or outputs.

## Standard commands

```sh
scripts/build-bwapi.sh
scripts/build-openrct2.sh
scripts/build-bridge-module.sh
/usr/local/go/bin/go build -o build/world-bridge ./cmd/world-bridge
scripts/run-frontier-outpost.sh
/usr/local/go/bin/go test ./...
ctest --test-dir build/bridge-module --output-on-failure
python3 -m unittest discover -s tests -p 'test_*.py'
for file in tests/test_*plugin.js tests/test_plugin_snapshots.js; do node "$file" || exit; done
tests/test_frontier_native_navigation_live.sh
```

Use the relevant unit tests before live graphical tests. Preserve navigation, combat, synchronization, and rendering regressions when refactoring. Park changes must keep structure footprints, spawn points, chokepoints, and destructible openings aligned with the scenario and native map. Keep generated parks and captures deterministic where possible.

Never commit user supplied RCT2 or StarCraft data, extracted sprites, proprietary graphics, local captures, or bundled engine builds. Follow `docs/licensing.md` and check staged paths before committing.

Report the commands run, pass or fail results, artifact paths, and remaining limits. If a live test cannot run, state the missing dependency or failure plainly. See `README.md` for the current playable workflow and `docs/first-playable-verification.md` for the prior baseline.
