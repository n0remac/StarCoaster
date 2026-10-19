# In-game park switching

The Pi game service runs `scripts/park_session_supervisor.py`. Its private park
library is the directory containing the path in `run-data/pi-park-path`. Only
regular `.park` files directly inside that directory appear in **StarCoaster:
Load Park**. The server accepts park names from that catalog, never client file
paths or browser uploads.

The menu offers **Save and switch**, **Discard changes and switch**, and
**Cancel**. Saving calls the authoritative OpenRCT2 host's `context.saveGame`.
The supervisor archives that save under `run-data/park-supervisor/saved/` and
uses it when the park is selected again. Source files in the library are never
overwritten. The most recently active park is recorded in
`run-data/park-supervisor/active-park.json` for service restarts.

Each load gets a new generation, a private working park copy, scenario
configuration, spawn journal, server data directory, and two fresh OpenBW
participants. Before stopping the current game, the supervisor runs a complete
native synchronization of the candidate park inside a private Linux network
namespace. This catches OpenBW navigation failures that a `.park` inspection or
standalone `.scm` load cannot detect. If preparation fails, the current game
continues. If activation fails, the supervisor attempts to start the previous
park as a fresh session. Unsaved in-memory changes cannot be recovered after
the old session stops.

The private WASM HTTP server stays up while the game host changes. Browser
clients reload at the same origin when a new generation becomes ready; their
IndexedDB game assets remain cached. Native clients reconnect to the same
multiplayer address. OpenRCT2's ordinary **File → Load Game** is local and is
not a shared park switch; use **StarCoaster: Load Park** in multiplayer.

## Verification

With two supported, distinct park files in a private directory, run:

```sh
tests/run_park_switch_live.sh --parks run-data/pi-parks \
  --first ordinary-frontier-park.park --second frontier-outpost-playable.park \
  --output run-data/verification/park-switch-live.json
```

The test starts A, switches to B, then returns to A. It checks fresh process
IDs, generations, journals, enabled construction profile, and the native host
listener. The runner creates its own network namespace so it can run while the
Pi game service remains online. Session and preflight logs stay under the
reported ignored `run-data/park-switch-live-*` directory. Browser gameplay
checks and captures use the private origin and ignored browser profile described
in `docs/wasm-browser.md`.
