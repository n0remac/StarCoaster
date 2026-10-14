> Historical verification report. Commands below record a prior baseline; use the [current workflow](../../README.md).

# Shared actor foundation verification (v0.3)

Baseline `999c910`; phases 0–2 are `6a53c29`, `0b14f8a`, and `4298dbe`. Phase 3 is `06db106`. Phase 4 adds the repeatable two-cycle test and this report. All game data, logs, screenshots, and generated maps remain under ignored `run-data/`.

## Gates run

| Command | Result |
| --- | --- |
| `/usr/local/go/bin/go test ./...` | Passed |
| `node tests/test_world_plugin.js` | Passed; includes runtime selection, squad order, removal, and catalog boundaries |
| `node tests/the former v1 snapshot test` | Passed |
| `ctest --test-dir build/bridge-module --output-on-failure` | Passed, 3/3 |
| `scripts/project.sh test` | Passed: Go, C++, 46 Python, and JavaScript tests |
| `RCT2_DATA_DIR=/home/pi/games/rct2 STARCRAFT_DATA_DIR=/home/pi/games/starcraft scripts/project.sh test-live` | Passed: navigation, generic two-client target removal, Frontier lifecycle, and two actor cycles |

The live actor report is [run-data/actor-lifecycle-1791863730/verification.json](../../run-data/actor-lifecycle-1791863730/verification.json), with cycle logs in [cycle 1](../../run-data/actor-live-1791863730/) and [cycle 2](../../run-data/actor-live-1791863776/). The sessions were distinct (`84a413ab…` and `63b4125e…`). Each cycle began with six Marines, spawned one native `openbw:3001`, and found seven unique Marine IDs in both clients. Publisher and controller creation frames matched at frame 303; both client render logs agreed on shared runtime snapshots. The new Marine passed native hit testing, movement, and attack commands. Client B reconnected before the Go bridge was restarted; the living ID remained unique and commandable afterward. Native combat killed it around frame 1060, before the fixture's frame-1800 fallback. Both clients returned to six Marines, and a later command to `openbw:3001` was rejected.

The other full-gate evidence is [native navigation](../../run-data/frontier-native-nav-1791863645/), [generic two-client removal](../../run-data/world-live-1791863700/), and [Frontier lifecycle](../../run-data/frontier-lifecycle/verification.json). Frontier lifecycle passed both cycles with accepted attack commands and six reconciled starting Marines.

A 20-second [graphical capture](../../run-data/artifacts/20261013T035710Z-b58ca24f431d/verification.json) on the same code passed as a capture-only check. Both graphical clients applied 88 snapshots containing `openbw:3001`; 138 shared snapshot sequences matched with no mismatch. The [client A](../../run-data/artifacts/20261013T035710Z-b58ca24f431d/client-a-final.png) and [client B](../../run-data/artifacts/20261013T035710Z-b58ca24f431d/client-b-final.png) screenshots remain local because they contain user-supplied RCT2 graphics.

## Limits

The graphical capture did not exercise orders, death, or reconnect; the native two-cycle test covers those. The fixture uses one synchronized native Marine spawn per session and a frame-1800 native kill fallback, although both recorded deaths happened earlier through combat. A reconnect precisely during the few-frame spawn/bind exchange is timing-dependent and was not forced; JavaScript tests cover snapshot-before-binding ordering and the live test covers reconnect with a living actor. Dynamic wall placement and removal remain a separate milestone.

## Resume record

Before this verification commit, HEAD was `06db106`. Phases 0–3 were committed separately; Phase 4 adds `tests/test_actor_lifecycle_live.sh`, the actor probes, `scripts/project.sh test-live` integration, and updated bridge, protocol, and agent guidance. All named regression gates above were run and passed; no required gate was skipped. The next phase is the separate live-world-updates milestone, beginning with reliable staged `entity.upsert` and `entity.remove` handling. Keep native engine patches isolated if that work requires them.
