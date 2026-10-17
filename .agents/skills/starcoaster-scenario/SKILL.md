---
name: starcoaster-scenario
description: Create or edit a packaged StarCoaster scenario using the implemented objectives, waves, spawn zones, and player reinforcement flow.
---

# Build a scenario package

Start with `scenarios/example-defense/` as a format reference. Choose the mission's own objectives, unit positions, zones, wave timing, and outcome conditions; Example Defense's eastern and western attacks are only an example. Keep the park, native map, and scenario coordinates aligned. The authoritative format is `internal/world/scenario.go`; package resolution is in `scripts/scenario_package.py`.

## Package files

Create `scenarios/ID/scenario.json`, `mapping.json`, and `package.json`, where ID has 1–64 lowercase letters, digits, or hyphens. Copy the three files from `example-defense` or `midway-junction` as a starting point, then set the matching `scenario_id` and `version: 2` in `scenario.json`. The two legacy generator arrays remain supported for their original Frontier Outpost and Example Defense packages. For an independently authored park, set `"generator": "layout-v1"` and `"layout": "park-layout.json"` in `package.json`, place the JSON file beside the package, and use `run-data/ID/save/ID.park`, `run-data/ID/fixture.json`, and `run-data/ID/navigation-elements.json` as outputs. The resolver rejects unrecognized generator commands, unsafe paths, and escaping symlinks. See `starcoaster-park-design` for layout primitives and supported objects.

`mapping.json` has a `rules` array of entity overrides. A rule matches `kind` and optional `type`; supported overrides are `destructible`, `targetable`, `blocks`, `health`, `owner`, `armor`, `damage_scale`, and `effect` (see `internal/world/mapping.go`). Keep the objective's entity kind, type, and optional name consistent with an actual park entity. The bridge discovers the entity from OpenRCT2; configuration does not create it.

## Scenario configuration

- `display_name`, `park_size` (width and height, each 1–256), and `starting_units.marines` / `starting_units.zerglings` describe the mission with unique, in-bounds tile positions. Finite missions require at least one starting Marine and Zergling; `park_defense` requires Marines and no starting Zerglings. The native map builder supports at most 256 starting actors of each type.
- Finite missions require a nonempty `objectives` array with unique `id`, player-facing `description`, `entity_kind`, `entity_type`, optional `entity_name`, and `required`. Their `initial_ai` uses `strategy: "objective_assault"`, an objective ID, and `delay_frames` from 0 to 600. `park_defense` uses `strategy: "park_defense"` and no objective.
- `spawn_zones` maps zone IDs to nonempty arrays of unique, in-bounds `tiles`. Choose reachable, clear tiles in the actual park. `waves` is an ordered array of uniquely named waves; each has a `trigger` and 1–64 `groups`. A group has a registered spawnable ground Zerg enemy `unit_type`, `count` from 1 to 64, and a `spawn_zone` ID. The total per wave cannot exceed 64. Hydralisks and Ultralisks are supported; confirm large-unit clearance in the native park.
- Supported trigger forms are `{"type":"on_ready"}`, `{"type":"elapsed_frames","frames":300}`, and `{"type":"wave_cleared","wave_id":"prior-wave"}`. Elapsed frames are relative to the first complete native frame after readiness. Wave references must exist and cannot form cycles. The runtime uses the shared native spawn queue and persists wave progress across bridge restarts.
- The implemented version 2 outcome fields are `victory.all_waves_cleared: true`, `victory.all_zerglings_eliminated: true`, `victory.objective_intact`, `defeat.objective_destroyed`, and `defeat.all_marines_eliminated: true`. The objective references must match `initial_ai.objective`. Other victory or defeat rules need implementation work.
- `park_defense` accepts either legacy `units_per_wave` or `wave_tiers`, never both. A tier has `from_wave` and `groups` containing `unit_type` and `count`; the first threshold is 1, later thresholds increase, and each composition totals at most 64. The highest eligible tier governs the durable periodic or manual wave sequence. Existing four-sided spawn rotation, fallback, manual cooldown, and OpenRCT2 scenario victory remain in force.

Marine reinforcements already use the player-facing **Spawn Marine** tool in the OpenRCT2 squad window. The player chooses 1–5 Marines and a clear park tile; the bridge sends the request through the same native spawn queue used by waves. There is no per-scenario JSON field for reinforcement count, allowance, unit type, or UI behavior. Use the existing flow as-is for a new package, and change the gameplay implementation only if the requested design requires a new capability. Keep fault injection and spawn probes test-only.

## Validate and play

```sh
scripts/project.sh validate-scenario ID
scripts/project.sh play ID --plan
scripts/project.sh park ID
scripts/project.sh play ID
scripts/project.sh record --scenario ID --duration 85
```

`validate-scenario` checks the scenario definition; `--plan` checks package resolution without launching. `park` requires a built OpenRCT2, its pinned upstream park fixture, and local licensed RCT2 data; `play` and `record` also need built engines and local StarCraft data. Run `scripts/project.sh test` after edits. Verify the objective, starting positions, wave placement, native movement, manual reinforcements, outcome, and two-client synchronization in a live run; use `starcoaster-verify` to select focused regressions. `tests/test_scenario_runtime_live.py` asserts Frontier-specific counts, names, and waves; it does not validate Example Defense or Midway Junction. Midway's focused live harness is `tests/test_midway_scenario_live.py`. Record commands, pass/fail results, and ignored `run-data/` evidence paths.
