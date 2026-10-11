# Marine versus Zergling replay video

The local `run-data/battle-demo/combined.mp4` is a 10 FPS H.264 replay of a real headless OpenBW fight. It shows four Terran Marines defending against eight attacking Zerglings over an empty OpenRCT2 park capture. Positions, facings, orders, firing frames, HP, deaths, and the outcome come from OpenBW's per-frame BWAPI log. Rendering is post-produced with locally extracted StarCraft sprites; this is **not footage of both live OpenRCT2 clients**. The native bridge still needs a battle-capable protocol and renderer before that capture can be made.

The recorded run has 27 Marine HP decrease events, 16 Zergling HP decrease events, four Marine deaths, three Zergling deaths, and a Zerg outcome. These counts are from this run and need not be identical in future runs. The video, source `bwapi.log`, verification JSON, video metadata, empty park background, and selected PNG frames are under ignored `run-data/battle-demo/`.

To regenerate from the locally installed StarCraft archives and the captured empty park scene:

```bash
scripts/build-bridge-module.sh
BRIDGE_BATTLE_TRACE=1 STARCRAFT_DATA_DIR=/path/to/starcraft-data \
  python3 scripts/test-battle-feasibility.py --seconds 12 --log-name video-source
STARCRAFT_DATA_DIR=/path/to/starcraft-data \
  python3 scripts/render-battle-replay.py
```

The renderer defaults to `run-data/final-render-demo/client-a-t20.png` as its empty park background. Pass `--background` to use another 1280×800 OpenRCT2 capture from the same camera angle. The source artwork and generated frames remain outside Git.

OpenBW facing values describe directions on its map. The replay projects those headings through the park camera before choosing an eight-direction sprite frame, so firing Marines and advancing Zerglings face their targets on screen.
