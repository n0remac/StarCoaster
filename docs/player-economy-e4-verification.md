# E4 ordinary-park economy verification

Implementation commits: `d5076d0` (deterministic native-valid placement,
finite startup, wave gate and projections) and `8a45a80` (validated startup
cache, private inventory cache and live probes). This report records tests run
before the user stopped automated app testing on 2026-11-07. It does not mark
the normal browser economy loop or E5 complete.

## Implemented behavior

- Stock park preparation inspects actual OpenRCT2 geometry, boundedly chooses
  owned, dry, flat and reachable space at one elevation, and records a fixed
  Command Center, four SCVs, six mineral deposits, a geyser, and two defense
  building spaces. No valid site yields `blocked` with no hidden units, funds or
  automatic waves. The original stock save is not modified.
- Generated ordinary parks use finite native balances (50 minerals, zero gas),
  synchronized native identities and collision masks. The wave clock starts
  after paired resource, Command Center and worker bootstrap; the first delay
  is 7,200 native frames. Authored scenarios retain their prior policy.
- A validated preparation package now includes the OpenRCT2 scenario index
  produced by isolated native preflight. The private browser server caches
  licensed RCT2 file digests qualified by device, inode, size, mtime and ctime;
  changed files are hashed again. Both caches are ignored USB-backed data.

## Results and commands

| Check | Exact command or source | Result |
| --- | --- | --- |
| Offline suite | `TMPDIR=/tmp/economy-e4-tmp GOTMPDIR=$PWD/build/tmp-e4 GOCACHE=$PWD/build/go-cache-e4 GOFLAGS=-p=2 GOMAXPROCS=2 BRIDGE_BUILD_JOBS=2 scripts/project.sh test` | PASS before the final inventory-cache change: Go packages, 3 C++ tests, 223 Python tests (1 skipped), and JavaScript plugin checks. `run-data/economy-e4-offline-final.log`. |
| Cache and inventory regressions | `python3 -m unittest tests.test_single_map_cache tests.test_single_map_cache_reader_races`; `GOCACHE=$PWD/build/go-cache-e4 GOFLAGS=-p=2 GOMAXPROCS=2 /usr/local/go/bin/go test ./cmd/wasm-server -count=1` | PASS after final cache changes: 15 Python tests and wasm-server Go tests. The new cache tests first failed before implementation. |
| Stock native mining | `python3 tests/test_player_economy_e4_native_route_live.py '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6' --runtime run-data/economy-e4-native-route-1` | PASS: native mineral deposit 1500→1492 at frame 1080; balance 50 at frame 624 and 58 at frame 1128 after delivery. Base tile `(49,41)`, source SHA-256 `84aeb880c2d5e2610d6a760eb13c087b3eefcd0683fc71aabe1b4e51cc585f44` unchanged. |
| Impossible stock layouts | `python3 tests/test_player_economy_e4_blocked_native_live.py '/home/pi/games/rct2/Scenarios/Roaring Twenties - Prison Island.SC6' --runtime run-data/economy-e4-prison-blocked`; same command with `Antarctic - Ecological Salvage.SC6` and `run-data/economy-e4-antarctic-blocked` | PASS: both report `no_native_valid_economy_site`; no economy entities, funds or automatic wave deadline. |
| Repeated sessions and switch | `python3 tests/test_park_supervisor_cache_native_live.py` with ignored runtime `run-data/economy-e4-supervisor-2` | PASS on earlier E4 source: two Bumbly generations, then Victoria Falls with a new generation/session and no prior actor IDs or wave count. First and second cache-hit selection 10.968 and 11.244 seconds. Rerun on final source was stopped at user request. |
| Final cache build | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft BRIDGE_FRAME_MS=15 python3 scripts/map-cache.py build '/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6'` | PASS: validated key `ff78cac335fcd1a47ea43872065c97bc66247ea07a37f7e31d105bea20243e84`, preflight scenario index included. |
| Browser New Game | `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft python3 tests/test_player_economy_e4_browser_handoff_live.py --runtime run-data/economy-e4-browser-handoff-16 --profile run-data/economy-e4-browser-handoff-8/profile --wasm-port 48965` | PARTIAL/FAIL: normal browser selection reached ready generation `f5ac870208ac4796979ea612f7bc0452`; graphical client reported 4 SCVs, 6 minerals and 1 geyser. Scripted train returned `Production building is unavailable`; early gather returned `Resource target has changed`; screenshot timed out after 120 seconds. The probe did not prove browser training or delivery. Its host later logged one accepted browser gather request, native depletion and rising balance; that does not repair the failed graphical gate. |

The final browser cache hit took 1.154 seconds; materialization took 7.321 ms.
Native session startup took 137.891 seconds under Chromium load despite reuse
of the scenario index, versus roughly 8 seconds in the earlier headless
supervisor check. The first private browser server start also exceeded the old
90-second probe limit while hashing 2,465 licensed files; the inventory cache
was added after that failure. Earlier normal browser runs failed during cache
lookup (400.215 seconds) or native startup (150.270 seconds); the final cache
fixes addressed those stalls but have no complete browser gameplay pass yet.

All captures, profiles, logs, packaged native maps and licensed files remain
under ignored `build/` or `run-data/`. The browser failure is in
`run-data/economy-e4-browser-handoff-16/browser.log`; the host record is in
`run-data/economy-e4-browser-handoff-16/supervisor/sessions/f5ac870208ac4796979ea612f7bc0452/session.log`.

## Open exit checks

- Verify the normal browser controls can train an SCV, order mineral gathering,
  deliver to the Command Center and show the same balance as native. The
  scripted browser probe issued commands before its local building/resource
  catalogs were fully usable and never completed this gate; a real UI attempt
  must establish whether this is probe timing or a player-facing defect.
- Run the dense 256 × 256 stock live case and measure time to a native Depot,
  Barracks and first trained defender before the delayed wave. These checks
  were stopped at the user's request. E5 still owns the complete native and
  browser resource, construction, gas, combat and recovery loop.
- The E3 ambiguous-creation reservation and worker-death/concurrent-edit fault
  cases remain outstanding. A DEV manual release is an evaluation build until
  these gates and the browser gameplay path pass.
