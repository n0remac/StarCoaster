# Mixed client verification

This controlled scenario uses the existing 64x64 Frontier Outpost park and six
native Marines. Its first automatic enemy wave is delayed beyond a browser
integration run so a Pi-hosted Chromium client can join, select a Marine, and
issue a synchronized order while a native client observes the same OpenBW
actors. The normal `park_defense` systems remain available, including manual
wave spawning. This package adds no gameplay protocol or browser logic.

Prepare the local park source after generating Frontier Outpost:

```sh
scripts/project.sh park frontier-outpost
mkdir -p run-data/wasm-mixed-client/source
cp run-data/frontier-playable/save/frontier-outpost-playable.park \
  'run-data/wasm-mixed-client/source/Frontier Outpost.park'
scripts/project.sh validate-scenario wasm-mixed-client
scripts/project.sh play wasm-mixed-client
```

The copied park and all resulting native maps remain under ignored `run-data/`.
