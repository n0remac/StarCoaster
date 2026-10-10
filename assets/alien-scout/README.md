# Alien scout art

This twelve-frame, four-direction creature was drawn for the bridge using the shapes in `generate.py`. It is an original stand-in for the prototype unit, with no StarCraft sprite pixels. The art and generator are released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The twelve 32×32 transparent PNGs in `sprites/` are generated from the source script.

Regenerate them with `python3 assets/alien-scout/generate.py` (requires Pillow and the pinned OpenRCT2 source checkout). The script matches opaque pixels to the nearest colors in OpenRCT2's standard indexed palette so the sprite importer preserves them.
