# Phase 3: Load prepared packages during map selection

Status: Planned. Depends on accepted Phase 2.
Read [the overview](README.md), [Phase 2](phase-2-single-map-cache.md), and its completion notes.
Next: [Phase 4](phase-4-catalog-prebuild.md).

## Outcome

Normal New Game and Load Game selections reuse an exact validated package, create a fresh session, and perform actual startup/readiness checks.
An uncached map is prepared once through the same pipeline and becomes reusable.

## Checklist

- [ ] Update ParkSessionSupervisor.prepare() and initial/recovery callers to use the shared resolver and cache.
- [ ] Preserve source_for()/catalog() validation, allowed directories, symlink restrictions, supported formats, upload checks, and current size limits.
- [ ] Resolve by exact validated source bytes and effective dependencies, including changed saves/uploads; never infer saved geometry from an original scenario name.
- [ ] On a valid hit, verify manifest/outputs and preflight identity, then materialize a fresh writable generation with correctly rebased paths.
- [ ] Skip preparation, park/native-map generation, and isolated preflight only for a compatible validated hit.
- [ ] On a miss or invalid package, build once using Phase 2 locking and publication; report failure through normal selection errors.
- [ ] Always start the actual OpenRCT2/OpenBW/Go session and wait for current-generation native synchronization/navigation readiness.
- [ ] Preserve switching order, cancellation, old-session recovery, generation handling, reconnect behavior, and active-park persistence.
- [ ] Keep mutable journals, world revisions, sockets, ports, server/client state, and runtime saves isolated from cache contents.
- [ ] Preserve live construction synchronization and same-session recovery without replaying scenario startup.
- [ ] Extend timing records with cache outcome/key and lookup/validation/materialization stages; distinguish skipped cached stages from unavailable client-join evidence.
- [ ] Add focused regressions for cached and uncached selection, initial load, changed save, corrupt cache, cancelled switch, and recovery failure paths.

## Acceptance and evidence

- Select the Phase 2 map twice through the supervisor. Repeat selection invokes no prep, generation, or isolated preflight; actual startup/readiness executes each time.
- An uncached supported map builds successfully and is a hit next time.
- A content-edited save uses new geometry and identity; source/settings/engine changes cannot reuse stale validation.
- Each generation receives fresh mutable state. Cached files remain byte-identical after gameplay/startup.
- A failed/cancelled selection retains existing recovery guarantees and does not report a stale generation ready.
- Compare Phase 1-compatible timings and report remaining actual-startup costs.
- Run applicable offline and isolated live checks; record skipped graphical checks explicitly.

## Completion notes

Pending. Record commits, resolver integration, cache/fallback timing evidence, recovery test results, and remaining limits here.
