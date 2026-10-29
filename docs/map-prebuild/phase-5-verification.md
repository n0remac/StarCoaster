# Phase 5: Verify correctness, gameplay, and loading improvement

Status: Planned. Depends on accepted Phase 4.
Read [the overview](README.md), all predecessor completion notes, and [Phase 1 baseline](../map-loading-baseline-phase1.md).

## Outcome

Demonstrate exact-content correctness, resilient cache operation, browser/native gameplay, and measured loading improvement.
Resolve discovered defects before marking the overall plan complete.

## Checklist

- [ ] Re-run representative Phase 1 maps with the same instrumentation and comparable engine/settings versions: Fungus Woods, Extreme Heights, and the saved frontier outpost park.
- [ ] Measure uncached preparation separately from repeated cached selection. Capture source identity, cache outcome, sample count, timings, host/build details, and meaningful differences from the baseline.
- [ ] Demonstrate repeat hits run no preparation, native map generation, or isolated preflight through invocation evidence as well as timings.
- [ ] Report cache lookup/validation/materialization, actual engine startup, and end-to-end selection separately; retain native navigation/readiness work.
- [ ] Verify new and edited saves, uploads, equal-length preserved-timestamp edits, changed StarCraft settings, generator changes, and engine/protocol changes.
- [ ] Exercise missing/checksum-corrupt files, incomplete publication, failed preflight, interrupted builder, concurrent requests, batch restart, and recoverable storage failure.
- [ ] Verify failed map switches, cancellation, recovery, active-session isolation, and cache immutability.
- [ ] Verify browser and native clients join the same prepared map, issue unit orders that execute in OpenBW, and display matching state.
- [ ] Build/remove paths, scenery, and relevant structures; verify ordered geometry synchronization and navigation. Save the changed park and reload it through the exact-content cache path.
- [ ] Verify reconnect/recovery does not reset actors or replay scenario startup incorrectly.
- [ ] Reconcile the installed catalog: every supported source is ready or has a recorded actionable failure; unsupported sources have explicit reasons.
- [ ] Document status/rebuild/rescan/cleanup commands, automatic update behavior, invalidation policy, and operational limits.
- [ ] Run required offline checks and applicable live/graphical checks from repository guidance; keep licensed assets/captures/results in ignored storage.

## Acceptance and reporting

Publish a committed verification report linking the Phase 1 baseline and final operational documentation.
Include before/after values and absolute/percentage change for comparable measurements; explain variance and avoid promising elimination of actual startup time.
Client join must be measured through an explicit graphical signal or reported unavailable. Headless WORLD_READY is insufficient.
Record exact commands, pass/fail results, artifact paths, cache/catalog counts, and any blocked checks with reasons.
Do not mark browser/native gameplay or full completion passed while required evidence is missing.
Production rollout remains a separate user-directed operation.

## Completion notes

Pending. Record commits, verification report path, performance results, gameplay evidence, catalog status, and unresolved limits here.
