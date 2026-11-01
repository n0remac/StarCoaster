# Phase 2: Prepare and reuse one cached map

Status: Complete (2026-11-01). Depends on completed Phase 1.
Read [the overview](README.md) and [Phase 1 evidence](../map-loading-baseline-phase1.md).
Next: [Phase 3](phase-3-supervisor-integration.md).

## Outcome

One representative map can be prepared, validated, published, and loaded from a persistent cache through a reusable API or developer command.
Keep normal supervisor selection behavior unchanged until Phase 3.

## Checklist

- [x] Inspect preparation, park generation, native map generation, and isolated preflight callers; extract one shared pipeline without duplicating engine behavior.
- [x] Define a versioned manifest and deterministic key covering source SHA-256, effective StarCraft configuration/mapping, generator dependencies, and relevant engine/protocol/build identity.
- [x] Hash the actual staged source used for generation; handle source changes during preparation without publishing under the wrong identity.
- [x] Make dependency invalidation explicit. Prefer conservative invalidation when compatibility cannot be established; document how locally modified generators or engine binaries are identified.
- [x] Package the prepared park, scenario/configuration, mapping, native .scm, required preparation metadata, output sizes/checksums, and successful preflight identity.
- [x] Separate immutable outputs from session-specific paths and state. Define how relative paths or manifests resolve after materialization into another session directory.
- [x] Validate all required files and preflight success before atomically publishing a temporary build as ready on the same filesystem.
- [x] Lock per package key; a second requester waits or reuses the published result. Interrupted builds and failed preflight never look ready; stale-lock recovery must not remove a live owner's lock.
- [x] Reject missing, corrupt, incompatible, or incomplete packages. Provide actionable diagnostics and a deliberate rebuild path.
- [x] Add single-map build/status/reuse entry points using existing CLI conventions; keep intermediate work under ignored USB-backed run-data.
- [x] Materialize two independent writable sessions without mutating the cached outputs. Do not hard-link files engines may write.
- [x] Retain Phase 1 timing and distinguish cache lookup, validation, build, preflight, and materialization.

## Acceptance and evidence

- First build publishes a validated package; repeat use invokes neither preparation/map generation nor separate preflight.
- A change to source bytes (including equal-length edits with preserved timestamps), settings, generator identity, or relevant engine identity prevents stale reuse.
- Missing/corrupt output, interrupted build, failed preflight, and two same-key requesters behave correctly.
- Two materialized sessions have fresh mutable state and can resolve all required paths after the builder workspace is removed.
- Run focused offline tests and repository-required checks. Record a representative live preflight, commands, package key, timings, and artifact paths.
- Do not claim browser/native graphical verification from headless readiness.

## Completion notes

Implementation commit: `8bc276d` on `phase2-single-map-cache`. `scripts/park_preparation.py` now owns the ordered preparation and isolated preflight calls used by the existing supervisor and `SingleMapCache`. The supervisor still prepares each selection normally; cache selection belongs to Phase 3. `scripts/project.sh map-cache` exposes `build`, `status`, and `reuse` for one source path. `SingleMapCache.build()`, `.status()`, and `.materialize()` are the reusable API.

Schema 1 hashes the exact source bytes, resolved source path and name, the current default defense settings and mapping identity, preparation and protocol source trees, native binaries, staged OpenRCT2 data, and the installed RCT2 and StarCraft data trees. Every dependency root is content hashed; local generator or engine binary edits change the key even if size and timestamp are preserved. This is deliberately conservative: a change to unrelated installed assets can also invalidate the package. The staged source is compared with the key's source SHA-256, and the original source and dependency roots are rehashed before publication. If they changed, the build fails and a new key is required.

Packages live under ignored `run-data/map-cache*/packages/KEY`. `manifest.json` records the key inputs, file sizes and SHA-256 hashes. The package contains the staged source, prepared park, scenario, mapping, preparation metadata, native `.scm`, and `preflight.json` linking the successful native preflight to the source, park, scenario semantics, mapping, and map hashes. The manifest and every required file are validated before a same-filesystem rename publishes the ready directory. Cache files are read-only. The per-key `flock` file stays in `locks/`; an abandoned build directory does not count as ready, and a live owner's lock is never removed. Failed builds go to `failed/`; successful preflight logs go to `logs/`. `build --rebuild` is the deliberate repair path for a corrupt or incompatible package and retires the prior directory only after a replacement validates.

The cached scenario and metadata use package-relative `save/` and `source/` paths. `materialize()` copies bytes into a fresh directory outside the cache, rewrites those paths for that directory, and creates empty writable server/client directories. It does not copy a spawn journal or hard-link any file. Two materializations from the final package had distinct park inodes (`33981790`, `34095072`) from the cached park (`33981719`); the session files were writable and the cached file remained read-only. A native session started successfully from a materialization after the builder directory was gone.

Representative map: installed `Fungus Woods.SC6`, source SHA-256 `1552df55…`, package key `a183db213720c003c79d6a18b8362763d378f075a85bf698a7ea2c6860a189a4`. These are first-build and immediate-repeat observations on a warm Pi, not cleared-cache machine measurements.

| Operation | Total s | Key lookup s | Locked key recheck s | Inspection s | Map generation s | Isolated preflight s | Materialization s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Build into fresh cache | 25.299 | 2.598 | 1.013 | 0.913 | 0.060 | 19.035 | — |
| Repeat build, validated reuse | 2.087 | 1.027 | 1.057 | — | — | — | — |
| Reuse into another session | 1.274 | 1.261 | — | — | — | — | 0.004 |

Repeat build saved 23.212 s (91.7%) in this pair. It invoked no inspection, park staging, map generation, or separate preflight. Actual live startup remained a separate 20.422 s, measured by the native check below; it was not treated as a cache hit or client join. The Phase 1 [baseline](../map-loading-baseline-phase1.md) remains the reference for the uncached selection path. Raw timings and the package are under `run-data/map-cache-phase2-evidence-20261101/`; native startup timings and log are under `run-data/map-cache-phase2-evidence-native/`. All artifacts are ignored and contain no committed licensed data.

Commands and results:

```sh
scripts/project.sh test                                           # PASS: Go, 3 C++ tests, 173 Python tests (1 skip), JavaScript
python3 -m unittest tests.test_single_map_cache tests.test_park_session_supervisor  # PASS: 24
scripts/project.sh map-cache build '/home/pi/games/rct2/Scenarios/Fungus Woods.SC6' --cache-root run-data/map-cache-phase2-evidence-20261101  # PASS: new package
scripts/project.sh map-cache build '/home/pi/games/rct2/Scenarios/Fungus Woods.SC6' --cache-root run-data/map-cache-phase2-evidence-20261101  # PASS: reused=true
python3 tests/test_single_map_cache_native_live.py '/home/pi/games/rct2/Scenarios/Fungus Woods.SC6' --cache-root run-data/map-cache-phase2-evidence-20261101 --session-dir run-data/map-cache-phase2-evidence-session --runtime run-data/map-cache-phase2-evidence-native  # PASS: WORLD_READY navigation=native and WORLD_SCENARIO_STATUS
scripts/project.sh map-cache reuse '/home/pi/games/rct2/Scenarios/Fungus Woods.SC6' --cache-root run-data/map-cache-phase2-evidence-20261101 --session-dir run-data/map-cache-phase2-evidence-session-b  # PASS: second independent session
git diff --check  # PASS
```

The first sandboxed native attempt failed at source inspection because loopback socket creation was denied; the same build passed with native access. The failure record and incomplete build are under ignored `run-data/map-cache-phase2-20261101/failed/`. Unit checks cover same-length source changes with preserved timestamps, settings and dependency changes, changed inputs during build, corrupt/missing/incompatible files, deliberate rebuild, failed preflight, orphan builds, concurrent same-key requests, and independent sessions.

Remaining limits: the cache is invoked only through the developer CLI and API. Normal supervisor selection, catalog-wide prebuilding, client join, browser orders, and graphical synchronization are for later phases. The headless native check proves only that the copied package loads and reaches the existing server/OpenBW readiness markers. Full content hashing of installed data costs about 1 s per warm lookup in this sample and may need a measured optimization before catalog-wide use.
