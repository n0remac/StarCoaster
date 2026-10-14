> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Initial battle feasibility investigation — 2026-10-10

This is the historical failing result at commit `0e63433`. The gate now passes using a battle-only map configuration; see [the resolution](battle-feasibility-resolution-2026-10-10.md).

The first combat gate is **blocked** on the pinned OpenBW/BWAPI stack. The normal single-unit and eight-Zergling patrol smoke tests still pass. No protocol, renderer, park, or capture work was started for the battle.

## Reproduce

```bash
scripts/build-bridge-module.sh
STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 scripts/the former battle feasibility test --seconds 12
STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 scripts/the former battle feasibility test --seconds 12 --probe-enemy-orders
```

The StarCraft archive path is a local example; use your own installed game data. The two commands intentionally fail the gate and write ignored logs under `run-data/battle-feasibility/`.

## Observed simulation

* BWAPI registered eight Zerglings and four Marines with twelve unique unit IDs and distinct owners.
* All eight Zergling attack-move orders were accepted. OpenBW reduced Marine HP in normal combat and emitted four Marine destruction events. The battle ended with eight Zerglings and zero Marines.
* No Zergling HP decreased. No Marine attack frame or attack order was observed. The Marine faction did not fight back.
* `game->enemy()` returned null. The active Terran `Player` was found through `getPlayers()`. `game->setAlliance(terran, false, false)` succeeded, but the resulting relationship was one-way: Zerg saw Terran as hostile, while Terran did not see Zerg as hostile.
* Issuing `Unit::attack` on the enemy-owned Marines from the Zerg controller returned `Unit_Not_Owned` for all four. This rules out using the current single BWAPI module to give direct Marine orders.

The module never calls `killUnit()` in battle mode. The existing frame-850 scripted patrol death remains confined to patrol mode.

## Two-controller investigation

The pinned `BWAPILauncher` creates one `GameOwner` and loads one AI module. `GameImpl::switchToPlayer()` only switches before the game starts. The OpenBW data layer does expose multiplayer synchronization through `createMultiPlayerGame()` and local socket modes (`LOCAL`, `LOCAL_AUTO`), so two launcher processes appear to be the supported route to command both factions while retaining one synchronized simulation.

I launched two `BWAPILauncher` processes with separate runtime directories, Zerg/Terran race settings, `MULTI_PLAYER` auto menu, and a shared local socket path. Both remained before `onStart()` for 12–15 seconds; neither produced a battle event. This establishes that the initial two-process setup did not start a match, not that OpenBW multiplayer is impossible. The next investigation should instrument the multiplayer lobby and slot selection, then get both modules into one game. Each module must issue orders only to its own units, and the publisher must read one synchronized authoritative state. Bidirectional hostility, HP loss on both sides, and a combat death should be rerun through the gate before Phase 2.

## Current scope

`retired scenario mode` is an opt-in feasibility probe. It creates and tracks the two factions but does not publish protocol v2 snapshots or render the battle. The phase gate must pass before those features are implemented.
