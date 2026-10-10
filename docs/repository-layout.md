# Repository layout

The project root is one Git repository. It tracks all bridge-owned source, patches, protocol definitions, openly licensed stand-in art, scripts, tests, and documentation together. No Git submodules are required for the bridge code.

| Path | Purpose | Tracked in bridge Git? |
| --- | --- | --- |
| `bridge-protocol/` | Wire schema and fixtures | Yes |
| `openbw-bwapi-module/` | BWAPI AI module and snapshot publisher | Yes |
| `openrct2-plugin/` | Server-distributed multiplayer plugin | Yes |
| `openrct2-patches/` | Reviewable native OpenRCT2 changes | Yes |
| `assets/alien-scout/` | Original CC0 stand-in art and generator | Yes |
| `scripts/`, `tests/`, `docs/` | Build, demo, checks, specifications, history | Yes |
| `dependencies.lock.json` | Exact upstream source revisions | Yes |
| `upstream/` | Local OpenBW, BWAPI, and OpenRCT2 checkouts | No; fetched at pinned revisions |
| `build/`, `run-data/`, `logs/`, `captures/` | Binaries, staged OpenRCT2 data, logs, screenshots | No |
| `game-data/`, `starcraft-data/`, `rct2-data/` | Optional local staging for user-supplied game files | No |

The existing game installations remain at `/home/pi/games/starcraft` and `/home/pi/games/rct2`, outside the repository. The run scripts refer to them through `STARCRAFT_DATA_DIR` and `RCT2_DATA_DIR`. StarCraft MPQs and RCT2 `.dat` files are also ignored by extension to reduce the chance of accidentally staging a copied file elsewhere in the tree. `git check-ignore -v <path>` shows which rule applies.

After a fresh clone, run `scripts/fetch-upstream.py`, then follow [bootstrap](bootstrap.md). The fetch script uses the exact commits in `dependencies.lock.json`; it keeps the engine source folders inside this project directory. This layout keeps bridge development in one Git history while retaining the upstream projects' own histories and avoiding a public copy of OpenBW before its redistribution terms are resolved. A fresh clone needs a network fetch and user-supplied game data to run the demo.

Before committing, inspect `git status --short` and `git diff --cached --name-only`. Review any file placed under `assets/` for its source and license. The local screenshots contain user-supplied RCT2 graphics and stay under ignored `run-data/`.
