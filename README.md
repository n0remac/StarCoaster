# Passthrough RTS Bridge

This project shows genuine OpenBW Marines and Zerglings fighting around a real carousel inside a shared OpenRCT2 park. OpenBW/BWAPI owns movement and combat; an OpenRCT2 multiplayer server distributes full snapshots to two modified graphical clients. The earlier one-unit and eight-Zergling demos remain available. The public build uses original CC0 placeholder art; an opt-in local build renders graphics extracted from the user's classic StarCraft installation.

Start with the [Rev 2 implementation specification](docs/specification.md), [repository layout](docs/repository-layout.md), [bootstrap guide](docs/bootstrap.md), and [local Zergling rendering guide](docs/rendering-phase.md). The [bridge protocol](bridge-protocol/README.md) has the first schema and fixture. The earlier Recoil/Minecraft proposal and Raspberry Pi assessment are kept in the [documentation archive](docs/archive/README.md) for historical reference.

The working tree keeps pinned upstream checkouts under ignored `upstream/`; `scripts/fetch-upstream.py` restores them after cloning this Git repository. The tracked source includes build scripts, a BWAPI module, an OpenRCT2 native render patch, and a server-distributed plugin. A 65-second rendering run on this Pi showed the locally extracted Zergling on two graphical clients, including scenery occlusion, elevation, all four camera rotations, animation, publisher removal, and return. All 657 common snapshots matched in session, tick, identity, motion, and position with no desync warning. See the [rendering guide](docs/rendering-phase.md) and [earlier flat-map test record](docs/headless-test-2026-10-10.md).

To repeat the squad recording here after building, run `DEMO_PARK=run-data/park-generator/save/bridge-render-test.park DEMO_OUTPUT_DIR=run-data/squad-demo python3 scripts/capture-live-demo.py --seconds 65 --demo-units 8 --verify-units --verify-animation --cycle-rotations --publisher-restart --record-video --video-layout combined --video-fps 10 --video-crf 28`. It uses the user-supplied game data at `/home/pi/games/starcraft` and `/home/pi/games/rct2`, starts two virtual displays, and saves MP4, screenshots, logs, and verification metadata under ignored `run-data/squad-demo/`. The game assets and captured RCT2 graphics are kept out of Git. See [squad phase](docs/squad-phase.md).

To record both graphical clients in one side-by-side MP4, install FFmpeg (`sudo apt-get install ffmpeg`) and add `--record-video`. Set `DEMO_OUTPUT_DIR=run-data/zergling-video` to choose an artifact directory. The video, `video-capture.log`, and `video-metadata.json` sit beside the original PNG screenshots; the PNGs remain the source for exact sprite checks. See [video capture and remote viewing](docs/rendering-phase.md#video-capture-and-remote-review).

## Remote test viewer

The StarCoaster artifact viewer collects new graphical captures and composited battle replays under `run-data/artifacts/` with unique run IDs. Its read-only Go server shows recent runs, validated MP4s with seeking, screenshots, verification results, event timelines, and filtered diagnostic logs. By default it listens on `127.0.0.1:8787` and is exposed privately with Tailscale Serve on port 8443. See the [viewer setup and Pi deployment guide](docs/test-viewer.md) for build, user service, Tailscale, API, and maintenance commands.

## Live ride siege

The ride siege demo starts from a separate park with a real, closed merry-go-round named **Frontier Carousel**. Eight OpenBW Zerglings attack a preplaced hostile Missile Turret proxy. OpenBW owns its 200 HP and weapon damage; after its death, the OpenRCT2 server issues one native `ridedemolish` action. Two graphical clients record the live synchronized result. The older patrol and composited battle replay demos remain available.

```sh
python3 scripts/create-render-test-park.py --scenario ride-siege
python3 scripts/create-render-test-park.py --scenario ride-siege --probe-demolition
python3 scripts/verify-ride-siege-headless.py
python3 scripts/capture-live-demo.py --scenario ride-siege --verify-destruction \
  --record-video --video-layout combined
```

The final command publishes a unique artifact run automatically. See the [ride siege guide](docs/ride-siege.md) for the map construction, coordinate mapping, startup order, verification, and private viewer URL.

## Park assault

The [Frontier Outpost park assault](docs/park-assault.md) adds a 48 × 48 tile developed park, real paths and scenery, clearance-aware navigation, and three separately destructible park structures. One OpenBW simulation controls 20 Zerglings in three squads while two graphical OpenRCT2 clients show the same native ride demolitions.

```sh
python3 scripts/verify-park-assault-headless.py
python3 scripts/capture-live-demo.py --scenario park-assault \
  --verify-destruction --record-video --video-layout combined
```

## Native Marine defense

The [Frontier defense guide](docs/frontier-defense.md) covers local Marine sprite extraction, the two faction OpenBW setup, map controls, and the verified two client recording. To run the complete live gate after building:

```sh
python3 scripts/capture-live-demo.py --scenario frontier-defense \
  --record-video --video-layout combined --verify-combat
```

This capture uses native OpenRCT2 sprites and live OpenBW combat. The older composited battle replay is a separate historical feasibility artifact.
