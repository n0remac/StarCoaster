# Native production HUD fixture

This package places all seven supported buildings in one park. The Barracks,
Academy, Supply Depot, Factory, and Armory are Terran-owned. The existing
western Hatchery and Spawning Pool are Zerg-owned. The map supplies the Zerg
participant with 500 minerals and an Overlord so native Zergling production can
run with OpenBW's normal prerequisite, cost, supply, and timing checks.

`production_control_owners: [0]` explicitly authorizes the multiplayer
commander to order the Zerg Hatchery in this test scenario. Other scenarios do
not grant that authority, so their enemy Hatcheries remain read-only. The
bridge and native Zerg participant still validate each production request.

The package uses the user's local Mt. Zergling park. Copy the licensed source
park to `run-data/native-production-hud/source/Mt. Zergling.park`, then run:

```sh
scripts/project.sh park native-production-hud
scripts/project.sh play native-production-hud
scripts/project.sh record --scenario native-production-hud --native-production-hud --duration 85
```

The recorder saves a labeled seven-building screenshot gallery and two-client
video in its ignored `run-data/artifacts/` output. Original StarCraft command
icons and Larva/Egg frames are extracted from the local licensed installation
by `scripts/start.sh`; generated images remain in ignored local directories.
