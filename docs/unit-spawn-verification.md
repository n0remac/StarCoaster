# Runtime unit spawning verification — v0.3.1

The Frontier Outpost spawn tool now sends a synchronized OpenRCT2 action to the Go bridge. A five-Marine request creates five native OpenBW units in sequence and gives each a canonical actor ID after native creation. The existing actor registry waits for publisher and controller bindings before a new Marine becomes commandable. The same bridge queue and native creation path also serve trusted Zergling scenario waves.

## Live evidence

All live runs below used local licensed RCT2 and StarCraft assets, with generated maps and logs retained only under ignored `run-data/`.

| Run | Result | Evidence |
| --- | --- | --- |
| `tests/test_unit_spawn_live.sh` | Pass | [five Marine action run](../run-data/unit-spawn-live-1791867143/) — started with six Marines, issued five native creations, and both clients displayed eleven unique IDs; native move and attack orders reached the Terran controller. |
| `BRIDGE_SPAWN_RECOVERY=1 BRIDGE_TEST_KILL_RUNTIME_MARINE_FRAME=450 tests/test_unit_spawn_live.sh` | Pass | [recovery run](../run-data/unit-spawn-live-1791869341/) — client B rejoined, the Go bridge restarted while OpenBW stayed active, all five IDs rebound, native death removed `openbw:3001`, and a replacement `openbw:3006` appeared on both clients and accepted a native move order. |
| `BRIDGE_TEST_DISCONNECT_SPAWN_INDEX=2 tests/test_unit_spawn_live.sh` | Pass | [in-flight fault run](../run-data/unit-spawn-live-1791869365/) — the publisher disconnected after issuing index 2. The bridge reported `uncertain`, then native reconciliation recovered `openbw:3003` and finished the batch. The log contains one issue and one `actor.spawn` for each of the five IDs. |
| `tests/test_unit_spawn_zerg_live.sh` | Pass | [Zerg wave run](../run-data/zerg-spawn-live-1791867620/) — five native Zerglings joined the initial twelve, both clients displayed seventeen distinct Zergling IDs, and native movement and attack frames were observed. |

The recovery test sends move and attack orders to the new squad before reconnect, then a stop order to keep the test squad away from the Zerg army while exercising bridge recovery. The native death hook is test-only. The replacement uses a different placement cell because living Marines can occupy the first spawn cell; native occupancy rejection is expected behavior.

## Final gates

| Command | Result | Evidence |
| --- | --- | --- |
| `PATH=/usr/local/go/bin:$PATH go test ./...` | Pass | World and bridge packages passed. An initial bare `go test ./...` invocation failed because `go` is absent from this shell's default `PATH`; the installed Go binary is `/usr/local/go/bin/go`. |
| `node tests/test_world_plugin.js` and `node tests/test_plugin_snapshots.js` | Pass | Synchronized spawn authorization, placement tool, lifecycle, and snapshot tests passed. |
| `ctest --test-dir build/bridge-module --output-on-failure` | Pass | All three C++ tests passed, including spawn placement checks in `world_navigation_test`. |
| `scripts/project.sh build` and `scripts/project.sh test` | Pass | Native module, OpenRCT2, Go, Python, C++, and JavaScript gates completed. |
| `scripts/project.sh test-live` | Pass | [native navigation](../run-data/frontier-native-nav-1791869110/), [two-client world demolition](../run-data/world-live-1791869165/), [two actor cycles](../run-data/actor-lifecycle-1791869198/verification.json), [five Marines](../run-data/unit-spawn-live-1791869292/), and [five Zerglings](../run-data/zerg-spawn-live-1791869301/). |

One earlier full live attempt timed out in `tests/test_world_live.sh` after client A repeatedly rejected a structure attack while both clients joined at once: [failed world run](../run-data/world-live-1791868935/). The test now waits for the server's complete target catalog and joins client A before client B. A focused rerun and the final full gate passed. The final Frontier lifecycle verifier passed both victory cycles; one cycle recorded `attack_command_accepted: false` for its optional attack probe.

## Protocol and failure behavior

`unit.spawn.request` uses a session-unique, stable request ID. Repeated identical requests return the same result; changed parameters and stale sessions are rejected. The bridge journals each per-unit state. Only one native creation awaits identity at a time. An issued command becomes `uncertain` after a disconnect or bridge restart. The same publisher may replay its result or explicitly report `not_received`; only the latter permits a new issue. Native rejection reports a reason and leaves successful units in a partial batch intact.

The Go unit tests cover validation, capacity, idempotence, partial batches, death before controller binding, explicit `not_received` retry, stale sessions, and status query after a client disconnect. The C++ placement test covers map edges, blocked walkability, and occupied space. JavaScript tests cover the synchronized spawn action and client actor lifecycle. The live fault run covers the most dangerous interval: a command issued and a native unit created while publisher transport is lost.

## Limits

- The player tool supports Terran Marines in batches of one to five. Trusted scenario configuration supports Zergling waves through the same queue; players cannot request Zerg ownership.
- The queue admits at most 64 pending units and the bridge defaults to at most 240 live combat actors under the 256-unit snapshot cap. Native placement rejects blocked or occupied cells; the tool does not automatically search for an alternative park location.
- The active park navigation map is static during a spawn. Dynamic construction and production buildings remain separate work.
- The live tests exercise the synchronized OpenRCT2 action with headless clients. The existing graphical artifact pipeline was not used to film a mouse click on the spawn placement tool in these runs.
