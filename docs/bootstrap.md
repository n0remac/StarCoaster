# Bootstrap

Use `scripts/project.sh start --scenario frontier-outpost` for the full fetch,
build, stage, and play flow. `scripts/start.sh` is the underlying bootstrap
entry point. Set `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR` to your own licensed
game installations; the defaults are `~/games/rct2` and `~/games/starcraft`.
The StarCraft directory must contain `StarDat.mpq`, `BrooDat.mpq`, and
`Patch_rt.mpq` (alternate capitalization for the first two is accepted).
User game data, extracted sprites, and built engines stay outside Git.

The pinned upstream revisions are in [`dependencies.lock.json`](../dependencies.lock.json).
For manual builds from the repository root:

```sh
python3 scripts/fetch-upstream.py
python3 scripts/check-dependencies.py
scripts/project.sh build
scripts/install-openrct2-local.sh
scripts/project.sh play frontier-outpost
```

The machine needs Go, CMake, Ninja, a C++ compiler, Python 3, `smpq`, and the
OpenRCT2 development libraries in its [Linux build guide](https://github.com/OpenRCT2/OpenRCT2/wiki/Building-OpenRCT2-on-Linux).
Graphical recording and live tests also need Xvfb, FFmpeg, and the local game
data. `BRIDGE_BUILD_JOBS=2` limits parallel build memory on the Pi.

The native OpenBW module has one gameplay mode: its publisher reports native
actors and targets, while its Terran controller applies authenticated Marine
commands on OpenBW frames. OpenRCT2 distributes the plugin to joined clients
and owns park discovery, demolition, multiplayer state, and rendering. The Go
world bridge coordinates snapshots and commands. `scripts/run-world-session.sh`
is the common runtime launcher used by package play and recording.

```sh
scripts/project.sh play example-defense --plan
scripts/project.sh park example-defense
scripts/project.sh record --scenario example-defense --duration 85
scripts/project.sh test
scripts/project.sh test-live
```

`play ID --plan` resolves paths without starting engines. `park ID` regenerates
only that package's park, fixture, and navigation export. `record --help` lists
video and test probe options. Captures and verification JSON stay under ignored
`run-data/`; see the [artifact viewer guide](test-viewer.md). Historical
prototype results are in [the archive](archive/README.md).
