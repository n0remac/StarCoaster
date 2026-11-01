# Phase 3: Load prepared packages during map selection

Status: Complete (2026-11-01). Depends on accepted Phase 2.
Read [the overview](README.md), [Phase 2](phase-2-single-map-cache.md), and its completion notes.
Next: [Phase 4](phase-4-catalog-prebuild.md).

## Outcome

Normal New Game and Load Game selections reuse an exact validated package, create a fresh session, and perform actual startup/readiness checks.
An uncached map is prepared once through the same pipeline and becomes reusable.

## Checklist

- [x] Write deterministic reader/rebuild regression tests and record failures against Phase 2 before the production fix; rerun the same tests unchanged after it.
- [x] Hold a shared per-key reader lock through validation and copying; an exclusive rebuild waits before retiring a package.
- [x] Cover a reader in the replacement gap, rebuild during materialization, concurrent builders, and failed rebuild.
- [x] Use the shared cache resolver from `ParkSessionSupervisor.prepare()` for normal, initial, and recovery loads.
- [x] Preserve catalog, source, upload, format, symlink, and map-size validation.
- [x] Resolve edited saves and uploads by their exact source bytes and dependencies.
- [x] Validate a hit's manifest, outputs, and preflight identity before fresh writable materialization.
- [x] Skip preparation, native map generation, and isolated preflight only for a validated hit.
- [x] Build misses once and repair invalid packages under the per-key lock; report failures through selection errors.
- [x] Start OpenRCT2/OpenBW/Go and await native readiness for every new generation.
- [x] Preserve switch order, cancellation, recovery, generation handling, reconnect path, and active-park persistence.
- [x] Keep mutable journals, revisions, sockets, ports, server/client data, and saves outside the cache.
- [x] Preserve the existing live construction and same-session recovery paths.
- [x] Record cache outcome/key and lookup, validation, materialization, startup, and explicit skipped stages; client join remains unavailable.
- [x] Cover cached/uncached selection, initial load, changed save, corrupt cache, cancellation, and recovery failure.

## Acceptance and evidence

- Reproduce the Phase 2 reader/rebuild failure with a deterministic regression, then show it passes with the fix before integrating supervisor selection. Record the synchronization/publication policy and reader behavior during rebuild.
- Select the Phase 2 map twice through the supervisor. Repeat selection invokes no prep, generation, or isolated preflight; actual startup/readiness executes each time.
- An uncached supported map builds successfully and is a hit next time.
- A content-edited save uses new geometry and identity; source/settings/engine changes cannot reuse stale validation.
- Each generation receives fresh mutable state. Cached files remain byte-identical after gameplay/startup.
- A failed/cancelled selection retains existing recovery guarantees and does not report a stale generation ready.
- Compare Phase 1-compatible timings and report remaining actual-startup costs.
- Run applicable offline and isolated live checks; record skipped graphical checks explicitly.

## Completion notes

Commits on `phase3-supervisor-cache`: `f609df3` added the two race regressions before production edits; `4cd1f1e` fixed reader/rebuild coordination; `4a86dd4` integrated cache reuse into supervisor selection and added focused checks. The regression command was run twice with **unchanged tests**:

```sh
python3 -m unittest tests.test_single_map_cache_reader_races -v > run-data/map-prebuild-phase3/red-reader-races.log 2>&1    # expected FAIL, exit 1, before fix
python3 -m unittest tests.test_single_map_cache_reader_races -v > run-data/map-prebuild-phase3/green-reader-races.log 2>&1  # PASS, exit 0, after fix
```

The first assertion found `CacheInvalid('cache missing: run map-cache build first')` while a rebuild had retired the package. The second found `CacheInvalid('cache changed during materialization: map/...scm')` after a rebuild replaced files mid-copy. The tests gate the replacement rename and first copy with `threading.Event`; the materialization test uses a bounded wait only to release the protected path after the writer has had a chance to reach retirement. Both tests now pass unchanged. `status()` and `materialize()` take a shared `flock` for the exact package key. `materialize()` holds it through validation, copying, checksum checks, path rebasing, and session publication. Builders keep the exclusive key lock, so readers wait for a complete replacement and rebuilds wait for readers. Failed rebuilds leave the prior ready package available; an invalid package is repaired once under the lock when selected.

`ParkSessionSupervisor.prepare()` still resolves the name through its private catalog and saved-park override. It now calls `SingleMapCache.build(..., repair_invalid=True)` and materializes the validated package into a new generation directory. A hit marks inspection, staging, map generation, and isolated preflight as `skipped`; `client_join` remains `unavailable`. A miss or invalid package uses the Phase 2 shared preparation/preflight pipeline. The normal initial and recovery paths call the same `prepare()`. Selection continues to stop the previous process only after preparation and cancellation checks, then starts a new OpenRCT2/OpenBW/Go session and waits for native readiness. Saved-park symlinks are rejected; an edited saved park gets a new byte-based key and new OpenRCT2-inspected dimensions.

The isolated Pi selection probe used installed `Fungus Woods.SC6` with fresh runtime and ports. Its cache key was `6af6925fb3b92a92f3bc23f6a0344d2f98f2baf55a9f93f73e428cffc491c182`. Both generations reached `WORLD_READY ... navigation=native` and `WORLD_SCENARIO_STATUS`; the prior process stopped during the switch. These are first and repeat selections with warm filesystem caches, not a cold-machine measurement.

| Selection | Cache outcome | Total s | Isolated preflight s | Native map generation s | Actual startup s |
| --- | --- | ---: | ---: | ---: | ---: |
| First | built | 46.894 | 19.031 | 0.057 | 19.219 |
| Repeat | hit | 22.171 | skipped | skipped | 18.919 |

The repeat selection saved 24.723 s in this pair. Its 3.252 s before native readiness includes content-key verification, package validation, fresh materialization, and stopping the prior session. The Phase 1 repeat baseline for this map was 38.644 s; this separate run measured 22.171 s, a 16.473 s difference under different warm-cache conditions. Startup remained a separate measured cost in every run. Full timings, session logs, package, and `verification.json` are under ignored `run-data/map-prebuild-phase3/native-fungus-20261101/`. A post-startup `scripts/project.sh map-cache status` returned `ready` after rechecking every package file checksum.

An isolated changed-save probe copied an existing 64×64 park into a private library, then placed a different valid 256×256 park under the same saved name. The two selections built distinct keys (`5e839f20…`, `a89290d1…`) and both reached native readiness. The inspected scenario size changed from `[64, 64]` to `[256, 256]`; timings, logs, and verification are under ignored `run-data/map-prebuild-phase3/native-edited-save-20261101/`. Its first and second total selection times were 26.678 s and 54.224 s, with separate startup times of 10.514 s and 18.018 s. The second selection was a new build, not a cache hit. The first invocation of the test script failed on its own import path; that test-only path was corrected before the passing native run.

Commands and results:

```sh
python3 -m unittest tests.test_park_session_supervisor tests.test_single_map_cache tests.test_single_map_cache_reader_races  # PASS: 33
scripts/project.sh test  # PASS: Go, three C++ tests, 182 Python tests (one skip), JavaScript
python3 tests/test_park_supervisor_cache_native_live.py --map 'Fungus Woods.SC6' --cache-root run-data/map-prebuild-phase3/native-fungus-20261101/cache --runtime run-data/map-prebuild-phase3/native-fungus-20261101  # PASS: built then hit, both ready
python3 tests/test_park_supervisor_saved_cache_native_live.py --initial-park run-data/pi-parks/ordinary-frontier-park.park --replacement-park run-data/world-256-park/world-256-scale.park --cache-root run-data/map-prebuild-phase3/native-edited-save-20261101/cache --runtime run-data/map-prebuild-phase3/native-edited-save-20261101  # PASS: new geometry and key, both ready
scripts/project.sh map-cache status '/home/pi/games/rct2/Scenarios/Fungus Woods.SC6' --cache-root run-data/map-prebuild-phase3/native-fungus-20261101/cache  # PASS: ready after startup
git diff --check  # PASS
```

Focused offline tests also cover initial load, fresh mutable session paths, exact edited-save bytes, corrupt-cache repair, cancelled switch, failed recovery, concurrent builder requests, and failed rebuild preserving the old valid package. The transport, live construction, and same-session recovery implementations were unchanged. Browser/client join, orders, rendering, and two-client synchronization were not verified by these headless checks. The cache still hashes installed data on each lookup; automatic catalog prebuilding belongs to Phase 4.
