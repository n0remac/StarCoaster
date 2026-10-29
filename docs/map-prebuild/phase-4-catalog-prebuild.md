# Phase 4: Automatically prepare the installed catalog

Status: Planned. Depends on accepted Phase 3.
Read [the overview](README.md), [Phase 3](phase-3-supervisor-integration.md), and predecessor completion notes.
Next: [Phase 5](phase-5-verification.md).

## Outcome

Installation and relevant updates schedule sequential prebuilds for the full supported installed catalog.
Unchanged entries are reused; interrupted work resumes and individual failures do not stop other maps.

## Checklist

- [ ] Share catalog discovery with the supervisor rather than introducing a different directory/extension policy.
- [ ] Include installed scenarios and the private park library; define validated upload handling and preserve deterministic duplicate-name precedence.
- [ ] Add a batch command to scripts/project.sh with help, status inspection, rescan, retry/rebuild options, and meaningful exit status.
- [ ] Use the same keys, validation, per-key locking, and preparation implementation as interactive selection.
- [ ] Build sequentially at low CPU/I/O priority on the Pi. Coordinate foreground selection with background work to avoid duplicate builds and resource contention.
- [ ] Integrate scheduling with the actual setup/update/deployment lifecycle after required engines and licensed inputs are available.
- [ ] Identify relevant dependency changes through Phase 2 identity; unrelated updates and unchanged maps must not rebuild.
- [ ] Rescan for added/changed maps and reconcile removed sources without deleting packages used by active sessions.
- [ ] Persist progress/status with source identity, package key, ready/pending/unsupported/failed state, error reason, attempt time, and duration.
- [ ] Continue after per-map failure; mark oversized/unsupported maps explicitly. Return failure/partial-success information suitable for operators and CI.
- [ ] Resume after interruption by validating existing ready packages and rebuilding only unfinished/invalid entries.
- [ ] Keep the server able to handle selection while packages are pending; use Phase 3's one-time miss path.
- [ ] Keep caches and licensed outputs private, on ignored USB-backed storage; document capacity needs and explicit cleanup rules.
- [ ] Document concrete command names and operational trigger behavior once implemented.

## Acceptance and evidence

- Run the catalog prebuild and account for every discovered map with a valid package or explicit unsupported/failure reason.
- A second scan performs no generation/preflight for unchanged valid maps.
- Add and change a map; only newly required keys build. A settings/engine change invalidates affected entries.
- Interrupt and resume a batch; ready packages survive and incomplete packages are not reused.
- A failed map does not prevent later maps completing. Foreground selection during a batch does not corrupt or duplicate a same-key package.
- Verify the automatic trigger in an isolated lifecycle test without replacing production or interrupting a live game.
- Record catalog counts, elapsed time, cache size, resource observations, commands, and failures.

## Completion notes

Pending. Record commits, CLI/status commands, discovery/trigger behavior, full catalog report, resource results, and remaining limits here.
