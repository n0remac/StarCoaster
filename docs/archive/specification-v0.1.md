# RTS Bridge

**Technical specification:** v0.1  
**Status:** Proposed  
**Initial host:** Minecraft Java Edition  
**Future host:** Skyrim Special Edition  
**RTS engine:** Recoil Engine  
**Communication:** gRPC and Protocol Buffers  
**Original development environment:** Linux, primarily Manjaro

This document records the project specification supplied for planning. It describes the intended architecture and acceptance criteria; technical assumptions remain subject to Phase 0 validation.

## 1. Project overview

RTS Bridge is a reusable framework that integrates a real-time strategy simulation into an existing RPG or sandbox game. The host game renders the world and handles player controls, physical interactions, and nearby combat. An independent RTS engine manages armies, military tactics, formations, pathfinding, and battles beyond the player's immediate surroundings.

Players experience one simulated world in two ways:

- **RPG mode:** Explore normally, fight alongside armies, and influence strategic events through direct action.
- **RTS mode:** View and command armies, issue military orders, and manage battles strategically.

The system must support interchangeable host adapters. Minecraft is the first development platform. Skyrim should later reuse the core simulation and communication protocol.

## 2. Core architecture

### A. Recoil RTS engine

Recoil independently maintains units, squads, armies, factions, navigation, formations, tactics, distant combat, health, status, and military objectives. It runs headlessly. Implement military behavior with LuaRules where practical and minimize native C++ extensions.

### B. RTS Bridge coordinator

A standalone service manages sessions and connections; stable cross-engine identities; coordinates and unit mappings; movement, combat, and command routing; simulation timing; activation and deactivation; recovery; diagnostics; and synchronization metrics. Its implementation language is unspecified. Protobuf is the source of truth for cross-process interfaces.

### C. RPG host adapters

**Minecraft:** A Java Fabric adapter runs on the logical server, including integrated single-player servers. It reads terrain, blocks, entities, and player state; creates visible soldiers; reports combat and world changes; and supports player interaction with RTS entities.

**Skyrim, later:** A C++ SKSE plugin performs equivalent work with Skyrim worlds and actors, using the same Protobuf protocol and coordinator. SkyCraft may be studied for native integration ideas.

Host-specific objects must never appear in the shared protocol.

### D. Military AI

Modular AI runs primarily in Recoil. Initial behaviors are attack, defense, squad organization, advance, retreat, threat evaluation, reinforcement requests, and reactions to casualties or battlefield changes. Study 0 A.D.'s Petra AI attack, defense, and army planning as a reference. Adapt relevant concepts into Recoil Lua; do not run Petra directly or port it wholesale. Campaign strategy, logistics, territory, and faction behavior are later work.

## 3. Communication protocol

External communication uses gRPC and Protocol Buffers. Define versioned messages in `proto/` and generate bindings for each adapter.

| Domain | Initial messages | Purpose |
| --- | --- | --- |
| Session | `SessionInfo`, `Heartbeat`, `SimulationStatus` | Lifecycle and health |
| World | `TerrainRegion`, `TerrainPatch`, `Obstacle` | World representation |
| Units | `UnitDefinition`, `UnitState`, `UnitSpawn`, `UnitRemove` | Entity synchronization |
| Player | `PlayerState`, `HeroState` | Player representation |
| Commands | `MoveOrder`, `AttackOrder`, `HoldOrder`, `RetreatOrder` | Military control |
| Combat | `DamageEvent`, `DeathEvent`, `AbilityEvent` | Combat reconciliation |
| Simulation | `Tick`, `StateSnapshot`, `StateDelta` | Timing and state updates |

Protocol requirements:

- Use stable bridge-level IDs, never engine-local IDs as canonical identities.
- Include session ID, simulation tick, and sequence number where applicable.
- Define coordinate origins, units, orientation, and scale explicitly.
- Support full snapshots, incremental updates, bidirectional streams, initial synchronization, and reconnection.
- Separate replaceable high-frequency state from discrete events.
- Reject incompatible versions and invalid commands; bound queues and apply backpressure.
- Apply incoming changes only on each receiving engine's safe simulation thread.
- Treat gRPC as transport, not as the simulation clock.

## 4. Simulation authority

**Outside the active player region:** Recoil owns movement, navigation, combat outcomes, health, orders, and tactical behavior. The host need not create physical actors.

**Inside the active player region:** The host owns physical movement, collision, damage, death, and direct combat interactions. Recoil still supplies strategic objectives, squad positions, formations, targets, reinforcements, and retreat orders. The coordinator forwards intent to host actors and returns authoritative outcomes to Recoil. A combat event must never be applied twice.

**Player representation:** Recoil tracks the player as a special hero unit. The host owns its position, health, abilities, and direct movement. The hero can be targeted and evaluated by military AI; player actions affect battles and objectives.

**Activation/deactivation:** As the player approaches, relevant units become host-game actors. As the player leaves, the coordinator reconciles their state with Recoil and removes physical representations as appropriate. Identity, health, faction, position, and orders must survive each transfer.

## 5. Terrain integration

The RTS operates on an approximation of host terrain. For Minecraft, extract surface elevation, water, impassable blocks, structures, other obstacles, traversable ground, and relevant changes from a selected region. Convert these into Recoil-compatible map data with documented origin, resolution, and coordinate transforms.

Initially use a fixed, generated battlefield and one surface elevation per horizontal coordinate. Caves, bridges, and complex vertical geometry are unsupported. Runtime terrain regeneration is not required in the first prototype. Later work can add incremental updates, caches, and navigation changes from construction or destruction.

A future Skyrim exporter should handle landscape, roads, navmeshes, settlements, and worldspaces. The shared terrain schema remains independent of either game's data formats.

## 6. Military units and AI

Create a minimal Recoil game package with infantry and ranged units, teams and factions, health, speed, damage, attack range, collision, and simple formation and combat rules. Cavalry is optional later. Define a shared unit taxonomy that maps RTS unit types to host actors.

Initial AI is deterministic and rule-based, with no LLM dependency. Keep tactical AI in Recoil where possible. Expose modular threat evaluation, squad management, target selection, attack planning, defense planning, and retreat evaluation. A future campaign AI may operate separately at a slower timescale.

## 7. RTS player controls

Controls follow the underlying bridge. Initially support observing armies and squads, selecting friendly formations, issuing move and attack orders, assigning defend and retreat objectives, and returning to RPG controls. A basic external debug interface is acceptable first. Later add an overhead camera and selection controls in Minecraft, then Skyrim. Both interfaces operate on the same canonical simulation state.

## 8. Development phases

### Phase 0 — Technical feasibility

Investigate headless Recoil, minimal game packages, LuaRules interfaces, and integration options. Prove that Recoil starts a headless simulation; a custom rule creates or controls a unit; external commands enter safely; unit state reaches another process; and communication does not block simulation threads. Investigate an unsynchronized Lua relay before requiring a native engine fork. **Deliverable:** Documented, working bidirectional Recoil integration. Do not start Minecraft development until this works.

### Phase 1 — Standalone military simulation

On a simple battlefield, add two teams, infantry definitions, spawning, navigation and attack commands, simple attack/defend/retreat AI, health and casualties, and external gRPC telemetry. **Deliverable:** Two autonomous armies controllable and observable externally.

### Phase 2 — Minecraft integration

Build a minimal Fabric adapter for bridge connection, player positions, test soldier actors, movement synchronization, cross-engine mappings, and basic combat reporting. **Deliverable:** A visible, interactive Recoil-controlled soldier in Minecraft.

### Phase 3 — Terrain and battles

Export a selected Minecraft region, convert it for Recoil, add opposing armies, transfer nearby combat authority, synchronize casualties, and load/unload physical actors. **Deliverable:** About ten soldiers per side in a Minecraft battle where the player participates and casualties persist in Recoil.

### Phase 4 — Tactical AI and RTS controls

Add squad behavior, formation movement, objectives and reactions, army selection and commands, a basic tactical camera/interface, and switching between RPG and RTS controls. **Deliverable:** The player commands and personally joins the same battle.

### Phase 5 — Persistent warfare

Add factions, strategic regions, persistent army movement, territory and settlements, reinforcement and recruitment, distant battle resolution, and persistence across saves. **Deliverable:** A military simulation beyond the player's immediate surroundings.

### Phase 6 — Skyrim adapter

Implement the host interface using SKSE. Reuse Protobuf, the coordinator, Recoil game package, AI, and campaign simulation. Replace world extraction, host entities, combat integration, and controls. **Deliverable:** A minimal Skyrim battle driven by the same RTS engine.

## 9. Nonfunctional requirements

**Performance:** Never block Minecraft's main server tick or Recoil's synchronized simulation thread on network calls. Batch state, prioritize combat events, measure latency and performance, configure active radius and physical actor limits, and scale up only after measurement.

**Reliability:** A process restart must not permanently corrupt the other process. Pause or degrade safely on disconnect. Prevent duplicate spawns, damage, and deaths. Recover from snapshots where possible. Log authority transfers and failures. Preserve reproducible inputs where practical.

**Security:** Begin local, offline, and single-player. Bind services to loopback by default, authenticate nonlocal exposure, validate commands, and never allow arbitrary remote code execution.

**Maintainability:** Separate gameplay rules from transport. Treat schemas as versioned public contracts. Minimize upstream engine changes. Pin tested Minecraft, Fabric, Recoil, Protobuf, and gRPC versions. Keep integration tests, deterministic fixtures, development notes, and known limitations. Check licenses before copying AI work and do not distribute proprietary game assets.

## 10. Suggested repository organization

| Path | Purpose |
| --- | --- |
| `proto/` | Shared Protobuf contracts |
| `bridge/` | Coordinator and session management |
| `adapters/recoil/` | Recoil integration and native gateway if needed |
| `adapters/minecraft/` | Fabric mod |
| `adapters/skyrim/` | Future SKSE plugin |
| `simulation/` | Minimal Recoil game package |
| `simulation/ai/` | Military AI and Petra-inspired strategies |
| `tools/` | Terrain export, scenario generation, diagnostics |
| `tests/` | Protocol, simulation, integration, and recovery tests |
| `docs/` | Architecture, decisions, plans, and test guides |

## 11. Initial acceptance criteria

The first substantial milestone succeeds when Recoil runs headlessly on Linux; an external gRPC client issues a unit command; Recoil reports changed state; Minecraft uses the same Protobuf schema; one unit is consistently represented in both engines; the player has a Recoil hero representation; two small armies fight in Minecraft under RTS tactical control; damage and casualties reconcile once; state recovers after a controlled disconnect; and host-independent bridge components have no Minecraft dependencies.

## 12. Out of scope for the MVP

Province-scale campaigns; thousands of physical NPCs; human multiplayer synchronization; complete Minecraft or Skyrim world conversion; complex underground or multilevel navigation; advanced logistics or economics; LLM military decisions; a complete in-game RTS interface; and Skyrim before the Minecraft prototype is proven.

## 13. Immediate next steps from the original specification

1. Review Recoil's current headless, LuaRules, and external communication implementations.
2. Identify the smallest viable bidirectional integration mechanism.
3. Review a minimal Recoil game package and its unit definitions.
4. Establish pinned development dependencies.
5. Draft initial Protobuf contracts.
6. Produce a brief technical design and proof-of-concept plan.
7. Implement the Phase 0 integration experiment.
8. Record measured results and unresolved limitations.

Do not assume Recoil has a gRPC server or that synchronized Lua can perform external network operations. Validate both before implementation.

**Central principle:** One RTS simulation, many host worlds. Minecraft establishes the bridge; Skyrim tests whether the architecture is genuinely reusable.

**Largest unresolved risk:** The Recoil gateway. Documented synchronized/unsynchronized Lua messaging and socket access in some unsynchronized environments do not yet prove a reliable headless gRPC integration.
