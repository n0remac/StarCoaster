# Asset and source inventory

This inventory records what the current checkout contains. It is not a determination of redistribution rights.

| Component | Evidence in pinned checkout | Project treatment |
| --- | --- | --- |
| OpenBW/BWAPI fork | [Pinned `LICENSE`](https://github.com/OpenBW/bwapi/blob/48124ba8ed1b4d52b3dfd52acbaf34afb9a37fe2/LICENSE) contains LGPL version 3 | Keep as a separate upstream checkout and record its exact commit |
| OpenBW core | No top-level license file found in the pinned `upstream/openbw` checkout | Resolve source and binary distribution terms before publishing a combined build |
| OpenRCT2 | [Pinned `licence.txt`](https://github.com/OpenRCT2/OpenRCT2/blob/33aacdeb0d9e22c1622acf071e6698f946365453/licence.txt) contains GPL version 3 | Keep native changes as reviewable patches against the pinned checkout |
| StarCraft MPQs and maps | User-supplied game data required by the [BWAPI fork](https://github.com/OpenBW/bwapi/blob/develop-openbw/README.md) | Never commit or bundle game data |
| RCT2 or RCT Classic assets | [Required by OpenRCT2 for gameplay](https://docs.openrct2.io/en/latest/faq/installing.html) | Never commit or bundle game data |
| Alien scout art | No art created or selected yet | Add only original or verified openly licensed work with attribution |

The `.gitignore` excludes the local `upstream/`, `build/`, and `run-data/` directories and common MPQ files. Check any new asset path before committing or packaging it.
