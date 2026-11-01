# Phase 2/3 integration on canonical main and DEV Pi

Status: integration validated for DEV deployment.

## Integration boundary

The integration branch `integration/cache-dev-pi` started at fetched `origin/main` `e442a1f`.
`phase3-supervisor-cache` remains at `3968934`. The old Phase 1 branch and its
cherry-picked deployment commits were not merged. The following cache commits
were cherry-picked in order, with no conflict resolution or production release
file changes:

| Original | Integrated | Content |
| --- | --- | --- |
| `8bc276d` | `3d0a898` | Phase 2 cache implementation |
| `8bfaf57` | `40e39c0` | Phase 2 evidence |
| `9a2fd49` | `44153ab` | Reader/rebuild requirement |
| `4302095` | `86f41a2` | Test-first requirement |
| `f609df3` | `4b41d92` | Deterministic race regressions |
| `4cd1f1e` | `fd26ed8` | Shared reader lock through materialization |
| `4a86dd4` | `9fea519` | Supervisor cache reuse |
| `3968934` | `6c0e43f` | Phase 3 evidence |

The integrated diff against `origin/main` leaves `scripts/update-pi-game.sh`,
`scripts/deploy-production.sh`, `scripts/pi-post-receive`, and
`deploy/activate-production.py` unchanged. The new DEV path uses separate scripts
and an explicit systemd override. Catalog prebuilding remains Phase 4.

## Ordered race evidence

After `4b41d92` and before `fd26ed8`, the unchanged command
`python3 -m unittest tests.test_single_map_cache_reader_races -v` exited 1.
Both explicitly synchronized tests failed as expected: a reader saw
`CacheInvalid('cache missing: run map-cache build first')` in the replacement
gap, and a materializing reader saw `CacheInvalid('cache changed during
materialization: map/...scm')` while a rebuild replaced the package.
The log is ignored `run-data/integration-cache-dev-pi/red-reader-races.log`.
After applying `fd26ed8`, the identical tests exited 0 (2 passed) in
`run-data/integration-cache-dev-pi/green-reader-races.log`. The writer now
waits for readers holding a shared per-key lock through validation, copy,
checksum checks, and publication.

The first isolated browser run exposed a separate CLI startup regression:
`signal.signal` was called without importing `signal`. The focused startup
test was added and failed before the fix with `NameError` in
`run-data/integration-cache-dev-pi/red-cli-startup.log`. The same test passed
after commit `1739fc0` restored the import, recorded in
`run-data/integration-cache-dev-pi/green-cli-startup.log`.

## Integrated verification

All artifacts below are private and ignored in `/media/pi/media1/starcoaster-dev-build`.
The first full offline attempt hit sandboxed socket restrictions. A second
attempt used a temporary path inside another checkout and inherited patch-test
fixture failures. With the prescribed USB-backed sibling temporary path and
local licensed assets, the full command passed:

```sh
TMPDIR=/media/pi/media1/.starcoaster-tmp GOCACHE=/media/pi/media1/starcoaster-dev-build/build/go-cache scripts/project.sh test
```

Result: Go packages passed, 3 C++ tests passed, 207 Python tests passed with
4 skips, and JavaScript checks passed. The full log is
`run-data/integration-cache-dev-pi/offline-suite-final.log`. The focused cache and
supervisor command passed 33 tests:

```sh
python3 -m unittest tests.test_park_session_supervisor tests.test_single_map_cache tests.test_single_map_cache_reader_races -v
```

The isolated native `Fungus Woods.SC6` probe reached actual native readiness
twice with distinct generations and an unchanged package. With the final
built binaries, its first run measured 64.750 s total and 19.822 s actual
startup. Its repeat measured 31.550 s total and 20.131 s actual startup;
source inspection, park preparation, map generation, and isolated preflight
were explicitly skipped. The repeat saved 33.199 s in this pair. The result
and per-stage timing records are in `run-data/nf-final/verification.json` and
`run-data/nf-final/load-timings.jsonl`. The command was:

```sh
python3 tests/test_park_supervisor_cache_native_live.py --map 'Fungus Woods.SC6' --cache-root run-data/nf-final/cache --runtime run-data/nf-final
```

The edited-save native probe replaced a 64 × 64 park with a 256 × 256 park
under the same saved name. Both sessions reached native readiness; the keys
changed from `70856868…` to `d6c46284…`, matching the new geometry.
Evidence is in `run-data/ns/verification.json` and
`run-data/ns/load-timings.jsonl`. The command was:

```sh
python3 tests/test_park_supervisor_saved_cache_native_live.py --initial-park /media/pi/media1/rts-bridge/run-data/pi-parks/ordinary-frontier-park.park --replacement-park /media/pi/media1/rts-bridge/run-data/world-256-park/world-256-scale.park --cache-root run-data/ns/cache --runtime run-data/ns
```

The first native probe in a deeply nested worktree failed with
`Error: File name too long` before its first readiness result. Moving that
isolated worktree to the stable, shorter DEV build path resolved it. These
timings are warm filesystem selections, not cold-machine measurements.

The isolated release candidate passed the repository browser gameplay check:

```sh
TMPDIR=/media/pi/media1/.starcoaster-tmp python3 scripts/test-release-candidate.py
```

It provisioned the private RCT2 assets into a fresh browser profile, opened
the graphical title screen, selected `Bumbly Bazaar.SC6`, joined generation
`f94a654f442444c29af3b3eafd15368a`, rendered and selected a Marine, sent
a move order, and observed movement in the browser. The report says
`outcome=passed`, 2,845 inbound and 55 outbound multiplayer frames, and
694 ms actor movement latency. The log is
`run-data/integration-cache-dev-pi/release-browser.log`; the report and
private captures are under `build/release-browser/`.

## DEV target and release safeguards

On `raspberrypi` (`100.109.28.107`), the active private game service used
loopback `8091`; Tailscale Serve port `10001` was tailnet only and proxied to
that loopback port. The existing timer ran `starcoaster-deploy.service` every
two minutes through a local override to `update-old-pi-game.sh`; that script
restarted the DEV user service. The stock main release script still targets
`100.119.114.99`, so the committed `deploy/starcoaster-dev-worker.conf` must be
installed and its effective `ExecStart` verified before a main push.

`scripts/update-dev-pi-game.sh` fetches canonical GitHub main into the
isolated DEV build checkout, fast-forwards only, rebuilds native and browser
artifacts from pinned sources and private licensed inputs, runs offline,
WASM, and isolated browser gameplay checks, then calls
`scripts/deploy-dev-pi.sh`. The deploy script refuses non-DEV hostname/IP,
verifies local dependencies, copies the built release into a versioned private
directory, checks the browser bundle and all staged hashes, then atomically
switches the DEV user service. The activator verifies the process working
directory and HTTP status. Failed activation restores the prior link and
service override; the previous successful release or legacy DEV service is
retained for manual `scripts/deploy-dev-pi.sh --rollback`. A manual rollback
pauses the automatic worker until `scripts/deploy-dev-pi.sh --resume` is run.
The release path does not invoke the production-Pi SSH uploader. Licensed
graphics and native builds remain on this private USB drive, outside Git.

## Deployment and remaining limits

The isolated browser run establishes graphical join, rendering, and one
browser-to-OpenBW move order on the release candidate. It does not exercise
two separately visible clients or prove a live tailnet browser session. The
final DEV service revision and post-deployment load evidence must be checked
after activation. Automatic catalog prebuilding is still Phase 4.
