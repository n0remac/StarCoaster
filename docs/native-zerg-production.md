# Native Hatchery production probe

The pinned OpenBW implementation owns this entire path. A completed Hatchery's
`SpawningLarva` secondary order creates up to three connected larvae
(`upstream/openbw/bwgame.h`). BWAPI's `getLarva()` exposes those connected units,
and `Hatchery.train(Zerg_Zergling)` forwards the order to an available larva
(`upstream/bwapi/bwapi/BWAPIClient/Source/UnitImpl.cpp`). OpenBW's
`ZergUnitMorph` order changes that **same native unit** from Larva to an
incomplete Egg and then to a Zergling. `ZergBirth` creates the second Zergling
with a distinct native ID. No OpenBW patch was needed for these mechanics.

Run `RCT2_DATA_DIR=... STARCRAFT_DATA_DIR=... tests/test_zerg_production_native_live.sh`
after building the bridge module and world bridge. The test copies `mt-zergling`
into an ignored run directory, adds 100 native Zerg minerals and a map-only
Overlord, and uses the scenario's existing Hatchery and Spawning Pool. The
probe is enabled only by `BRIDGE_TEST_ZERG_PRODUCTION` and orders production
from the Zerg participant. Both participants record their observed state.

On 2026-10-18 the probe passed all eight checks under
`run-data/zerg-production-native-1792348998/verification.json`. The Hatchery
was completed, owned by player 0, and exposed larva ID 11. Native training
was accepted; minerals changed 100 to 50 and supply used changed 0 to 1. Both
participants saw incomplete Egg ID 11 with 420 build frames remaining, then
completed Zergling IDs 11 and 13 after the egg disappeared. This verifies
same-ID morphing and separate-ID twin creation in the pinned engine.

`tests/test_zerg_production_rejection_native_live.sh` passed all nine checks in
`run-data/zerg-production-rejection-1792348846/verification.json`. Its isolated
fixtures remove the native Spawning Pool in both participants, start with one
mineral, or fill native supply to 18/18 with test-only units. In each case
BWAPI `canTrain()` and `train()` reject the order, resources do not change,
and no Egg appears. The Pool fixture waits for BWAPI's completed Pool count
to reach zero before requesting production. These hooks stay in the native
verification probe and are never player controls.

## StarCoaster integration

Larvae enter the visible actor registry when OpenBW creates them. An incomplete
Egg also enters that registry. A type or completion change on an existing
native ID emits `actor.morph`; the canonical ID, generation, and participant
bindings remain intact. If OpenBW creates a different native ID, the ordinary
spawn path registers it separately. The bridge forwards native type, owner,
health, completion, and remaining build time in snapshots. Only completed,
controllable actors can receive combat commands.

The owning native participant publishes one `building.state` contract for each
supported building. Hatchery `getLarva()` and Egg `getHatchery()` provide larva
count and observed morph progress. Command readiness comes from BWAPI
`canTrain()`. The bridge adds scenario command authorization and forwards orders
to the owning native participant. `native-production-hud` is the isolated
fixture that authorizes owner 0; ordinary enemy Hatcheries remain read-only.
OpenBW still charges resources, enforces prerequisites and supply, and completes
production.

## Original graphics and button data

The local extraction pipeline reads Larva image 36, Egg image 21, Egg Spawn
image 23, Larva remnants image 37, and Egg remnants image 24 from the user's
licensed MPQs. It uses their pinned `iscript` sequences. The Egg starts with
GRP frames 20–23 at two native ticks each, then cycles frames 0–11. Its spawn
overlay plays frames 0–4 at five ticks each. Hatching waits one tick before
frames 12–19, two ticks each. Larva movement uses directional banks 0, 17,
34, 51, and 68 at one tick each. Larva death uses six two-tick frames and
three 25-tick frames; Egg death uses nine two-tick frames and three 25-tick
frames. The renderer stores per-frame waits and keeps death presentation alive
for the corresponding native duration. Contact sheets under
`run-data/artifacts/zerg-animation-contact-sheets/` label the source GRP frame
and wait for every pose.

The six currently executable training commands use original frames from
`unit/cmdbtns/cmdicons.grp`. BWAPI's pinned unit documentation provides the
icon frame IDs. The pinned BWAPI unit state does not publish usable original
button positions (`buttonset` is zeroed in `UnitUpdate.cpp`), so the common 3×3
card fills slots from native capabilities in generated declaration order.
Research and upgrades have no executable native bridge path yet; their slots
stay empty.

## Graphical verification

The two-client `native-production-hud` recording passed all 17 capture checks
under `run-data/artifacts/20261018T204345Z-7711c91fdf68/`. Its
`building-hud-gallery/` contains a labeled screenshot for each of the seven
building windows, including live camera viewports and the shared 3×3 card.
The same directory contains Barracks and Factory training screenshots, accepted
native result screenshots, and `combined.mp4`. Both clients observed the same
Larva, its incomplete Egg, and the distinct Zergling pair. The recording also
confirmed accepted Marine and Vulture training and native results reaching the
HUD. The before and after Armory demolition screenshots show the ordinary park
removal closing the inspector after native synchronization, with no stale
window left on screen. The scenario fixture and generated licensed images
remain under ignored `run-data/`; they are not source assets.

The current bridge exposes executable training commands only. BWAPI's existing
research and upgrade support has not been routed through the command contract,
so Academy, Armory, Supply Depot, and Spawning Pool show native status with
empty command slots. The Armory capture exercises ordinary park demolition;
combat demolition target invalidation is covered by the building inspector
regressions.

## Final verification

On 2026-10-18, `scripts/project.sh generate` and `scripts/project.sh build`
passed with the local licensed installations. `scripts/project.sh test` passed
the Go and C++ checks and 119 Python tests (one skipped). The complete
`scripts/project.sh test-live` suite passed; its local log is
`run-data/milestone-test-live-complete.log`. This includes both native Zerg
probes, actor restart and reconnect, scenario runtime, all live construction
cases, and the manual objective removal test. The graphical capture used
`scripts/project.sh record --scenario native-production-hud --native-production-hud --duration 85`
and produced the passing artifact above.
