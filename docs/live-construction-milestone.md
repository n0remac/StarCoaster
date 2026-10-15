# Live park construction synchronization

OpenRCT2 construction now updates the running OpenBW match through the shared
world bridge. OpenRCT2 owns the park state, OpenBW owns actor movement and
combat, and the bridge stages one ordered world revision at a time. The feature
does not start the proposed Mt. Zergling scenario.

## Lifecycle and ownership

The authoritative OpenRCT2 server listens for successful synchronized
construction actions, debounces them for six park ticks, and compares a
normalized discovery pass with the last synchronized world. It also scans at a
low frequency for missed supported changes. The confirmed baseline advances
only after `world.patch.status: synchronized`; later edits remain queued while
a patch is in flight. An oversized batch requests a full authoritative
snapshot. Geometry comparison ignores display names, entity revision stamps,
and runtime combat HP.

The observed action families are `ridecreate`, `trackplace`, `trackremove`,
`ridedemolish`, `wallplace`, `wallremove`, `smallsceneryplace`,
`smallsceneryremove`, `largesceneryplace`, `largesceneryremove`,
`footpathplace`, `footpathremove`, `landsetheight`, and `watersetheight`.
Ordinary track edits retain the ride's `openrct2:ride:<native ID>#<generation>`
identity. Successful demolition and recreation actions advance the generation
even when OpenRCT2 recycles its ride ID. Scenery and wall removals likewise
retire the old generation. Repeated discovery does not change a continuing
object's generation. If OpenRCT2 misses both lifetime actions and the object
reappears with exactly the same key between reconciliation scans, the plugin
cannot prove a new lifetime and conservatively treats it as continuing.

`world.patch` carries a stable patch ID, session, base/result revisions,
additions, modifications, removals, terrain replacements, and exact operation
counts. Its envelope is capped at 1 MiB and 4,096 operations. Go validates
the entire mapped candidate registry and derives navigation before staging;
validation failure leaves the confirmed registry unchanged. Receipt
acknowledgement means staged, not synchronized. Both OpenBW participants
stage the same hash, report current frames, accept a common future frame,
apply there, and report the actual result. The bridge confirms matching
revision, frame, and hash before publishing the new target catalog. Unchanged
navigation hashes advance the revision without rebuilding native path regions.
`navigation.mask.cancel` and full-snapshot reconciliation supersede unresolved
native staging.

Manual removal and combat destruction use the same revision sequence while
retaining distinct outcome history. A confirmed combat removal becomes a
synthetic `combat:<event ID>` one-removal patch. Its dead proxy retires at park
confirmation, and its geometry commits only after both native participants
apply the revision. A manually removed required objective records
`objective_removed` and a durable defeat without a combat destruction event.
Commands that arrive during an update are queued with their original IDs;
spawn journals and scenario wave state continue independently.

New targetable rides and shops use the existing asynchronous native proxy
creation and association flow. Footprint modifications keep canonical
identity and HP. If a proxy cannot remain near its footprint, controlled
replacement retires the old binding and restores remaining HP before the new
binding becomes commandable. Manual demolition invalidates the binding.
Capacity and placement failures leave valid navigation geometry in place and
report an unsupported reason. Same-session snapshot recovery reconciles
targets and actors, preserves continuing HP and spawn progress, and replays a
zero-HP native target that died while the bridge was disconnected so it cannot
reappear at full health.

## Supported geometry and limits

Live wall edges, solid small and large scenery, ground paths, ride and shop
footprints, supported land height and slope changes, and water changes use the
existing planar navigation derivation. New collision on a live actor produces
`occupied_construction_geometry`, leaves the world unsynchronized, and
recovers after the conflicting obstacle is removed. Unsupported overlapping
walking layers, incompatible slope encodings, and multiple ground paths at a
single tile fail explicitly. The native map limit remains 256×256. A purely
visual edit can change the world revision with no native navigation rebuild.

## Verification and evidence

All generated logs, licensed data, maps, screenshots, and videos remain under
ignored `run-data/`. The final offline `scripts/project.sh test` run passed
Go, three C++ tests, 75 Python tests (one skipped), and JavaScript plugin
validation; see `run-data/offline-after-owner.log`. The native module rebuilt
with `scripts/build-bridge-module.sh`; see `run-data/module-build-final.log`.

| Command or case | Result and local evidence |
| --- | --- |
| `scripts/project.sh test-live-construction` | Passed all 15 sequential native cases in `run-data/test-live-construction-complete.log`. Earlier combined runs exposed an overlap assertion that matched a later valid revision and a commander join race in the outage-death probe; both test drivers were corrected before this clean run. |
| Wall build and removal with native movement | Passed: `run-data/live-construction-nav-1792047284/verification.json`. Both native masks applied at frames 379 and 656; the same Marine rerouted and then crossed the reopened route. |
| Six-action path, wall, scenery batch | Passed: `run-data/live-construction-batch-1792047321/verification.json`; one patch and one native update. |
| Runtime target creation, attack, destruction | Passed: `run-data/live-construction-targets-1792049201/verification.json`; two-client catalog changed as proxy became usable and retired. |
| Ride footprint modification and HP | Passed: `run-data/live-construction-modification-1792049274/verification.json`; stable ride ID, controlled replacement, preserved 34 HP. |
| Concurrent construction and combat | Passed: `run-data/live-construction-concurrent-1792048456/verification.json`; consecutive revisions and one removal. |
| Manual removal, target capacity, actor overlap | Passed: `run-data/live-construction-manual-1792048413/`, `run-data/live-construction-capacity-1792048529/`, `run-data/live-construction-overlap-1792048601/`. |
| Terrain, scenery, paths, unchanged hash | Passed: `run-data/live-construction-terrain-1792048633/`, `run-data/live-construction-scenery-path-1792048694/`, `run-data/live-construction-unchanged-1792048737/`. An invalid slope rejected atomically and recovered. |
| Bridge restart, interrupted update, death during outage | Passed: `run-data/live-construction-recovery-1792048769/`, `run-data/live-construction-interrupted-1792048849/`, `run-data/live-construction-death-recovery-1792049115/`. |
| Manual required objective | Passed: `run-data/live-objective-manual-1792049168/verification.json`. |
| Frontier and Midway navigation | Passed: `run-data/frontier-outpost-native-nav-1792046834/` and `run-data/midway-junction-native-nav-1792046728/`. The latter checked actual post-gate native movement. |
| Frontier scenario runtime and spawn recovery | Focused rerun passed: `run-data/scenario-runtime-live-1792050030/`. Both Marine spawn recovery hooks passed: `run-data/unit-spawn-live-1792049990/` and `run-data/unit-spawn-live-1792050016/`. |
| Midway outcomes | Defeat passed at `run-data/midway-live-defeat-1792046677/`. Victory remained intermittent: recent runs ended in genuine native combat defeat when reinforcements died or were delayed; see `run-data/midway-live-victory-1792050300/` and `run-data/midway-live-victory-1792050409/`. An earlier run passed at `run-data/midway-live-victory-1792001881/`. |
| Full native suite | `scripts/project.sh test-live` passed Ridge, Frontier navigation, 256×256 navigation, world synchronization, two lifecycle cycles, normal Marine/Zergling spawning, and graphical playable start; it stopped on an intermittent Frontier scenario defeat at `run-data/scenario-runtime-live-1792047132/`. The focused scenario rerun passed above. See `run-data/test-live-final.log`. |
| Two-client graphical capture | `scripts/project.sh record --scenario frontier-outpost --duration 70 --video-layout combined --live-construction` passed construction-specific checks at `run-data/artifacts/20261015T073735Z-cf9d912e44d6/`. It contains `combined.mp4`, two final PNGs, logs, and `verification.json`. The generic recorder's drag-selection criterion is unrelated to this construction capture, so its detailed status is `capture_only` while `capture_complete` is true. |

The optional `Mt. Zergling.park` local fixture was absent, so no authored-park
validation was run. Native proxy placement failure was not separately forced;
capacity failure and navigation retention were exercised. Midway victory and
the full aggregate native suite should be rerun when the reinforcement test's
tactical timing is stabilized. These limits do not change the successful
generic live-construction wall, target, overlap, and recovery checks above.

## One-run performance samples

Measurements are from the actual native wall and six-action batch runs, not
an estimate of an incremental navigation algorithm. One complete derivation
per batch is used.

| Metric | One wall | Six actions in one batch |
| --- | ---: | ---: |
| Action to detection | 221 ms | 269 ms |
| Detection to patch emission | 0 ms at millisecond resolution | 0 ms at millisecond resolution |
| Go validation including navigation | 8 ms | 8 ms |
| Navigation derivation | 3.538 ms | 3.338 ms |
| Selected native lead | 96 frames | 96 frames |
| Publisher/controller native rebuild | 22.694 / 23.413 ms | 16.064 / 17.533 ms |
| Target reconciliation | 91 ms | 177 ms |
| End-to-end bridge synchronization | 4,346 ms | 4,435 ms |
| Native navigation updates per batch | 1 | 1 |

The rebuild occupies one native application frame; its measured work was
16–23 ms in these runs. Sustained tick jitter was not independently sampled.
The unchanged-hash case reported `unchanged=1` and skipped path-region
rebuilding. Most synchronization latency is the conservative common-frame
lead; reducing it requires measuring communication delay under load while
preserving both participants' on-time application checks.
