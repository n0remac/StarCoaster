# First Playable Verification — Frontier Outpost

> Historical first-playable baseline. The v0.2 [foundation verification](foundation-verification.md) resolves the listed victory, reconnect/restart, and generic live demolition gaps; the [park design report](park-design-v0.2.md) records the corrected wall geometry and native route retest.

**Status: In progress.** The graphical first-playable encounter, native navigation checks, and live selection-control checks pass. Victory and a live scenario restart/reconnect still need verification, so this report does not declare the milestone complete.

## Test target

- Repository baseline and tested source commit: `72b498c96bb5cf0fa2bac6918fe38d525a1c943c`.
- The verification ran with the working-tree changes present; the source commit is the baseline, not a claim that these changes have been committed.
- Frontier Outpost was launched through `scripts/run-frontier-outpost.sh` with the installed RCT2 and StarCraft data on this Pi.
- `WORLD_READY` reported `entities=556 targets=27 obstacles=231 navigation=native unsupported=0`. The graphical capture showed all six Marines and twelve Zerglings.

## Build and regression commands

| Command | Result | Evidence |
| --- | --- | --- |
| `scripts/build-bwapi.sh` | **PASS** | BWAPI/OpenBW rebuilt with both native navigation patches applied. |
| `scripts/build-openrct2.sh` | **PASS** | Configure/build succeeded; the native renderer was up to date and the staged `g2.dat` asset pack generated. |
| `scripts/build-bridge-module.sh` | **PASS** | C++ adapter rebuilt against the patched BWAPI/OpenBW interfaces. |
| `/usr/local/go/bin/go build -o build/world-bridge ./cmd/world-bridge` | **PASS** | Rebuilt the Go bridge binary used by the normal launch scripts. |
| `git apply --reverse --check openbw-bwapi-module/0002-native-navigation-openbw.patch` from `upstream/openbw` | **PASS** | Patch is present and reverse-checks cleanly. |
| `git apply --reverse --check openbw-bwapi-module/0003-native-navigation-bwapi.patch` from `upstream/bwapi` | **PASS** | Patch is present and reverse-checks cleanly. |
| `/usr/local/go/bin/go test ./...` | **PASS** | All Go packages passed. |
| `ctest --test-dir build/bridge-module --output-on-failure` | **PASS** | `world_state_test` and `world_navigation_test`, 2/2. |
| `for test_file in tests/test_*plugin.js tests/test_plugin_snapshots.js; do node "$test_file"; done` | **PASS** | Plugin lifecycle, combat validation, and snapshot tests passed. |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | **PASS** | 43 tests passed. |
| `tests/test_frontier_native_navigation_live.sh` | **PASS** | Six live actor-position checks passed; details below. |
| `tests/test_world_live.sh` | **FAIL** | In `run-data/world-live-1791836216/`, the client probe repeatedly received `Invalid Zergling target` and never issued the attack. In `run-data/world-live-1791835871/`, the attack was accepted, but ride 1 was not removed within 180 seconds while the Marine navigated the park. |
| Java regression suite | **DEFERRED** | The repository has no Java sources or Java test harness. |

## Acceptance criteria

### A. Build and initialization

| Criterion | Status | Evidence |
| --- | --- | --- |
| OpenBW, BWAPI, OpenRCT2, and Go bridge compile | **PASS** | Build commands above and Go tests passed. |
| Native navigation patches apply to their upstream checkouts | **PASS** | Both patches reverse-check cleanly; rebuilds passed. |
| Normal Frontier Outpost launcher starts | **PASS** | Graphical capture invoked `scripts/run-frontier-outpost.sh`; `WORLD_READY` was emitted. |
| Six Marines, twelve Zerglings, combat targets, and geometry initialize | **PASS** | Capture log and `verification.json`; 27 supported targets, 231 obstacles, zero unsupported targets. |
| Reject readiness when a required scenario component is absent | **DEFERRED** | The successful startup proves required components are present; a missing-component startup was not deliberately exercised. |

### B. Native navigation

All checks use OpenBW actor positions from live client snapshots, not route calculations alone. `run-data/frontier-native-nav-1791834732/verification.json` records all six as true.

| Criterion | Status | Evidence |
| --- | --- | --- |
| Units navigate around the intact carousel | **PASS** | Zero pre-demolition carousel-footprint intrusions. |
| Units pass through legitimate wall openings | **PASS** | Marines crossed at the observed route below the blocked wall run (y 1283–1289). |
| Units cannot traverse blocked corridors | **PASS** | The blocked wall corridor had no pre-demolition crossings. |
| Destroying a wall opens a route | **PASS** | Both OpenBW processes applied the wall removal at frame 973; all six Marines crossed x=896 near y=1132–1139 afterward. |
| Destroying the carousel makes its footprint traversable | **PASS** | Live Marine positions entered its former x=576–672, y=544–640 footprint after ride removal. |
| Multiple Marines move without persistent collision or stuck behavior | **PASS** | All six moved 372–491 pixels in the native test without stalls. |

### C. Player controls

| Criterion | Status | Evidence |
| --- | --- | --- |
| Click selection and Shift-click selection | **PASS** | A live click selected Marine 1000; Shift-click added Marine 1002. Logs and screenshots are in `run-data/artifacts/20261012T201917Z-54511633fdcc/`. |
| Drag selection and visible selection highlight | **PASS** | The running interface selected all six Marines; `client-a-t2.png` shows their selection highlights. |
| Visible selection rectangle while dragging | **PASS** | `client-a-t0.png` shows the rectangle feedback on the OpenRCT2 map. |
| Control-group save and recall | **PASS** | Ctrl+1 saved the six-Marine group; `client-a-t1.png` shows the cleared selection and `client-a-t2.png` shows all six restored after pressing 1. |
| Move, attack, attack-move, hold, and stop | **PASS** | The graphical encounter issued move, attack, and attack-move orders; an earlier graphical run issued hold and stop. All six Marines accepted squad orders. |
| Commander authorization and command-result feedback | **PASS** | Plugin regression rejects a non-commander; live command acknowledgments were accepted and the squad window displayed “Order 6 accepted.” |

### D. Combat and scenario lifecycle

| Criterion | Status | Evidence |
| --- | --- | --- |
| Zerglings use native movement and combat against Marines and park structures | **PASS** | The graphical capture recorded Zergling movement and deaths, Marine HP falling from 40 to 35, native Marine attacks, and carousel demolition followed by defeat. |
| Critical structures have the configured target proxies and footprints | **PASS** | Frontier initialization linked 27 targets; the carousel used its configured proxy and footprint, and its confirmed demolition retired that target. |
| Shared health remains synchronized across multiple proxies for one structure | **DEFERRED** | Each tested structure uses one native proxy, so a multi-proxy shared-health case was not exercised. |
| Demolition updates OpenRCT2, retires the target, and updates navigation | **PASS** | The capture confirmed wall and carousel removal; navigation acknowledgments and observed wall traversal follow. The native test also observed traversal through the demolished carousel footprint. |
| Authoritative victory and defeat conditions | **DEFERRED** | The recorded run reached an authoritative defeat (`marines=6 zerglings=10` at objective loss). Victory by eliminating every Zergling while preserving the carousel was not exercised. |
| Clean scenario restart/reconnect without duplicate entities | **DEFERRED** | A live Frontier scenario restart/reconnect cycle with entity counts compared before and after has not been run. |

### E. Multiplayer and regression

| Criterion | Status | Evidence |
| --- | --- | --- |
| Two graphical clients show consistent movement, combat, and destruction | **PASS** | The recording compares 321 shared snapshot sequences with zero mismatches; both clients joined the same normal OpenRCT2 host. |
| Existing Go, C++, JavaScript, Python, and integration regressions | **FAIL** | Go, C++, JavaScript, Python, and the Frontier native-navigation test passed; the generic `tests/test_world_live.sh` ride attack did not finish before timeout. No Java suite exists (see above). |
| Normal gameplay works without test probes or hardcoded actions | **PASS** | The demonstration used the normal launcher and mouse/keyboard input through the OpenRCT2 interface. Probe plugins were limited to automated test fixtures. |

## Recorded demonstration

The capture verifier reports `demonstration_complete: true`. The two graphical clients show squad selection and commands, Zergling obstacle navigation and combat, carousel demolition, Marines crossing a demolished wall, and an authoritative defeat. Artifacts are published through the Pi artifact viewer:

- [Run page](https://raspberrypi.tail628049.ts.net:8443/runs/20261012T195837Z-5c59c8cfe115)
- [Combined two-client video](https://raspberrypi.tail628049.ts.net:8443/media/20261012T195837Z-5c59c8cfe115/combined.mp4)
- [Client A final screenshot](https://raspberrypi.tail628049.ts.net:8443/media/20261012T195837Z-5c59c8cfe115/client-a-final.png)
- [Client B final screenshot](https://raspberrypi.tail628049.ts.net:8443/media/20261012T195837Z-5c59c8cfe115/client-b-final.png)
- Local evidence directory: `run-data/artifacts/20261012T195837Z-5c59c8cfe115/` (video, four screenshots, logs, scenario config, and `verification.json`).
- Native navigation evidence: `run-data/frontier-native-nav-1791834732/`.
- Live controls capture (the overall run is marked failed because it did not include opened-wall traversal): [run page](https://raspberrypi.tail628049.ts.net:8443/runs/20261012T201917Z-54511633fdcc). Its [drag rectangle](https://raspberrypi.tail628049.ts.net:8443/media/20261012T201917Z-54511633fdcc/client-a-t0.png), [cleared group](https://raspberrypi.tail628049.ts.net:8443/media/20261012T201917Z-54511633fdcc/client-a-t1.png), [recalled group](https://raspberrypi.tail628049.ts.net:8443/media/20261012T201917Z-54511633fdcc/client-a-t2.png), [click selection](https://raspberrypi.tail628049.ts.net:8443/media/20261012T201917Z-54511633fdcc/client-a-t3.png), and [Shift-click selection](https://raspberrypi.tail628049.ts.net:8443/media/20261012T201917Z-54511633fdcc/client-a-t4.png). Logs and metadata are in `run-data/artifacts/20261012T201917Z-54511633fdcc/`.

The run page and video returned HTTP 200 through the Pi's private Tailscale viewer. The video is a direct X11 recording of two OpenRCT2 clients; gameplay was not synthesized.

## Known bugs and remaining limitations

- Victory and a clean Frontier scenario restart/reconnect need live verification.
- Native navigation was verified on the Frontier geometry and tested destruction routes; arbitrary park terrain and height combinations are outside this run.
- Combat proxies use OpenBW's Terran Civilian unit and its small native hitbox. Target placement remains bounded by supported native proxies; generic world sessions can report unsupported targets.
- Live construction and path objects as combat targets remain unsupported.
- The generic adapter's broad target-coverage limits and cross-process target association remain as described in [OpenBW adapter status](openbw-adapter-status.md).
- The generic 4,426-entity park live regression has unstable structure-target validation for a new client. One run repeatedly returned `Invalid Zergling target`; another accepted the attack but did not demolish the selected ride within 180 seconds. Frontier Outpost's graphical combat and demolition scenario passed.
