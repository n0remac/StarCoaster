# Headless test record — 2026-10-10

Machine: Raspberry Pi, Linux AArch64. Test root: `/media/pi/media1/rts-bridge`.

## Checks performed

| Check | Result |
| --- | --- |
| `python3 scripts/check-dependencies.py` | Passed. OpenBW `4b046d5f`, BWAPI `48124ba8`, OpenRCT2 `33aacdeb` match the lock file. |
| `build/openrct2/openrct2-cli --version` | Passed: v0.5.5, Linux AArch64, network `0.5.5-2`, plugin API `124`. |
| `build/openrct2/openrct2 --version` | Passed with the same build and API versions. |
| `nm -D build/bridge-module/BridgeAIModule.so` | Passed: `gameInit` and `newAIModule` are exported. |
| `ctypes.CDLL` load of `BridgeAIModule.so` | Passed: the shared library loads on this Pi. |
| Local TCP fixture to `scripts/receive-snapshots.py` | Passed: three framed snapshots were received, including a reported position change. **This was fixture data, not OpenBW simulation.** |
| `BWAPILauncher` startup | Blocked: `Error: file_reader: failed to open ./Patch_rt.mpq for reading`. |
| `scripts/run-bwapi.sh` preflight | Correctly rejects the absent `StarDat.mpq` / `Stardat.mpq` data file. |
| `scripts/run-openrct2-host.sh` preflight | Correctly rejects the absent park file; RCT2 game assets are also absent. |

The fixture receiver prints `reported unit position changed (publisher not authenticated)`. That result establishes TCP framing and receiver behavior only. It does not establish that `createUnit`, `Unit::move`, or `getPosition` work at runtime.

## Screenshot status

No screenshot was produced. A headless host has no framebuffer to capture. A genuine screenshot of the requested result requires an offscreen graphical OpenRCT2 client, user-supplied RCT2 assets and a park, a successful OpenBW/BWAPI runtime gate with the required StarCraft MPQs and map, and the OpenRCT2 native renderer and multiplayer plugin. The latter two bridge components have not yet been implemented. A screenshot of a fixture or console would falsely imply the crossover is working.

## Inputs needed for the next runtime gate

- StarCraft: Brood War `StarDat.mpq` (or `Stardat.mpq`), `BrooDat.mpq` (or `Broodat.mpq`), and `Patch_rt.mpq`. The pinned BWAPI checkout supplies a `ZergTest.scm` test map, though its default movement points still need runtime validation.
- RollerCoaster Tycoon 2 or RCT Classic game files, plus a suitable `.park`, `.sv6`, or scenario file.

Keep these user-supplied files outside Git. The launch scripts stage paths under ignored `run-data/`.
