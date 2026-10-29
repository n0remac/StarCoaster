# Map prebuild plan

Status: Phase 1 complete; phases 2–5 planned. Start with [Phase 2](phase-2-single-map-cache.md).
This directory is the shared context for Happier sessions implementing map prebuilds.
Creating these plans does not start implementation or authorize production deployment.

## Goal and sequence

Prepare every supported installed OpenRCT2 map with the default StarCraft settings ahead of selection. Reuse validated immutable outputs; create fresh mutable state for every session.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 1 | Complete | [Instrumentation and baseline](../map-loading-baseline-phase1.md) |
| 2 | Planned | [Single-map cache and preparation API](phase-2-single-map-cache.md) |
| 3 | Planned | [Supervisor cache integration](phase-3-supervisor-integration.md) |
| 4 | Planned | [Automatic catalog prebuild](phase-4-catalog-prebuild.md) |
| 5 | Planned | [Correctness, gameplay, and performance verification](phase-5-verification.md) |

Finish the single-map path through Phase 3 before scaling to the whole catalog.
Each phase depends on the previous phase's acceptance evidence.

## Phase 1 findings to preserve

Commits: `dcfd52b` (instrumentation), `8e369a6` (USB temporary files), `f23a079` (report).
Two samples per map measured preparation / isolated preflight / actual session startup:

| Map | Preparation s | Preflight s | Startup s | Total s |
| --- | ---: | ---: | ---: | ---: |
| Fungus Woods, repeat | 0.873 | 18.737 | 18.919 | 38.644 |
| Extreme Heights, repeat | 0.875 | 10.031 | 9.909 | 20.929 |
| Saved frontier outpost, repeat | 1.079 | 10.635 | 10.511 | 22.340 |

These are fresh session workspaces, not cold-machine measurements. Full evidence and reproduction command are in the Phase 1 report.
Preflight and actual startup dominate. Cache reuse should remove repeated generation and isolated preflight; actual session startup and native navigation initialization remain.
The baseline is headless. Client join is unavailable in supervisor timing and browser/native graphical gameplay remains unverified.

## Shared implementation constraints

- Read repository `AGENTS.md` and applicable skills before changing code.
- Inspect current code; paths below are starting points, not a prescribed API.
- Reuse `scripts/prepare_existing_defense.py`, `scripts/scenario_package.py`, and `ParkSessionSupervisor.prepare()` in `scripts/park_session_supervisor.py`.
- Preserve current StarCraft gameplay settings, engine authority, ordered construction synchronization, normal New Game/Load Game, and session-switch recovery.
- Cache identity must reflect exact source bytes, effective gameplay settings, preparation dependencies, and relevant built engine/protocol versions. File name, size, or mtime alone is insufficient.
- Store generated packages, licensed inputs, benchmarks, and logs in ignored `run-data/` on the Pi USB drive. Do not commit licensed assets or generated native maps.
- Prepared packages are immutable; journals, sockets, logs, server/client data, runtime geometry revisions, and active saves belong to fresh sessions.
- A cached preflight never substitutes for actual live readiness or client gameplay evidence.
- Use isolated test runtimes/ports. Do not stop active games or deploy to production as part of these documentation tasks.

## Happier handoff contract

Read this overview, the Phase 1 report, the target phase, and predecessor completion notes.
Implement only the assigned phase unless the user requests more.
For each phase record status, commits, commands/results, ignored artifact paths, failures, skipped checks, and decisions affecting the next phase.
Update this table and that phase's completion notes only after its acceptance criteria are met.
Commit coherent documentation and implementation increments according to `AGENTS.md`.

## Overall completion

Every supported installed map has a valid prepared package or an explicit recorded failure.
Selecting a validated prepared map runs no preparation/map generation or separate isolated preflight, while fresh session initialization and live readiness still run.
Edited saves use their exact geometry; browser and native clients can join, command units, and remain synchronized after construction.
