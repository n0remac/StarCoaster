# Phase 2: Prepare and reuse one cached map

Status: Planned. Depends on completed Phase 1.
Read [the overview](README.md) and [Phase 1 evidence](../map-loading-baseline-phase1.md).
Next: [Phase 3](phase-3-supervisor-integration.md).

## Outcome

One representative map can be prepared, validated, published, and loaded from a persistent cache through a reusable API or developer command.
Keep normal supervisor selection behavior unchanged until Phase 3.

## Checklist

- [ ] Inspect preparation, park generation, native map generation, and isolated preflight callers; extract one shared pipeline without duplicating engine behavior.
- [ ] Define a versioned manifest and deterministic key covering source SHA-256, effective StarCraft configuration/mapping, generator dependencies, and relevant engine/protocol/build identity.
- [ ] Hash the actual staged source used for generation; handle source changes during preparation without publishing under the wrong identity.
- [ ] Make dependency invalidation explicit. Prefer conservative invalidation when compatibility cannot be established; document how locally modified generators or engine binaries are identified.
- [ ] Package the prepared park, scenario/configuration, mapping, native .scm, required preparation metadata, output sizes/checksums, and successful preflight identity.
- [ ] Separate immutable outputs from session-specific paths and state. Define how relative paths or manifests resolve after materialization into another session directory.
- [ ] Validate all required files and preflight success before atomically publishing a temporary build as ready on the same filesystem.
- [ ] Lock per package key; a second requester waits or reuses the published result. Interrupted builds and failed preflight never look ready; stale-lock recovery must not remove a live owner's lock.
- [ ] Reject missing, corrupt, incompatible, or incomplete packages. Provide actionable diagnostics and a deliberate rebuild path.
- [ ] Add single-map build/status/reuse entry points using existing CLI conventions; keep intermediate work under ignored USB-backed run-data.
- [ ] Materialize two independent writable sessions without mutating the cached outputs. Do not hard-link files engines may write.
- [ ] Retain Phase 1 timing and distinguish cache lookup, validation, build, preflight, and materialization.

## Acceptance and evidence

- First build publishes a validated package; repeat use invokes neither preparation/map generation nor separate preflight.
- A change to source bytes (including equal-length edits with preserved timestamps), settings, generator identity, or relevant engine identity prevents stale reuse.
- Missing/corrupt output, interrupted build, failed preflight, and two same-key requesters behave correctly.
- Two materialized sessions have fresh mutable state and can resolve all required paths after the builder workspace is removed.
- Run focused offline tests and repository-required checks. Record a representative live preflight, commands, package key, timings, and artifact paths.
- Do not claim browser/native graphical verification from headless readiness.

## Completion notes

Pending. Record implementation API/commands, cache location/schema, dependency-key policy, commits, validation results, and remaining limits here.
