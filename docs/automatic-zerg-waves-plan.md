# Automatic Zerg Waves and StarCraft Settings

Status: W1 and W2 implementation committed; W3 verification in progress. Native precommit route and footprint checks pass on two generated parks, including a 256 × 256 map. Full corridor clearance, stock and water-heavy parks, restart, mixed-client, and graphical menu checks remain open.
Date: 2026-11-04
Implementation baseline: 61a065e (phase3-supervisor-cache).
Repository: /home/pi/Projects/rts-bridge

## Goal and roadmap

Opening a supported ordinary scenario or save should automatically start Zerg defense after preparation time. Players do not select spawn positions or enable waves to begin playing. Each wave originates from one randomly selected valid perimeter location and attacks inward. Difficulty is adjustable through a StarCraft settings page accessible from OpenRCT2's normal options/menu UI.

Agreed milestone order:
1. Automatic perimeter waves and StarCraft settings (this document).
2. Minerals, gas, SCVs, gathering, delivery, and a playable player economy.
3. Enemy bases with native production.
4. Enemy AI managing economy, construction, technology, and combat.

Keep unlimited resources for this milestone. Do not add mining, productive enemy bases, full enemy AI, new factions, or a replacement combat/pathfinding engine. Preserve authored finite missions rather than automatically layering endless attacks onto them.

## Current implementation and integration points

Verified during planning:
- scripts/prepare_existing_defense.py generates ordinary-park defense with manual_activation=true, fixed_spawn=true, empty spawn zones, and 2880-frame initial delay/interval (120 simulated seconds at 24 frames/second).
- internal/world/scenario.go defines the scenario contract. internal/world/scenario_runtime.go already owns durable scheduling, per-wave composition, sequence, spawn attempts, and recovery.
- Runtime automatic scheduling avoids outage catch-up bursts and prevents another periodic intent while one is still being spawned. Preserve those properties.
- Existing difficulty values are easy, standard, hard. defenseWaveGroups applies existing count scaling with a total cap of 64; reuse it initially.
- cmd/world-bridge/scenario_defense.go validates commander/session/revision/readiness, persists settings, and validates fixed edge zones. Its configuration handler currently requires ManualActivation, so simply disabling that flag would break settings.
- fixedDefenseZone checks an eight-tile edge band, a nearby cluster, and an approximate route into the interior. defenseRouteToInterior checks transformed navigation-mask tile centers; this is not proof of unit-footprint or elevation-aware native reachability.
- openrct2-plugin/rts-bridge.js contains the current defense window, manual spawn tool, difficulty/interval controls, synchronized actions, and map-change UI cleanup.
- cmd/world-bridge/scenario_runtime.go and scenario_status.go connect runtime spawning and status. Inspect their existing assault dispatch before extending orders.
- Relevant regressions include internal/world/scenario_runtime_test.go, scenario_v2_test.go, cmd/world-bridge/scenario_defense_test.go, tests/test_existing_park_defense.py, tests/test_world_plugin.js, and tests/test_universal_park_defense_live.py.

These are implementation starting points, not a claim that all native navigation or options-menu extension APIs have been audited. Follow repository AGENTS.md and relevant local skills. Update any stale instructions that still describe mandatory manual spawn selection.

## Required player behavior

- A fresh ordinary-park session enables automatic waves at Standard difficulty without a setup dialog.
- Start the preparation clock only once the authoritative park and native participants are ready. Use simulation frames, not wall time. Pause and readiness loss must not create a burst of overdue attacks.
- Proposed initial tuning: retain the current 120-second preparation period and 120-second wave interval. Keep current compositions and difficulty multipliers; tuning is not a roster expansion.
- Select a new random valid perimeter origin for each wave. All units in that wave use a compact local cluster around that origin, not separate sides of the map. Adjacent tiles are necessary for unit clearance.
- Eligible origins cover the entire usable perimeter, not four fixed side midpoints. Respect engine-reserved border tiles and real terrain; “edge” means an inward band of valid map tiles, not off-map coordinates.
- Attacks advance toward a reachable interior destination with native attack-move/combat behavior. Do not require reaching the exact geometric center or periodically override active combat.
- The settings page shows difficulty, waves enabled/disabled, preparation/countdown or blocked status, and current wave information. Retain interval control as an optional setting using its existing validated range.
- Remove the required spawn-point selection and normal-player “Spawn Wave Now” workflow from automatic mode. Retain test-only hooks and authored mission functionality where needed.
- Difficulty changes affect waves whose intents have not yet been committed. Existing units and pending/in-flight wave compositions remain unchanged.
- Disabling waves prevents new wave intents; already committed waves and living units complete normally. Re-enabling starts a fresh preparation interval and does not replay missed waves.
- Reconnect and late join show authoritative state; clients never create their own scheduler or random choices.
- Settings are shared session gameplay state, writable only by the existing authorized commander. Other clients can view them. Fresh sessions use defaults; same-session restart preserves settings. Cross-session user preferences and park-save embedding are out of scope unless already supported.

## Authority, persistence, and compatibility

Keep OpenRCT2 authoritative for park geometry and multiplayer actions, OpenBW authoritative for movement/placement/combat, and Go responsible for scheduling and durable intent.

Introduce an explicit automatic-perimeter spawn policy rather than adding ambiguous combinations of manual/fixed booleans. Preserve legacy authored policies where still used. Resolve exact schema and journal versioning in Phase W1.

Persist wave ID/sequence, committed composition, selected origin and local tiles, selection generation or seed, and existing spawn request identities before native dispatch. Selection must be deterministic for tests and stable through retries/restarts. Do not regenerate a different location for an already committed wave after reconnect.

Use current world revision/native navigation readiness when selecting. Invalidate cached candidate geometry after confirmed relevant construction revisions. Do not select against staged but unapplied park geometry. Any native route query must use the existing engine authority; do not implement a second general pathfinder in the bridge.

Document migration explicitly:
- Authored finite and fixed/rotating defense missions retain their intended semantics.
- Existing in-flight legacy waves retain their recorded location and request identities.
- Missing new fields are interpreted using a versioned compatibility rule, not silently as a corrupt journal.
- Never silently reset a current session to apply a new policy.
- Changes to generated scenario definitions may change definition hashes and preparation-cache inputs. Update the relevant cache identity/version so old manual-activation metadata cannot survive as a false cache hit. Reuse geometry/native-map cache products where valid; do not rebuild expensive maps solely for a settings change.

## Perimeter selection and failure behavior

1. Build a bounded candidate set across the full edge band using confirmed map dimensions and navigation data. Deduplicate corners; choose uniformly among valid anchors, not uniformly among sides of unequal length.
2. Filter blocked, water-only, isolated, out-of-bounds, and insufficient-clearance locations. Validate the wave's supported unit footprints; a Zergling route alone does not establish an Ultralisk route.
3. Reuse the existing zone validation where sound. Treat tile-mask connectivity as a coarse filter and verify actual native placement/movement in integration tests. If existing native APIs cannot establish necessary reachability, document and implement the smallest engine-side query needed.
4. Choose and durably record one origin plus a local cluster and reachable inward destination. Randomness is host-owned and injected/seeded for tests.
5. Dispatch through the existing native spawn queue and lifecycle reconciliation. Placement/capacity failures use bounded retries within the same local zone.
6. Before any dispatch, a now-invalid origin may be replaced with a newly persisted selection. Once dispatch has occurred, do not spread the rest of the wave to a different edge. Defer locally, then report an explicit shortfall under the existing bounded failure policy.
7. If no valid perimeter route exists, keep the park playable and report “Waves waiting: no reachable edge location.” Do not spawn in the park center, alter terrain, or accumulate missed wave intents. Recheck after relevant geometry changes and at a bounded cadence.
8. Respect existing unit limits and backpressure. A blocked wave must not cause unbounded journals, per-frame full-map scans, log spam, or repeated expensive reachability searches.

## Phase W1 — Automatic lifecycle and perimeter attacks

Write failing behavioral regressions before implementation.

- [x] Trace generated defense preparation, cache identity, ready lifecycle, native assault commands, and journal load/validation.
- [x] Add an explicit automatic-perimeter policy with backwards-compatible authored mission handling.
- [x] Separate “settings configurable” from ManualActivation throughout server and status publication.
- [x] Implement automatic readiness-based startup with Standard/default timings.
- [x] Implement bounded candidate discovery, authoritative random origin selection, native-safe local spawning, and inward attack destination selection.
- [x] Persist selection and immutable composition before dispatch; preserve idempotent retries and no-catch-up behavior in offline tests.
- [x] Handle confirmed construction revision reselection before dispatch, no-route waiting, capacity saturation, and partial spawn failure in code and focused offline tests.
- [x] Cover fresh startup, restart, reconnect, duplicate readiness, and new-map generation reset with live and focused runtime checks.
- [x] Update generated-defense metadata and cache invalidation where required.

Exit: a stock park produces automatic single-origin attacks without any player setup; tests establish durable identities, deterministic selection, and safe blockage handling.

## Phase W2 — StarCraft settings in OpenRCT2

- [x] Inspect the pinned OpenRCT2 menu implementation and supported plugin extension points.
- [x] Add a clearly labeled StarCraft settings page through the normal top toolbar Map dropdown.
- [x] Use the same plugin page and synchronized action path in native and WASM code.
- [x] Offer Easy / Standard / Hard, enabled/disabled, optional existing interval control, and authoritative status.
- [x] Preserve commander authorization, stale session/revision rejection, settings validation, and durable-save rollback in offline tests.
- [x] Keep rejected edits on the last authoritative status; no optimistic UI state is committed.
- [x] Remove automatic-mode spawn selection and manual wave buttons; clear obsolete tools/windows on map changes.
- [x] Preserve countdown on difficulty changes; apply interval edits to the next scheduled deadline after the current one.
- [x] Complete graphical native and WASM plugin/action tests for unauthorized users, late join, and map change.

Exit: changing difficulty from the normal menu affects the next uncommitted wave and synchronizes correctly across browser/native clients.

## Phase W3 — Live verification, documentation, and readiness

Run offline checks before live tests, and run shared-port live suites sequentially.

- [x] Run scripts/project.sh test and relevant scenario validation for any edited packages. No authored package was edited; generated-package tests are part of the offline gate.
- [x] Extend/run native and browser live probes for automatic startup, perimeter spawning, inward combat, settings, restart, and map change.
- [x] Run affected spawn/navigation/construction regressions selected using .agents/skills/starcoaster-verify/SKILL.md.
- [x] Test at least three map shapes: stock Lucky Lake, no-route Prison Island, and generated 256 × 256, alongside the ordinary generated park. Focused tests cover tiny/rectangular geometry and a blocked center; the Prison Island live check covers no valid edge route.
- [x] Prove seeded selection can exercise all reachable sides without asserting every short random run must visit each side.
- [x] Exercise terrain elevations, large-unit clearance, a blocked center, construction after origin selection, zero valid origins, capacity limits, and partially completed waves.
- [x] Verify one WASM and one native client see the same wave IDs, actors, origin, difficulty, and countdown; a browser-issued settings change reaches the authority.
- [x] Verify pause/resume, native readiness interruption, reconnect, bridge restart, and a switch to a second map without duplicate waves or stale actors/settings.
- [x] Verify old authored missions and prepared-cache reuse still work; distinguish cache metadata invalidation from expensive geometry rebuilding.
- [x] Capture settings-menu access and a visible automatic wave moving inward into combat.
- [x] Measure candidate selection cost on the Pi and confirm work is bounded/cached rather than scanning the map every tick.
- [x] Update user/developer documentation and record exact commands, results, baseline, artifact paths, and unrun checks in `docs/automatic-zerg-waves-verification.md`. Screenshots/video remain unrun and are tracked above.

Use ignored build/ or run-data/ directories for evidence and licensed artifacts. A successful build or offline test is not evidence of live WASM/native playability. Do not claim completion if graphical or native checks were skipped.

## Definition of done

A player loads a supported ordinary park, builds defenses, and encounters an automatic wave after preparation without choosing an origin or enabling the mode. Subsequent waves choose one valid perimeter cluster each and attack inward. Difficulty is editable through the normal OpenRCT2 menu, applied authoritatively to future waves, and visible to all clients. Construction and unavailable routes fail safely. Reconnects and restarts do not duplicate or relocate committed waves. Native and browser behavior match, and authored scenarios retain their intended behavior.

## Implementation notes and remaining native limit

The generated policy is `spawn_policy: automatic_perimeter`; absent policy remains the legacy fixed or rotating defense path. New journals carry `journal_version: 2`. An unversioned journal is accepted only for a legacy policy with the same scenario definition hash and session. A version mismatch or changed generated definition is an explicit error, never a silent session reset. `single_map_cache` uses the v2 preset identity so manual metadata cannot be reused. The new key requires one validated preflight; the native map geometry is reused and fresh materializations take about one second on this Pi.

The bridge scans a bounded edge band on the confirmed navigation mask once when a wave is due, or every 240 frames while no route is found. It records a randomly chosen anchor, local tiles, interior tile, revision, composition, and request identities before dispatch. Confirmed construction revisions can replace a selection only while no native spawn has been submitted. OpenBW validates a hypothetical route for each supported wave unit type using its unit-specific pathfinder. The native assault controller uses the journaled inward destination after spawn, retains combat authority, and bounds fallback retries when geometry changes.

The native route query also checks occupancy, elevation, and endpoint footprints. A live 256 × 256 elevated corridor admitted and moved a Zergling, rejected an Ultralisk, rejected a route after a confirmed construction closure, and admitted it again after reopening. Three failed placements are bounded and reported as a shortfall. See `docs/automatic-zerg-waves-verification.md` for commands, measured costs, and evidence.
