# Passthrough RTS Bridge — OpenBW × OpenRCT2

**Status:** Implementation specification / feasibility proof of concept — **Revision 2: BWAPI integration**  
**Goal:** One genuine OpenBW-simulated Zergling moves through an OpenRCT2 park and appears in the same position to two connected OpenRCT2 players.  
**Principle:** One simulation owns each gameplay fact; clients render a synchronized projection of that state. **Use the OpenBW-specific BWAPI fork as the supported RTS control API, not direct OpenBW internal structs.**  
**Asset policy:** The bridge ships no Blizzard or RollerCoaster Tycoon proprietary graphics. Use an independently drawn, appropriately licensed **alien-creature stand-in** for the first Zergling visual; do not extract or redistribute StarCraft sprites. OpenRCT2's stock graphics still depend on proprietary RCT2 assets unless an adequate open replacement is used.

## 1. Product vision

Build a reusable bridge connecting independently running 2D/isometric game engines into a shared world. The initial crossover combines OpenRCT2's park construction, terrain, rides, guests, and economics with OpenBW's StarCraft unit simulation. Later, the same hub can connect engines such as OpenTTD, Factorio, or open Zelda-like engines, supporting live passthrough multiplayer and asynchronous cross-game events.

A player should be able to keep playing OpenRCT2 normally while a military unit from the OpenBW simulation traverses the same world. The system should not embed one game's completed video framebuffer over another's scene.

**Prototype outcome:** The OpenBW/BWAPI launcher starts one headless simulation; a custom BWAPI `AIModule` creates and commands a genuine Zergling through `BWAPI::Game` / `BWAPI::Unit` APIs. OpenBW simulates movement and the AI module publishes snapshots; both OpenRCT2 clients render them with openly licensed substitute art. With both clients connected to the same server, their displayed paths agree, including after camera rotation and joining late.

## 2. Architecture and authority

```text
                     One host machine for POC (can split later)
  +--------------------------------------+      localhost TCP      +---------------------------+
  | OpenBW simulation via BWAPILauncher  |   -- state snapshots -> | OpenRCT2 multiplayer host |
  | - headless (no UI needed)            |                        | - remote JavaScript plugin|
  | - true StarCraft simulation          |                        | - validates snapshots     |
  | - custom BridgeAIModule (.so)        |                        | - server-approved custom  |
  |   * creates one Zergling via BWAPI   |                        |   synchronized game action|
  |   * issues Unit::move()              |                        +-------------+-------------+
  |   * reads Unit::getPosition() etc.   |                                      |
  |   * publishes versioned snapshots   |                              synchronized actions
  +--------------------------------------+                                      |
                                                               +---------------+---------------+
                                                               |                               |
                                                      +--------v----------+           +--------v----------+
                                                      | OpenRCT2 client A |           | OpenRCT2 client B |
                                                      | modified C++ build|           | modified C++ build|
                                                      | remote JS plugin  |           | remote JS plugin  |
                                                      | render-only actor |           | render-only actor |
                                                      +-------------------+           +-------------------+
```

- **OpenBW owns** RTS unit identity, movement, commands, and eventually combat. **BWAPI is the control/observation API**; the OpenBW-specific BWAPI fork launches the simulator with `BWAPILauncher` and calls our `AIModule` once per frame. The POC runs *one* OpenBW simulation; its 1v1 networking mode is unnecessary.
- **OpenRCT2 server owns** park gameplay state and scheduling/distribution of synchronized bridge actions. It does **not** simulate the Zergling's RTS movement.
- **OpenRCT2 graphical clients own presentation only**: select sprites, transform camera coordinates, sort into the world paint pipeline, invalidate old/new display regions, and optionally visually interpolate.
- **Bridge protocol stays engine-neutral**: IDs, world position, heading, motion state, tick/sequence, and session epoch. BWAPI-native values are normalized at the RTS adapter boundary; OpenRCT2 world coordinates are computed at the display adapter boundary.
- **Only the OpenRCT2 server connects to the AI module's local bridge publisher.** No per-player BWAPI/OpenBW instances or connections are needed. For the POC, place both servers on one host because OpenRCT2's scripting socket API is loopback-only.

**Deployment distinction:** A server-distributed *remote JavaScript plugin* is loaded by clients, but it **cannot deliver C++ binaries or art**. Each graphical player must install the matching OpenRCT2 fork and openly licensed creature asset pack. Fail clearly on incompatible native/asset/protocol versions.

**OpenBW/BWAPI source separation:** `OpenBW/openbw` is the simulation source; [`OpenBW/bwapi`](https://github.com/OpenBW/bwapi/tree/develop-openbw) is a modified BWAPI 4.2.0 fork integrating OpenBW, with its own launcher and API compatibility layer. Do **not** confuse it with the upstream [`bwapi/bwapi`](https://github.com/bwapi/bwapi) repo targeting original StarCraft.

## 3. Scope

### In scope

- Build/test on Linux first, with a headless OpenRCT2 host and two OpenRCT2 graphical clients.
- Build `OpenBW/bwapi` together with `OpenBW/openbw`, run `BWAPILauncher` with rendering disabled, and drive one genuine `Zerg_Zergling` using a custom BWAPI `AIModule`.
- Provide a simple flat test area mapped into an OpenRCT2 park.
- Display one original Zergling-like creature with walking/idle states and four directions (eight if artwork is already available).
- Render it in the normal OpenRCT2 world paint pipeline so it can be in front of/behind scenery based on its position.
- Broadcast its authoritative movement to both players with OpenRCT2's synchronized action mechanism.
- Provide startup, smoke tests, logging, version checks, and repeatable acceptance tests.

### Explicitly out of scope

- Opponent AI, attacks, damage, buildings, production, economy, full dynamic park-to-StarCraft terrain translation, persistent RTS saves, controlling the RTS from player input, cross-game spectators, and cross-engine true multiplayer PvP. A tiny waypoint script inside the AI module is permitted; a general military AI is not required.
- Redistributing StarCraft graphics, MPQs, or data files, or relying on OpenBW's undocumented licensing being safe for redistribution.
- Replacing OpenRCT2's entire proprietary RCT2 art set as part of this POC.

## 4. Feasibility gate: OpenBW **through BWAPI**

**Complete this gate before committing to the renderer fork.** The OpenBW/BWAPI fork makes the RTS integration substantially simpler: it provides a C++ API for creating and ordering units, reading their state, handling events, and running headlessly. Do not write a new OpenBW game loop or manipulate internal `unit_t`/`sprite_t` pointers for POC v1.

### 4.1 Repositories and build

Pin and record compatible git commit SHAs for:

- [`OpenBW/openbw`](https://github.com/OpenBW/openbw) — RTS simulation.
- [`OpenBW/bwapi`, branch `develop-openbw`](https://github.com/OpenBW/bwapi/tree/develop-openbw) — BWAPI 4.2.0 integration, build, `BWAPILauncher`, and AI module examples.

The fork's README documents a CMake build that compiles OpenBW as part of BWAPI. Example Linux development commands (assuming sibling clones):

```bash
git clone https://github.com/OpenBW/openbw.git
git clone --branch develop-openbw https://github.com/OpenBW/bwapi.git
cmake -S bwapi -B bwapi/build -DCMAKE_BUILD_TYPE=Release \
  -DOPENBW_DIR="$(pwd)/openbw" -DOPENBW_ENABLE_UI=0
cmake --build bwapi/build -j
```

This checkout keeps all three upstream repositories under `upstream/`; see the [pinned revisions](../../dependencies.lock.json) and [bootstrap commands](../bootstrap.md) used on the target Pi.

**Note:** The fork is a development branch with potential breaking changes. The commands are documented configuration guidance, **not yet validated as successful on the target machine**. Start by building the supplied `ExampleAIModule`; avoid touching private implementation until the public API proves inadequate. OpenBW can run without SDL when the UI is disabled.

### 4.2 Run prerequisites and licensing gate

The README identifies three required, **user-supplied** StarCraft data archives in the launch working directory (from an appropriate original installation). The pinned OpenBW loader opens the case-sensitive names `StarDat.mpq`, `BrooDat.mpq`, and `Patch_rt.mpq`; the BWAPI README spells the first two `Stardat.mpq` and `Broodat.mpq`. The [launcher script](../../scripts/run-bwapi.sh) accepts either spelling and stages the source-required names. Configure the AI plugin and map in `bwapi-data/bwapi.ini`, or use supported `BWAPI_CONFIG_*` environment variables. The launcher is `BWAPILauncher`.

Example concept for launching from a directory containing the required MPQs and BWAPI configuration:

```bash
OPENBW_ENABLE_UI=0 \
BWAPI_CONFIG_AI__AI=/absolute/path/to/BridgeAIModule.so \
BWAPI_CONFIG_AUTO_MENU__RACE=Zerg \
/absolute/path/to/bwapi/build/bin/BWAPILauncher
```

Set the map via the BWAPI configuration and use a valid flat map with legal positions. Verify the actual built module name and location. The source README's environment variables and launcher options may require adjustment for the pinned revision.

**Licensing distinction:** The BWAPI fork declares **LGPL-3.0**, but that **does not establish a license for the separate OpenBW core**. Audit the OpenBW license before binary/source redistribution; do not bundle MPQs or proprietary textures/audio. The OpenRCT2 base installation still depends on original RCT2 game assets unless independently replaced. If these dependencies are unacceptable, keep the protocol and OpenRCT2 work, but evaluate OpenRA/OpenHV as an alternate simulation provider.

### 4.3 Implement `BridgeAIModule`

Create a C++ shared module based on [`bwapi/ExampleAIModule`](https://github.com/OpenBW/bwapi/tree/develop-openbw/bwapi/ExampleAIModule); it should link to `BWAPILIB` and include the appropriate module entry-point/factory (see the example's `Dll.cpp`).

Use the **public BWAPI APIs**:

- `AIModule::onStart()` — validate game state, create one real `UnitTypes::Zerg_Zergling` using the fork's `Broodwar->createUnit(Broodwar->self(), type, position)`, store its unit ID, and issue `unit->move(target)`.
- `AIModule::onFrame()` — query `unit->exists()`, `unit->getPosition()`, `unit->getAngle()` (radians, zero = east), `unit->isMoving()`, and `Broodwar->getFrameCount()`; log and publish snapshots at a decimated cadence. If it reaches a waypoint, issue the next legal movement order.
- `AIModule::onUnitDestroy()` / `onEnd()` — publish removal/stop state when appropriate.
- Always check `Unit::move()` and `createUnit()` results and log `Broodwar->getLastError()` on failure. Do not directly set positions: that would invalidate the simulation proof.

Minimal **illustrative** module logic; a complete plugin additionally needs the example's factory and transport implementation:

```cpp
#include <BWAPI.h>

class BridgeAIModule : public BWAPI::AIModule {
    BWAPI::Unit zergling = nullptr;
public:
    void onStart() override {
        auto* game = BWAPI::Broodwar.operator->();
        if (!game->self()) return;
        zergling = game->createUnit(game->self(),
                                    BWAPI::UnitTypes::Zerg_Zergling,
                                    BWAPI::Position(320, 480));
        if (zergling && !zergling->move(BWAPI::Position(640, 480))) {
            // Log game->getLastError(); fail the movement gate.
        }
    }

    void onFrame() override {
        if (!zergling || !zergling->exists()) return;
        if (BWAPI::Broodwar->getFrameCount() % 3 != 0) return;
        const auto p = zergling->getPosition();
        const double headingRadians = zergling->getAngle();
        // Publish {game session, unit ID, tick, p.x, p.y,
        //          headingRadians, isMoving} over localhost; do not draw.
    }
};
```

### 4.4 Gate acceptance

1. The launcher and custom AI module run with **no graphical window**.
2. `createUnit` successfully returns a real Zergling on a valid test map.
3. `Unit::move` is accepted and the reported position changes as the **OpenBW simulation advances**, with waypoint arrival observable.
4. The module publishes changing unit states to a local test receiver. No OpenRCT2 code is required yet.
5. The team records exact build revisions, data dependencies, and any failing/unsupported API calls.

**Stop/go:** If BWAPI's documented API cannot reliably drive the unit in this fork, diagnose and patch the adapter in isolation. If proprietary runtime data is a blocker to the product's distribution goals, do not quietly replace OpenBW with fake movement; retain the transport interface and explicitly gate or swap the RTS backend. A mock publisher may help downstream renderer testing, but **cannot fulfill this gate**.

References: [`README.md`](https://github.com/OpenBW/bwapi/blob/develop-openbw/README.md), [`Game.h`](https://github.com/OpenBW/bwapi/blob/develop-openbw/bwapi/include/BWAPI/Game.h), [`Unit.h`](https://github.com/OpenBW/bwapi/blob/develop-openbw/bwapi/include/BWAPI/Unit.h), [`AIModule.h`](https://github.com/OpenBW/bwapi/blob/develop-openbw/bwapi/include/BWAPI/AIModule.h), [`GameImpl.cpp`](https://github.com/OpenBW/bwapi/blob/develop-openbw/bwapi/BWAPI/Source/BWAPI/GameImpl.cpp), [`ExampleAIModule.cpp`](https://github.com/OpenBW/bwapi/blob/develop-openbw/bwapi/ExampleAIModule/Source/ExampleAIModule.cpp). Consult OpenBW internals only if the API proves insufficient; do not use OpenBW's UI pixels.

## 5. Wire protocol and timing

Use newline-delimited JSON over **localhost TCP** for the POC; isolate serialization and transport behind an interface so protobuf/gRPC can be introduced later without altering the renderer. No inbound public bridge port.

An example full snapshot (proposed protocol, not an existing engine API):

```json
{"v":1,"kind":"units.snapshot","session":"demo-001","map_id":"demo-flat","seq":42,"bw_tick":173,"units":[{"id":"openbw:1","kind":"alien_scout","x":320.0,"y":480.0,"facing":64,"motion":"walk","alive":true}]}
```

- `session`: new unique runtime/epoch ID on every BWAPI game restart; reset sequence tracking and remove stale actors when this changes. Include a map/park identifier in configuration to prevent applying a snapshot to the wrong world.
- `id`: stable unit ID derived from the BWAPI unit ID and scoped by `session` (e.g., `openbw:1`); never transmit a raw pointer as a network ID.
- `seq`: strictly increasing snapshot sequence for duplicate/out-of-order rejection.
- `bw_tick`: simulation frame; use for diagnostics and interpolation timing, **not** as an OpenRCT2 tick number.
- `x,y`: document whether these are OpenBW-native coordinates or neutral world units. Convert in one explicit transform; do not conflate StarCraft screen pixels with OpenRCT2 projected screen coordinates.
- `facing`: **canonical direction unit (0–255 full circle)**; derive from BWAPI `Unit::getAngle()` **in radians (0=east)**, normalize/wrap, and verify handedness/y-axis direction before quantization to sprite directions. Do not assume the BWAPI angle is already a byte or a frame index.
- `motion`: semantic state (`idle`, `walk`, later `attack`) inferred initially from BWAPI `Unit::isMoving()` and velocity/order if needed, **not** proprietary GRP frame indices.
- `alive`: allows the render-side entity to disappear cleanly.

Run the OpenBW simulation with its normal BWAPI frame callbacks and publish **full snapshots at 5–10 Hz**, configurable; render at OpenRCT2's own frame rate using optional interpolation. With one unit, full snapshots simplify reconnection, late joins, and state recovery. Avoid sending a synchronized action for every OpenBW tick unless profiling demonstrates it is safe.

Use a configurable map transform (`origin_x`, `origin_y`, `scale_x`, `scale_y`, `axis_flip`, `rotation`) and calibrate it against known points. Let **OpenRCT2 terrain determine visual Z** for this flat-map POC. Expansion into real elevation/pathfinding is a separate phase.

## 6. OpenRCT2 server integration

Create a **remote plugin** (`rts-bridge.js`) that runs on the multiplayer server and is delivered by OpenRCT2 to joining clients.

- On `network.mode === "server"`, connect to the **BWAPI BridgeAIModule's local publisher** using OpenRCT2's localhost TCP socket API (or reverse the socket direction if the chosen implementation demands it). Do not connect the OpenRCT2 clients directly to BWAPI.
- Validate message version, **session epoch**, schema, unit count, coordinates, map bounds, sequence progression, and configured source identity. Only accept the configured local runner.
- Register a custom game action such as `rtsbridge.applySnapshot` using `context.registerAction(name, query, execute)`.
- On each accepted input snapshot, invoke `context.executeAction(...)` **on the server**, not direct client-side state mutation.
- The custom action's **execute** function updates only the bridge-owned presentation registry on every participant at the same OpenRCT2 game tick. It must not write unsynchronized OpenRCT2 simulation state.
- Keep query/execute deterministic for identical arguments; do not make network requests, read wall-clock time, or generate randomness in action execution.
- Include logging for dropped/invalid data, applied sequence numbers, active clients, and missing renderer API.

The C++ renderer registry needs a minimal script-facing function in our modified OpenRCT2 build (e.g., `rtsBridge.applySnapshot(snapshot)`), registered with the script engine and called **only from the custom action execute handler**. This is a **proposed new binding**, not a built-in OpenRCT2 API. On the headless host it must update a lightweight state registry or safely do nothing for graphical presentation; on each graphical client it updates its local render snapshot. Native ABI and plugin protocol versions must match.

OpenRCT2's documentation explicitly states that remote scripts can register multiplayer-safe custom game actions, and that plugin TCP sockets are restricted to localhost. See [`scripting.md`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/distribution/scripting/scripting.md) and [`openrct2.d.ts`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/distribution/scripting/openrct2.d.ts).

## 7. Native OpenRCT2 render adapter

Do **not** register a new ordinary `EntityType` for POC v1. Maintain a separate, render-only map of `ExternalActor {id, x, y, z, facing, motion, image_id, last_seq}` on each client.

Implement these pieces:

1. **Asset pack:** Import transparent PNG walking/idle animation frames through OpenRCT2's supported sprite/image loading machinery. Bundle only original or properly licensed pixel art. Maintain a fixed manifest mapping animation/direction/frame to image IDs. Verify correct offsets and indexed palette conversion.
2. **Spatial lookup:** Index bridge actors by OpenRCT2 map tile. Avoid iterating all external actors for every map tile.
3. **Paint hook:** Call `PaintBridgeActors(session, tile)` alongside `EntityPaintSetup(session, tile)` in `PaintSessionGenerateRotate`, or extend `EntityPaintSetup` to process that tile's external actors. Use `PaintAddImageAsParent` to enter the native world paint/sort pipeline.
4. **Position and bounds:** Set `session.SpritePosition` in OpenRCT2 world X/Y; select sprite based on facing plus `session.CurrentRotation`; use world Z and a correct `BoundBoxXYZ`. Set interaction type to `none` initially; avoid dangling `EntityBase*` references.
5. **Redraw:** Invalidate the old and new projected screen region when a snapshot changes the actor. Handle zoom, clipping, camera rotations, actor removal, and terrain height. Match other actor zoom behavior deliberately.
6. **Thread safety:** Publish immutable/copy-on-write snapshots or otherwise synchronize access because painting can be parallelized. Do not mutate the registry while paint worker threads iterate it.
7. **Interpolation:** Optional and strictly presentation-only. Never feed interpolated client positions back into OpenBW or OpenRCT2 authoritative simulation.

Read the current code: [`Paint.Entity.cpp`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/src/openrct2/paint/Paint.Entity.cpp), [`Paint.cpp`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/src/openrct2/paint/Paint.cpp), [`Paint.Duck.cpp`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/src/openrct2/paint/entity/Paint.Duck.cpp), [`ImageTable.cpp`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/src/openrct2/object/ImageTable.cpp), [`ImageImporter.cpp`](https://github.com/OpenRCT2/OpenRCT2/blob/develop/src/openrct2/drawing/ImageImporter.cpp).

**Do not draw on top of the final framebuffer.** Correct scene occlusion is a core acceptance criterion.

## 8. Development order / milestones

### M0 — OpenBW/BWAPI integration and environment

- Pin `OpenBW/openbw` and `OpenBW/bwapi` `develop-openbw` SHAs. Compile BWAPI via CMake, which builds its OpenBW backend; build and load a custom `BridgeAIModule` by adapting `ExampleAIModule`.
- Configure `BWAPILauncher` and a flat map, with GUI disabled. Record the required user-supplied MPQ data files and licensing/distribution constraints.
- In `onStart`, create a genuine Zergling via `Broodwar->createUnit` and issue `Unit::move`. In `onFrame`, publish actual `getPosition`, `getAngle`, `isMoving`, `getID`, and frame count to a localhost test subscriber.
- Build stock OpenRCT2 client and headless host; verify two-client vanilla multiplayer.

**Exit:** The BWAPI module is loaded by `BWAPILauncher`, the real Zergling moves and publishes changing coordinates **with no rendered StarCraft window**, and two OpenRCT2 clients can join the park.

### M1 — Rendering in one OpenRCT2 client

- Implement asset loading and `PaintBridgeActors` using a hardcoded actor.
- Validate in-world position, animation, rotation, occlusion and redraw.

**Exit:** A stand-in creature walks correctly *in the world* under scripted local coordinates, without any OpenBW connection.

### M2 — Server-to-two-client synchronization

- Add server remote plugin, loopback socket receiver, schema checks, new script/native binding, and a synchronized custom action.
- First use a deterministic fake publisher to isolate the network system.
- Verify both clients show the same position and respond to camera rotation independently.

**Exit:** Both clients consistently reproduce one externally controlled actor; no duplicate or disappearing actor after normal snapshot updates.

### M3 — Real OpenBW-driven POC

- Replace mock publisher with the **BWAPI `BridgeAIModule`** unit-state snapshots.
- Use `BWAPI::Game::createUnit`, `BWAPI::Unit::move`, and `AIModule::onFrame` to spawn, order movement, and transmit the actual simulated unit position/state.
- Demonstrate 60+ seconds of continuous OpenBW-authoritative motion with both OpenRCT2 clients connected.

**Exit:** Killing `BWAPILauncher` stops/fades the actor according to the documented failure policy; restarting it with a new `session` epoch cleanly respawns/synchronizes the unit without duplicates.

### M4 — Hardening/demo

- Late join: third/restarted client gets the next full snapshot and sees the current actor within 2 seconds.
- Connection loss/recovery, invalid/out-of-range packets, fast camera rotations, zoom changes, park pause/resume, and map reload tested.
- Include run scripts, debug overlay/logs and a screen recording or reproducible demo checklist.

**Exit:** Another developer can run it from the README without editing source or manually copying hidden state.

## 9. Acceptance criteria

1. **OpenBW running through `BWAPILauncher` and a custom BWAPI `AIModule`**—not a mock—creates/updates the Zergling and is solely responsible for its movement; logs prove `createUnit` / `move` / `getPosition` were used.
2. One headless `BWAPILauncher`/OpenBW instance and one OpenRCT2 multiplayer server host two graphical OpenRCT2 clients; neither client runs OpenBW or BWAPI.
3. Both clients show **the same actor identity and authoritative path**, while each can pan or rotate independently.
4. Actor appears correctly in front of and behind park scenery using OpenRCT2's world sorting, not a screen overlay.
5. Moving actor animates and clears its old drawing position; actor is removed on despawn.
6. Late joining/reconnection does not create duplicates; stale/invalid snapshots are rejected, and **a new BWAPI session epoch** removes state from the prior run.
7. No proprietary StarCraft art or binary assets are committed or redistributed; all included creature artwork carries verifiable license/attribution.
8. Build/run steps for `OpenBW/bwapi` and the custom AI module, pinned revisions, required MPQs, and OpenBW/BWAPI licensing constraints are documented, including cases where an open-data solution is not yet possible.
9. Logs demonstrate simulation tick, message sequence, OpenRCT2 application tick, and actor coordinates for troubleshooting.

## 10. Risks and explicit decisions

| Risk | Mitigation |
| --- | --- |
| OpenBW still needs original StarCraft MPQs and its core license is unclear | BWAPI does not eliminate dependencies; verify required archives, avoid redistribution, retain alternate RTS adapters |
| OpenBW/BWAPI fork is old/development-only; API or build may fail | Pin both repositories to tested revisions, adapt `ExampleAIModule`, test launcher headlessly before touching OpenRCT2 |
| BWAPI angles/coordinates are not OpenRCT2 direction/image formats | Normalize radians to canonical byte facing and convert BWAPI world pixels using an explicit transform |
| OpenRCT2's ordinary base graphics still require RCT2 assets | Ship no proprietary assets; document requirement; evaluate OpenGraphics separately |
| OpenRCT2 script plugins cannot render arbitrary actors by themselves | Minimal C++ client/server fork plus new script binding |
| Native fork/version mismatch between clients | Protocol/asset/build version handshake; clear error before joining demo |
| Render snapshot changes during parallel paint jobs | Immutable state snapshots or guarded read transactions |
| Multiplayer desynchronization | All shared updates via server-approved custom actions; non-authoritative rendering registry only |
| High-frequency game-action traffic | Batch/full snapshots at 5–10 Hz, profiling and interpolation; do not use 24+ synchronized actions/s by default |
| Late join loses transient external state | Repeat complete snapshots with `session` epoch; bind to park IDs; reset state on new park, reconnect, and `BWAPILauncher` restart |
| StarCraft/OpenRCT2 grid and art perspective mismatch | Explicit tunable world transform and directional sprite testing |

## 11. Repository layout and handoff

Suggested project layout (can be separate forks/repos as appropriate):

```text
passthrough-rts/
  docs/architecture.md
  docs/protocol.md
  docs/licensing.md
  bridge-protocol/           # schemas and fixture messages
  openbw-bwapi-module/       # custom BWAPI AIModule, Dll factory, publisher; no vendored OpenBW
  openrct2-plugin/          # server-distributed remote JS plugin
  openrct2-patches/         # native renderer + script binding patches
  assets/alien-scout/       # original/openly licensed art + credits
  tests/                    # protocol, snapshot, multi-client smoke tests
  scripts/                  # local launch/demo helpers
  README.md
```

Required deliverables: working source/patches, version-pinned dependencies, art source/license, executable smoke tests, `start-demo` instructions, screenshots/video instructions, known limitations, and a small follow-on plan for collision/pathing/park-to-RTS mapping.

**Future extension seam:** Define `SimulationAdapter`, `WorldAdapter`, `EntitySnapshot`, `WorldMutation`, and `ActionResult` interfaces. The OpenBW adapter calls **BWAPI**, not OpenBW internal functions; other RTS backends can later implement the same bridge protocol. Avoid a premature generalized hub, database, inter-game economy, or protobuf deployment requirement.

**Definition of done:** Start headless `BWAPILauncher` with the custom `BridgeAIModule`, the OpenRCT2 headless server, and two modified clients. In one park, both users can observe the same independently illustrated Zergling-like creature walking a path because OpenBW issued and simulated its movements. The visible creature belongs to OpenRCT2's spatial drawing scene rather than a pasted-on video layer.

## 12. Revision history

- **Rev 2 (2026-10-09):** Make [`OpenBW/bwapi`](https://github.com/OpenBW/bwapi/tree/develop-openbw) the primary simulation integration. Replace custom OpenBW runner with `BWAPILauncher` and a shared BWAPI `AIModule`; specify `Game::createUnit`, `Unit::move`, `Unit::getPosition`, `Unit::getAngle` (radians), `AIModule::onFrame`, CMake, headless configuration, and the three required user-supplied MPQs. Add session epochs and separate BWAPI LGPL-3.0 from OpenBW core licensing.
- **Rev 1:** Original engine-agnostic bridge, OpenRCT2 render hook, and two-client multiplayer POC plan.
