# Two-sided OpenBW combat feasibility — resolved 2026-10-10

## Cause and fix

The pinned OpenBW engine randomizes player slots for melee games in `sync.h`. The default patrol map, `ZergTest.scm`, contains slots with different alliance relationships. The player entries are shuffled at match start, while the alliance matrix is indexed by slot. In some launches the Zerg and Terran players land in slots that are not mutually hostile. The Zerg BWAPI module can change only its own alliance, so this produced a one-way fight. Other launches of the same map happened to start in mutually hostile slots and showed automatic Marine retaliation.

No engine or BWAPI modification is needed for this proof of concept. The battle scenario now defaults to the pinned BWAPI test map `testmap1.scm`, which yielded mutually hostile active players across the repeated tests. The normal patrol scenario retains `ZergTest.scm`. `BRIDGE_MAP_FILE` still overrides either default for explicit experiments. This is a scenario-specific configuration change, not a change to BWAPI's `setAlliance()` semantics or unit ownership rules.

The Marine units begin in `PlayerGuard`. Once Zerglings approach, OpenBW changes Marine orders to `AttackUnit`, sets a Zergling order target, enters attack frames, applies weapon damage, and emits unit destruction events. The bridge supplies only Zergling attack-move orders. It does not order Marines, calculate damage, alter HP, or call `killUnit()` in battle mode.

## Reproduce

```bash
scripts/build-bwapi.sh
scripts/build-bridge-module.sh
STARCRAFT_DATA_DIR=/path/to/your/starcraft-data \
  python3 scripts/test-battle-feasibility.py --seconds 20
```

The test writes ignored logs under `run-data/battle-feasibility/`. It requires 4 Marines, 8 Zerglings, 12 unique IDs, distinct owners, mutual hostility at initialization and contact, 8 accepted Zergling orders, a Marine attack frame aimed at a registered Zergling, HP loss in both factions, an event-backed combat death, and a non-timeout outcome.

Five consecutive battle runs passed (`trial-1.log` through `trial-5.log`). A later default-paced 20-second run also passed (`final-default.log`): 17 Marine attack-frame transitions, 28 Marine HP decrease events, 14 Zergling HP decrease events, 4 Marine deaths, and 2 Zergling deaths. OpenBW reported a Zerg victory at frame 144. Exact kill counts are not assumed stable across runs.

The ownership probe (`ownership-probe.log`) passed the battle gate while all four attempted Zerg-controller orders on Terran Marines were rejected with `Unit_Not_Owned`. The old-map negative case (`legacy-map-1.log`, `BRIDGE_MAP_FILE=.../ZergTest.scm`) failed the gate with one-way hostility, no Marine attack, and no Zergling HP loss. That map can also start with mutual hostility, so it is unsuitable as a deterministic battle default.

The standard one-Zergling and eight-Zergling headless patrol smoke tests both passed after the map selection change. No StarCraft archives, Blizzard sprites, or captured artwork were added to Git.

## Constraints and next milestone

This solution proves one headless, single-owner OpenBW simulation with automatic Terran defense. It does not add general faction control or solve two-controller multiplayer setup. The current battle probe does not publish protocol v2 or render the battle in OpenRCT2. The next milestone is to carry authoritative combat state through the bridge and native renderer, then verify it on both graphical clients.
