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
`run-data/zerg-production-native-1792341479/verification.json`. The Hatchery
was completed, owned by player 0, and exposed larva ID 11. Native training
was accepted; minerals changed 100 to 50 and supply used changed 0 to 1. Both
participants saw incomplete Egg ID 11 with 420 build frames remaining, then
completed Zergling IDs 11 and 13 after the egg disappeared. This verifies
same-ID morphing and separate-ID twin creation in the pinned engine.

The probe currently exercises the positive prerequisite path with a completed
Spawning Pool and enough resources. Separate negative tests for absent Pool,
insufficient minerals, and supply cap are still needed. StarCoaster actor
registration and rendering do not yet expose larvae or incomplete eggs; this
report describes native behavior only.
