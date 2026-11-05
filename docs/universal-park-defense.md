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

Zerg waves are enabled automatically when the park and native participants are
ready. The first wave begins after 120 OpenBW simulation seconds; later waves
recur every 120 seconds. Each wave uses one randomly selected reachable edge
cluster. No spawn point selection is required. Open the normal OpenRCT2 top
toolbar **Map → StarCraft Settings** menu item to change difficulty, wave
interval, or whether new waves are enabled. This menu item is provided by the
same plugin on native and private WASM clients.
Disabling defense stops future automatic waves but leaves existing enemies in
the park. Re-enabling starts a fresh preparation countdown. The current Terran
commander can change these settings; other players can view the status.

The StarCraft Construction window offers Barracks, Academy, Supply Depot,
Factory, and Armory. Terran minerals and gas display as unlimited. OpenBW still
controls supply, prerequisites, training time, movement, and combat. Park rides,
guests, and finances continue through OpenRCT2.

The defense configuration and active waves are journaled under `run-data/` for
bridge recovery. A committed wave's origin, nearby tiles, and composition survive
recovery; the preparation deadline is also journaled. The generated scenario
uses the existing wave tiers: eight Zerglings for waves 1–2, seven Zerglings
and two Hydralisks for waves 3–5,
then an Ultralisk joins each later wave.

## Verification on the Pi

The live fixture script saves an ordinary copy of the Frontier park with its
authored objective removed. It does not edit the input save:

```sh
python3 tests/prepare_universal_park_fixture.py
OPENRCT2_PORT=12153 STARCOASTER_BRIDGE_PORT=42110 \
BRIDGE_OPENBW_PORT=42111 BRIDGE_CONTROLLER_PORT=42112 \
UNIVERSAL_DEFENSE_SOURCE="$PWD/run-data/universal-park-defense-live/fixture/save/ordinary-frontier-park.park" \
  python3 tests/test_universal_park_defense_live.py
```

Use free isolated ports when another StarCoaster session is running. Each live
probe writes to a unique directory under `run-data/universal-park-defense-live/`
and checks its journal session against its current launch. A generated ordinary
park and a generated 256 × 256 park passed automatic startup, native clustered
spawn, and inward movement after the native route query was added. Exact reports
and remaining limits are in `docs/automatic-zerg-waves-verification.md`.

The mixed check uses the private bundle in
`run-data/universal-defense-deploy/current`; the automatic-wave mixed-client,
browser reconnect, and graphical menu checks remain outstanding.
The Factory check confirms native Marine and Vulture training; the combat
check confirms ordered demolition without repeated park snapshots. The
browser-build check confirms Barracks placement and Marine training issued by
the browser commander and accepted by OpenBW. The unauthorized check uses two
native clients to confirm a second player's disable attempt is rejected by
the server while defense remains enabled. Run
`scripts/project.sh test` and private `scripts/project.sh test-wasm` for offline
and asset-provisioning coverage. `tests/test_mt_zergling_gameplay_live.py`
exercises six native waves, including Hydralisks at wave three and an
Ultralisk at wave six; `tests/test_mixed_zerg_restart_live.py` checks actor
identity and request continuity after a Go bridge restart. All recordings,
browser profiles, generated parks, and licensed assets stay in ignored
directories.

`tests/test_shared_viewport_live.py` also checks a native graphical client:
Marine selection, ride and guest windows, park tools, and a squad order share
the viewport. Its ignored `ride.png` capture shows the park and Marine sprites.

The playable graphical check uses a 64 × 64 park. Highly fragmented saves can
reach OpenBW's native region-count limit before the 256 × 256 size limit; the
launcher reports that navigation error. The current graphical recording shows
moving Zergling sprites, but it does not separately exercise every building
animation and command icon. Browser reconnect and native bridge restart have
separate live checks; a browser-connected bridge restart was not captured.
