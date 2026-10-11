# Frontier defense live demo

This scenario puts four real OpenBW Marines and eight real OpenBW Zerglings in the existing Frontier Carousel park. Two OpenBW/BWAPI processes use the supported `LOCAL` transport. The Zerg endpoint publishes complete v3 snapshots; the Terran endpoint owns Marine orders. The OpenRCT2 server validates snapshots and player commands, distributes unit state through a synchronized custom action, and demolishes the carousel once its OpenBW Missile Turret proxy is destroyed.

`Game::switchToPlayer()` only switches a slot before a game starts in the pinned OpenBW/BWAPI implementation. A Zerg controller's orders to Marines are rejected with `Unit_Not_Owned`. The second synchronized BWAPI process is therefore required for player commands. Neither the plugin nor the native renderer computes damage or moves units independently.

## Build and run on the Pi

```sh
python3 scripts/prepare-starcraft-sprites.py --unit zergling
python3 scripts/prepare-starcraft-sprites.py --unit marine
BRIDGE_SPRITE_SOURCE=starcraft-local scripts/build-openrct2.sh
scripts/install-openrct2-local.sh
scripts/build-bridge-module.sh
python3 scripts/create-render-test-park.py --scenario frontier-defense
python3 scripts/create-ride-siege-map.py --scenario frontier-defense \
  --output run-data/frontier-defense-map/frontier-defense.scm
python3 scripts/capture-live-demo.py --scenario frontier-defense \
  --record-video --video-layout combined --verify-combat
```

Set `STARCRAFT_DATA_DIR` to the directory containing the locally licensed `StarDat.mpq`, `BrooDat.mpq`, and `Patch_rt.mpq` before running OpenBW. The capture command starts the park server, both OpenBW factions, and two graphical clients; it also regenerates the map and park fixtures as needed. Run the public build with `BRIDGE_SPRITE_SOURCE=alien-scout`; it uses an original CC0 human soldier placeholder when local Marine art is absent. The proprietary GRP, extracted PNGs, and built g2.dat stay under ignored `run-data/`, `upstream/`, and `build/` paths.
The `--verify-combat` gate also uses `xdotool` to exercise real map clicks and right-click orders in the graphical client.

## Controls

Click a Marine to select it. Shift and click to add or remove Marines from the squad. Right click a ground point to move the selection; right click a Zergling to attack it. Press **H** to hold position. **M** toggles additive selection without holding Shift. The native custom map tool supplies `onRightClick`; OpenRCT2's shortcut manager intentionally reserves the right mouse button. The OpenRCT2 server checks that each selected ID is a living Terran Marine in the current session and that an attack target is a living Zergling. The Terran BWAPI controller checks ownership again and sends an explicit command result to the requesting player.

## Verification

The capture run writes a combined MP4, ten battle screenshots, Zerg and Terran logs, OpenRCT2 logs, scenario configuration, and `verification.json` to one artifact run under `run-data/artifacts/`. The Pi artifact viewer indexes that directory. A passing result requires twelve initial native actors, real Marine attack frames, damage to Zerglings, combat deaths, two agreeing OpenBW state digests, matching server and client snapshots, a client Marine movement order and Zergling attack order accepted by Terran BWAPI, an actual map click and right-click movement order with position change, and one carousel demolition. The command probe is a local plugin installed only in client A for the additional automated orders; the map control check uses X11 mouse input against the running client.

The only upstream engine changes are the OpenRCT2 native painter and map interaction binding, plus a BWAPI pregame slot selection patch for deterministic local multiplayer ownership. OpenBW simulation internals are unchanged. The current scenario uses a fixed clear combat lane; it does not map arbitrary park obstacles into OpenBW pathfinding.

## Verified Pi run

Run `20261011T160310Z-eb31e11bb497` passed on 2026-10-11 with client B rotated. It recorded 12 initial units, 28 Marine attack frames, six combat deaths, 38 carousel damage events, one demolition, 90 matching OpenRCT2 snapshots, a map-selected Marine moving after a right-click order, and a Terran BWAPI attack order accepted against a Zergling. Its combined MP4, ten screenshots, six filtered logs, configuration, and verification JSON are in `run-data/artifacts/20261011T160310Z-eb31e11bb497/` and on the [private Pi artifact viewer](https://raspberrypi.tail628049.ts.net:8443/runs/20261011T160310Z-eb31e11bb497).
This run includes the facing correction: the native painter projects each OpenBW heading through the active isometric camera rotation before choosing a directional sprite. For example, a Marine shooting west in OpenBW points northeast in client A's unrotated view and southeast in client B's quarter-turned view.
The viewer's `commit_sha` records the baseline HEAD (`a1ee4c1`); this implementation is currently in uncommitted workspace changes.

The controlled map deliberately has a clear combat lane. Park terrain and arbitrary obstacles are not converted into OpenBW navigation. The carousel proxy is a preplaced Terran Missile Turret with 200 HP; its identity and placement are checked before demolition.
