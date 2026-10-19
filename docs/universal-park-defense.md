# StarCraft Defense in an existing park

Use an ordinary OpenRCT2 `.park` save with a built native installation:

```sh
scripts/project.sh play --park /path/to/your-park.park
```

To build and start the native server and private browser client together:

```sh
scripts/project.sh start --park /path/to/your-park.park --browser
```

The launcher inspects the save, creates a working copy and navigation map under
ignored `run-data/`, and leaves the source save untouched. The current native
map supports parks up to 256 × 256 tiles. Set `RCT2_DATA_DIR` and
`STARCRAFT_DATA_DIR` to the locally licensed installations. Original StarCraft
graphics are the default visual source for native and private WASM builds; the
build reports missing or stale licensed graphics. `BRIDGE_SPRITE_SOURCE=alien-scout`
is an explicit development fallback.

Open **StarCraft Defense** from the OpenRCT2 plugin menu. Select a valid tile
near the park edge, then enable Zerg waves. The first wave begins after 120
OpenBW seconds; later waves recur every 120 seconds from the selected zone.
Disabling defense stops future automatic waves but leaves existing enemies in
the park. Re-enabling starts a fresh preparation countdown. The current Terran
commander can change these settings; other players can view the status.

The StarCraft Construction window offers Barracks, Academy, Supply Depot,
Factory, and Armory. Terran minerals and gas display as unlimited. OpenBW still
controls supply, prerequisites, training time, movement, and combat. Park rides,
guests, and finances continue through OpenRCT2.

The defense configuration and active waves are journaled under `run-data/` for
bridge recovery. The selected spawn zone and countdown survive a browser
reconnect. The generated scenario uses the existing wave tiers: eight
Zerglings for waves 1–2, seven Zerglings and two Hydralisks for waves 3–5,
then an Ultralisk joins each later wave.

## Verification on the Pi

The live fixture script saves an ordinary copy of the Frontier park with its
authored objective removed. It does not edit the input save:

```sh
python3 tests/prepare_universal_park_fixture.py
UNIVERSAL_DEFENSE_SOURCE="$PWD/run-data/universal-park-defense-live/fixture/save/ordinary-frontier-park.park" \
  python3 tests/test_universal_park_defense_live.py --manual --observe-combat
UNIVERSAL_DEFENSE_SOURCE="$PWD/run-data/universal-park-defense-live/fixture/save/ordinary-frontier-park.park" \
  python3 tests/test_universal_park_defense_live.py --factory
UNIVERSAL_DEFENSE_SOURCE="$PWD/run-data/universal-park-defense-live/fixture/save/ordinary-frontier-park.park" \
  python3 tests/test_universal_park_defense_live.py --wasm
UNIVERSAL_DEFENSE_SOURCE="$PWD/run-data/universal-park-defense-live/fixture/save/ordinary-frontier-park.park" \
  python3 tests/test_universal_park_defense_live.py --wasm --browser-build --capture-only
```

Use isolated network namespaces when another StarCoaster session already owns
the native ports. The mixed check uses the private bundle in
`run-data/universal-defense-deploy/current` and writes
`run-data/universal-park-defense-live/mixed/verification.json`, screenshots,
and `browser-gameplay.mp4`. It verifies a visible park, native Zerglings,
fixed-zone placement, browser reconnect, and no duplicate accepted wave.
The Factory check confirms native Marine and Vulture training; the combat
check confirms ordered demolition without repeated park snapshots. The
browser-build check confirms Barracks placement and Marine training issued by
the browser commander and accepted by OpenBW. Run
`scripts/project.sh test` and private `scripts/project.sh test-wasm` for offline
and asset-provisioning coverage. All recordings, browser profiles, generated
parks, and licensed assets stay in ignored directories.

The playable graphical check uses a 64 × 64 park. Highly fragmented saves can
reach OpenBW's native region-count limit before the 256 × 256 size limit; the
launcher reports that navigation error. The current graphical recording shows
moving Zergling sprites, but it does not separately exercise every building
animation and command icon. Browser reconnect and native bridge restart have
separate live checks; a browser-connected bridge restart was not captured.
