# Shared park and unit cursor input

Commit `5208dc9` reactivated the Marine selection tool whenever no other tool
was active. OpenRCT2 sends viewport left clicks to active tools and substitutes
their cursor for its normal entity hover handling. That made ordinary ride and
guest interactions unavailable even though construction tools still worked.

The native patch now registers a passive viewport interaction separately from
the active tool. It offers hover, mouse down, drag movement, release, and right
click to the plugin in the main viewport. Only an explicit boolean `true`
consumes an interaction. An unclaimed left release reaches
`ViewportInteractionLeftClick`; an unclaimed hover reaches
`ViewportInteractionLeftOver`. Those native functions retain authority over
ride/shop windows, guests, staff, vehicles, park entrances, balloons, and ducks.
Scenery and paths retain their usual contextual and editing behavior.

The plugin selects living player-owned Marines using compact screen footprints
around their rendered bodies and feet. Native projection accounts for terrain
height, rotation, visual movement, and zoom. Hidden actors are excluded. This
uses approximate footprints, not per-pixel sprite or occlusion testing. A unit
can take priority over a park object at the same screen position; Alt-click
bypasses the unit handler. A four-pixel drag threshold starts rectangle selection
and suppresses an incidental park click on release. Releasing over another
window cancels the gesture.

Park clicks preserve the selected squad. Right-click consumes input only when
it issues a squad order; Alt-right-click preserves OpenRCT2 context behavior.
The existing right-drag camera handling remains in OpenRCT2. Construction and
spawn tools retain priority. Select or Ctrl+Shift+U cancels the active tool.
Construction owns its highlights until it finishes, after which Marine
highlights return.

The full native patch and an incremental upgrade both contain the change.
Patch regressions cover fresh application, previous patch versions, repeated
builds, local sprite offsets, unrelated edits, and atomic rejection of conflicts.
No park layout, native simulation, transport, or scenario gameplay format changed.

## Verification on October 16, 2026

| Command | Result |
| --- | --- |
| `CCACHE_DIR=/tmp/starcoaster-ccache cmake --build build/openrct2 --parallel 2` | Passed; graphical and headless binaries rebuilt. |
| `python3 scripts/apply-openrct2-patches.py` | Passed; current native sources verified. |
| `GOCACHE=/tmp/starcoaster-go-cache scripts/project.sh test` | Passed: Go packages, three C++ tests, 87 Python tests (four skipped), and JavaScript plugin checks. |
| `python3 tests/test_marine_controls_live.py` | Passed after rebuilding the local module: both orders accepted and delivered in order, native frames ordered, Marine reversed within 1,051 ms. |
| `scripts/project.sh record --scenario mt-zergling --duration 25 --marine-screen-probe --no-video` | Passed: all five Marines box-selected at four rotations/zoom levels, elevated projection, no active selection tool, and 221 matching shared snapshots with no mismatches. |
| `python3 tests/test_shared_viewport_live.py` | Passed all 11 checks: native hover cursors, ride/guest windows, overlapping Alt-click, tool priority, selection recovery, and a real right-click order delivered to OpenBW. |

The command regression is at
`run-data/marine-controls-live-1792180300/verification.json`. Its first attempt
used a stale module without the expected frame/order diagnostics; rebuilding
`BridgeAIModule.so` resolved the assertion failures.

The two-client capture is at
`run-data/artifacts/20261016T195223Z-75537e297396/`. Its verification file,
rotation screenshots, and both client logs are retained locally. This was an
input and synchronization check, not a combat playthrough.

The focused graphical artifacts are at
`run-data/shared-viewport-live-1792180977495356429/`, including `ride.png`,
`guest.png`, `overlap.png`, and `verification.json`.

The focused graphical test uses a disposable Frontier session with delayed
waves and disabled assault AI. It adds a guest spawn through synchronized
native actions because Frontier has no guest spawn points. This temporarily
releases ownership of one existing path tile and enables sandbox mode in the
disposable session; the production park is not saved or modified. It compares actual
X11 cursor images, opens the carousel and guest windows with mouse clicks,
checks Alt-click on an overlapping guest, exercises an active tool and the
selection shortcut, selects a Marine again afterward, and sends a move order
with a real right click. It requires Xvfb,
xdotool, scrot, X11/Xfixes, built engines, and locally licensed game data.
Xvfb was extracted under `/tmp/starcoaster-xvfb` for these runs and supplied
through `PATH`; no system package was installed. Screenshots, logs, test
scenario data, and verification JSON remain ignored.

The complete `test-live` suite was not rerun; focused command and graphical
input checks cover this change. Other native park entity types use the same
unchanged native interaction dispatch but were not individually clicked in the
focused test.
