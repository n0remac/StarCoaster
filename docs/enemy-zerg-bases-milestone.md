# StarCoaster milestone: Productive enemy Zerg bases

Status: SPEC / NOT IMPLEMENTED
Date: 2026-11-08
Planning baseline: `76f38af` (main and completed economy fixes)
Implementation branch: `enemy-zerg-bases`
Next milestone: enemy economic and strategic AI

## 1. Goal and player experience

Replace the arbitrary perimeter unit creation of generated ordinary-park defense with **one genuine, visible, destructible Zerg colony near the park edge**. That colony produces its attackers through native OpenBW Hatchery/Larva/Egg/Zergling mechanics. Attacks are scheduled and commanded by the existing scenario runtime, not by a second StarCraft simulator. The player can hold the park or counterattack the enemy base; damaging the production chain weakens future waves, and destroying the Hatchery ultimately stops new units from that base.

The economy milestone is the prerequisite. Preserve its native Terran Command Center, four SCVs, minerals, geyser, finite costs, SCV construction, and normal OpenRCT2 park gameplay. The existing wave options remain visible in Map > StarCraft Settings. Ordinary parks receive this enemy-base policy by default when the new milestone is fully activated; authored fixed/rotating and finite missions retain their explicit existing semantics.

Target minimum demonstration:
1. Choose a supported ordinary stock scenario from the normal browser New Game flow.
2. See the Terran economy in a valid site and a separated Zerg Hatchery/Spawning Pool colony in a valid perimeter site.
3. Observe native Larvae, Eggs, and newly produced Zerglings appear at the colony; no attacker is manufactured by `actor.spawn`.
4. After preparation time, several completed, colony-produced Zerglings form an attack group and attack-move into the park.
5. Terran units can reach and destroy the enemy Spawning Pool and Hatchery. Existing Zerglings fight on; subsequent Zergling training fails without its prerequisite, and future production ends with the Hatchery.
6. A browser reload/second client and a bridge restart do not resurrect destroyed structures, issue duplicate training commands, manufacture lost waves, or duplicate units.

## 2. Verified baseline and integration points

- `docs/automatic-zerg-waves-plan.md` and `docs/automatic-zerg-waves-verification.md`: generated parks use `spawn_policy: automatic_perimeter`; a durable Go wave scheduler chooses one reachable edge cluster, journals origins/composition/request IDs, and orders native attack-move. Settings, blocking, mixed-client synchronization, and no-catch-up behavior exist.
- `scripts/prepare_existing_defense.py`, `scripts/scenario_package.py`, and `scripts/create-world-base-map.py`: source parks are copied into ignored run-data, inspected, provisioned with a generated Terran economy, and staged for native initialization. The current generated scenario supplies a Command Center via `initial_structures` and a finite economy via `economy.starting_entities`; it has **no enemy base**.
- `docs/player-economy-plan.md`, `docs/player-economy-e4-verification.md`: finite Terran economy is integrated for ordinary maps, with explicit no-valid-site behavior. Some expensive E5/browser fault and playthrough gates were left for manual review; this milestone must not silently claim those were completed.
- `scenarios/mt-zergling/scenario.json`, `internal/world/scenario.go`, `cmd/world-bridge/scenario_runtime.go`, `tests/test_zerg_base_lifecycle_live.py`: authored native Zerg Hatchery/Spawning Pool structures, stable identities, combat targeting, demolition, restart, and second-client projections already exist.
- `docs/native-zerg-production.md`, `openbw-bwapi-module/src/WorldZergProductionProbe.h`: native Hatchery -> Larva -> Egg -> Zergling *pair* production was demonstrated, including real resource/supply/prerequisite rejection. OpenBW already owns those morphs. The probe is test-only; **a production scheduler for ordinary enemy bases is not yet implemented**.
- `openbw-bwapi-module/src/WorldAdapter.h` / `WorldUnitController.h`: native training command paths exist but are currently authorized around player/owner and linked production targets; do not assume they can be sent unchanged for autonomous enemy production.
- `openbw-bwapi-module/src/WorldAssaultController.h`: native attack-move and combat control should be reused, not recreated inside Go.
- `.agents/skills/starcoaster-verify/SKILL.md`: choose focused tests first, never overlap shared-port live suites.

Do not interpret a successful native probe as proof of a full browser gameplay loop. No live test has been run for this specification.

## 3. In scope / out of scope

In scope:
- One generated Zerg base in the perimeter band of eligible ordinary parks, potentially more after a separate scale gate.
- Native completed Hatchery, Spawning Pool, supply source (Overlord or equivalent native-validated setup), native Larvae/Eggs/Zerglings, visible creep if the pinned engine and projection support it.
- Native funded Zergling production and deterministic attack assignment; bounded preparation/attack intervals.
- Base and prerequisite structure damage/destruction; no cheating replacement units after loss.
- Durable base identity, unit lifecycle, attack assignment, restart/reconnect/map-switch recovery, explicit blocked states, a compact shared status, and cache-version compatibility.
- Existing difficulty, enable/disable, and interval settings adapted to base-driven assaults.

Out of scope:
- Full enemy Drone mining, economic budgeting decisions, constructing new buildings, expansion decisions, strategy selection, and tactical AI (next milestone).
- Hydralisk/Ultralisk creation without their real production prerequisites. In generated base-backed mode use Zerglings only initially; preserve old mixed unit tiers for authored/legacy automatic waves.
- New factions, research/upgrades/abilities, campaign objectives, Zerg running rides, RCT guest combat, persistent complete OpenBW save serialization.
- Editing a user's source park in place, globally disabling native collision or terrain rules, unlimited spawned units, or a replacement native pathfinder.

## 4. Authority, contracts, and identity

- OpenRCT2 owns authoritative park dimensions, land/scenery/ride/terrain state, normal park actions and multiplayer rendering. Prepare a derived copy; never mutate the supplied source save.
- OpenBW owns Zerg buildings, player ownership, creep (if supported), Larva/Egg morphs, real mineral/supply deductions, training prerequisites, combat, movement and native unit IDs. Both native participants must agree on initialized state.
- Go coordinates selection, base configuration/identity, high-level pacing, generation-qualified bindings, durable intent and attack group membership. It may authorize internal enemy orders but must not implement a parallel production/economy/physics engine.
- Native units must be observed via the actor/native structure registries. An Egg morphing on the same native ID must preserve the canonical binding; the extra Zergling receives its own new ID. Every produced Zergling must be attributed to an existing living Hatchery/colony and assigned to at most one attack wave.
- Distinguish **enemy base initialization**, **native training order**, **observed production**, **wave assignment**, **assault order** and **observed death** as different durable states. Native acceptance of an order is not proof that two Zerglings exist yet.
- Never expose enemy train commands through the player-facing command card/API. Introduce a narrow bridge-origin, enemy-participant command path with session, native generation, target binding, revision/frame, type, authorization, and durable request ID. Confirm actual engine support before designing an API around assumed behavior.
- Journals must be versioned. A running legacy wave retains its old mode and request IDs; a bridge restart cannot silently upgrade or recreate a current session.

## 5. Placement policy — generated ordinary parks

Placement happens once before readiness, after actual source geometry and Terran economy placement are known. A bounded deterministic chooser scans eligible tiles around the **usable perimeter**, not merely four side midpoints; the band is inside the native playable boundary, never outside the map.

A candidate must satisfy all of:
1. Real OpenRCT2/native map dimensions and confirmed geometry, safe elevation, level/dry footprints, appropriate land/ownership/projection constraints, no ride/path/scenery/entrance/object overlaps, and no collision with Terran Command Center, resource fields, workers, reserved approaches or defense build sites.
2. Fits a Hatchery (currently declared 4x3), a Spawning Pool (3x2), larva/egg emergence and a useful Zergling assembly area. Include appropriate separation, creep/prerequisite validity, and production exits.
3. Native-confirmed ground clearance **outward from production** and an attack route toward a reachable park interior. A small Terran counterattack also must have a reachable approach to the base. A coarse navigation-mask pass alone does not prove either native route or native building placement.
4. Does not trap or destroy park playability; no automatic terrain flattening, building deletion, hidden collision exemptions or forced park-object removal.
5. Is stable for a given source hash/policy version/seed and valid for the current derived scenario. Select from deterministic, evenly considered candidate anchors, not side-biased first-fit.

Decide the placement with both bases in view: extending Terran layout generation or a two-pass deterministic solver is preferable to randomly searching later and invalidating the Terran site. Reuse any expensive geometry/native-map cache whose actual inputs remain unchanged; bump generated layout policy and preparation/cache identities for new scenario metadata. Persist chosen native tiles, projection tiles, types, footprint, seed/version and IDs before starting.

A blocked Zerg site must be explicit (e.g. `enemy_base_waiting:no_valid_perimeter_site`), keep ordinary RCT gameplay functional, and **not** silently revert to free perimeter unit spawning. Re-evaluate on relevant confirmed geometry revisions at a bounded cadence; do not scan per tick or indefinitely delay the browser handoff. Retain the separate Terran-economy blocked status and no-wave gate.

Start with exactly **one** base. Multi-base selection is a follow-up only after 1-base gameplay works on ordinary maps; enforce distance, native capacity and CPU budgets before enabling multiple bases.

## 6. Enemy production and wave behavior

At initial session bootstrap, create one completed Zerg Hatchery and Spawning Pool plus validated native supply capacity on the enemy side. Verify which CHK initialization path, participant ownership, and hatchery creep/larva behavior are actually available in the pinned engines and whether projections are correctly read-only and destructible. Do not solve spawn collisions by bypassing native checks.

Production policy for milestone B:
- Use the engine's Hatchery/Larva train path to spend real native minerals, wait through Egg morph, and create actual native Zerglings. Check `canTrain` and report native rejection reasons; never set unit completion manually.
- A finite scripted **enemy production budget** may be initialized as native mineral balance. A bounded, deterministic top-up of native minerals is permitted only if a minimal native proof shows a safe synchronized API and idempotent journaled accounting; it must never bypass prerequisites, training time or supply. If no safe top-up path exists, start with an explicitly finite bank, expose `production_exhausted`, and defer infinite-loop balancing to enemy economy AI. Do not fake native balance updates in Go or give the human economy resources.
- Produce and retain a capped staging pool near the Hatchery. Completed living Zerglings in the pool are assignable. If training cannot keep up with a deadline, dispatch only real available completed units or defer under a bounded policy; no instant compensating `actor.spawn`. Native Zergling production yields pairs per Egg and must not be miscounted.
- Keep the current first-wave **7,200 native-frame** economy preparation default and **2,880-frame** interval as provisional baselines (from `prepare_existing_defense.py`), but measure how many Zerglings can actually hatch during preparation; tune only with a recorded native-frame reason. Frame-based timing is authoritative; pause/readiness interruption must not accumulate a backlog.
- Existing Easy/Standard/Hard settings may change desired group sizes/cadence for **uncommitted** waves. They must not add new units or overwrite already assigned groups. Current mixed Zergling/Hydralisk/Ultralisk tiers remain exclusive to policies capable of actually producing those types.
- Record wave ID, colony ID/generation, exact actor IDs, unit types, native destination/formation, assignment state and order request identities **before** dispatch. Reconcile observed live actors after restart; no double wave, double training, or reassignment of a dispatched unit.
- Use existing native assault control to attack-move from the colony toward reachable interior objectives. Do not periodically reset units engaged in combat. Geometry changes may trigger a bounded native route re-evaluation; incapable paths surface status rather than teleporting.
- Disabling waves stops new assignments/orders, keeps committed attackers active, and bounds the idle garrison/production. Re-enabling starts a fresh countdown. Destruction of the base stops its production independently of that toggle.
- Destroyed Spawning Pool: native prerequisites prevent further Zergling training, but existing eggs and units finish/fight according to OpenBW. Destroyed Hatchery: no new larvae or local production; living attackers continue normally. No replacement base is built in this milestone. Do not change normal RCT scenario victory/defeat when a base is killed; expose a "Zerg colony defeated" defense status.

## 7. Implementation phases and handoff gates

### B1 — Geometry and native base bootstrap
1. Write failing deterministic tests for edge-site selection, both-direction reachability, footprint overlap, inability to place, cache IDs, source integrity, and one-time session bootstrap.
2. Add versioned base policy/config to validated generated scenarios; preserve authored missions and old journals. Implement deterministic, bounded enemy site selection coordinated with Terran economy planning.
3. Stage real Hatchery/Spawning Pool/supply native entities through the existing native map, project them into the park with stable scenario IDs, and correctly handle terrain, ownership and creep. Validate no invisible solid duplicate blocks units.
4. Focused exit gate: in at least one ordinary-park fixture, both native participants observe one and the same base, the browser/native projection identifies it, and Marines can reach it. A deliberately blocked fixture shows a clear status without a free wave.

### B2 — Native production lifecycle and funding
1. First test failure/duplicate/restart conditions for enemy-only training orders; prove native funded training, native rejection, paired Zergling birth, and Larva/Egg canonical binding.
2. Introduce the smallest authorized server-to-enemy-participant train path; implement bounded native production orchestration. Use BWAPI state rather than inferred production timers.
3. Introduce explicit starting mineral/supply capacity and prove it with a native fixture. Only add refill after a separate native feasibility proof and a durable exactly-once policy; otherwise document a finite starting supply.
4. Focused exit gate: a visible Hatchery spends native minerals, produces real eggs and Zerglings, and a bridge reconnect does not repeat a train or duplicate any actor.

### B3 — Wave ownership, combat, and killable production
1. Write failing wave-assignment tests: due with too few units, pair birth, duplicate packets, late acknowledgements, failed route, death during assembly, destroyed prerequisite, destroyed Hatchery, restart and settings toggle.
2. Add an explicit `base_production` defense policy (not a reinterpretation of `automatic_perimeter`), journal source base and observed actor identities, and route already-produced unit groups through the existing native assault controller.
3. Stop issuing free `actor.spawn` for that policy. Use bounded retries and status for missing units/routes/funding; preserve existing authored and legacy policies.
4. Focused exit gate: units visibly emerge from the colony, attack the park, can be fought, and killing the base prevents all further production while existing attackers remain consistent.

### B4 — Normal-map release hardening / manual gameplay gate
1. Check one compact authored fixture, two ordinary park geometries including one larger/elevated case where feasible, and one intentionally impossible base-site case. Verify normal New Game selection, cache reuse, map switch, 2-client observer state, confirmed construction revision and bridge reconnect.
2. Bound all recurring work: site selection, native checks, journal size, actor cap, staging units, production polling and log volume. Avoid expensive map rebuilds on a settings-only update.
3. Update Map > StarCraft Settings and/or compact shared status with enemy colony count, production/attack state and actionable blocking reasons. Keep existing difficulty/interval/enable controls.
4. Write `docs/enemy-zerg-bases-verification.md` with exact test revisions/commands, native observations, skipped checks, elapsed frames and ignored artifact paths; update user-facing instructions and technical protocol.

Manual exit: player performs a browser playthrough building Terran defenses, watches genuine production and an attack, counterattacks and destroys the Spawning Pool/Hatchery, and confirms the next planned attack never materializes from a dead source. Do not automatically start long Chromium/manual gameplay suites or full video captures; offer the manual script for the user and ask for observed bugs. The milestone remains "verification pending" until the player checks it.

## 8. Focused validation policy (avoid long test loops)

- **Regression tests first** for every feature/fix; run the smallest targeted Go/Python/JS/C++ check while developing.
- Run `scripts/project.sh validate-scenario` for changed authored packages, targeted native probes for real training/assault outcomes and `scripts/project.sh test` once per coherent integration boundary (or the relevant packages when full suite is costly).
- Do not run `scripts/project.sh test-live`, long `record` sessions, graphical browser playthrough loops, or comprehensive parallel port-consuming suites automatically. Native live probes must use isolated ports and run sequentially.
- Provide the human a concise manual check: New Game -> identify Terran/colony -> watch larva/egg -> wait for attack -> train Marines -> counterattack -> kill Pool/Hatchery -> observe subsequent wave behavior -> reload/rejoin. Capture exact revision, map and observations.
- Build/deploy to DEV after focused gates and code review; do not merge to main or release to production on presumed browser success. Mark missing expensive checks explicitly, rather than labeling them passing.

Suggested new regression files: `internal/world/scenario_enemy_base_test.go`, `cmd/world-bridge/enemy_base_runtime_test.go`, `tests/test_enemy_base_layout.py`, `tests/test_enemy_base_production_native_live.py`, `tests/test_enemy_base_assault_native_live.py`, and a small plugin settings/status test. Names are provisional; reuse existing test harnesses instead of creating duplicate infrastructure.

## 9. Specific code surfaces to inspect in order

1. `scripts/prepare_existing_defense.py`, `scripts/scenario_package.py`, generated OpenRCT2 economy-layout logic, `scripts/create-world-base-map.py`, and cache-key tests: site selection and synchronized native map bootstrap.
2. `internal/world/scenario.go` and scenario validation: explicit `enemy_base`/`base_production` schema, compatibility, stable IDs and migration.
3. `cmd/world-bridge/scenario_runtime.go`, `internal/world/scenario_runtime.go`, `cmd/world-bridge/scenario_defense.go`, `scenario_status.go`: authority for production pacing, committed attack assignments, journal/restart semantics and settings.
4. `openbw-bwapi-module/src/WorldAdapter.h`, `WorldUnitController.h`, `WorldZergProductionProbe.h`, native actor/building observations: target authorization, native `canTrain`, Zerg pair morph and controllable attack groups.
5. `openrct2-plugin/rts-bridge.js`, `bridge-protocol/README.md`, generated entity declarations and projection order: synced art/status/command boundaries. Regenerate catalogs via `scripts/project.sh generate` rather than editing generated registries.
6. Existing probes `tests/test_zerg_base_lifecycle_live.py`, `tests/test_zerg_production_native_live.sh`, `tests/test_universal_park_defense_live.py`, `tests/test_player_economy_e4_native_route_live.py`, `tests/test_player_economy_e4_blocked_native_live.py`.

## 10. Risks and decisions to settle in B1/B2

- Real native prerequisites: Hatchery creep, Spawning Pool placement, Overlord supply, Larva egress and which native participant actually owns Zerg production. Verify in the pinned engine rather than assuming StarCraft wiki behavior directly maps to this fork.
- Generated-polygon placement may be impossible near the perimeter for park saves with crowded land, incompatible ownership or isolated high ground. Favor a visible blocked state and safe park play over arbitrary fallback enemies.
- Production speed may not satisfy 8 Zerglings per 2,880 frames with a single Hatchery. Measure genuine frames and constrain wave size/cadence or add capacity only after B2 evidence.
- Enemy resource refill may require a new native command. Avoid duplicated grants on reconnect, bypass of native costs, or sharing resources with player 1. Time-box proof before committing to infinite production.
- Native-created units have IDs and morph semantics different from existing durable external spawn requests. Model assigned waves as references to native observed units, not as coordinate-spawn requests with fabricated outcomes.
- Enemy base destruction during an outstanding training command or wave assembly must reconcile from complete native observations; park scenery and native building identity must not be resurrected.
- Source/cache behavior must preserve the already-working E4 finite economy startup, including explicit blocked maps. This is new generated metadata, not a reason to invalidate all prebuilt native maps on every load.

## 11. Next milestone — Enemy AI (not part of B1–B4)

A1. Native Zerg economy: Drones mine minerals, return cargo and fund production; retire scripted initial/top-up allowances.
A2. Base management: AI selects workers, structures, production priorities and expansion sites; construction must use actual native build/creep/prerequisite systems.
A3. Strategic army management: choose composition and wave timing from resources, losses, difficulty and enemy state; replace simple scheduling decisions, not the native simulation.
A4. Tactical behavior: defend attacked bases, choose objectives, regroup and react to park defenses. Keep OpenBW authoritative for navigation, combat and production.

After the two-sided economy/AI loop works, layer in native research/upgrades, abilities and additional units in a separate milestone.

## 12. Definition of done / decision

B1–B4 are complete only when a generated ordinary park has a valid visible Zerg colony that **actually trains** real native Zerglings and launches them at the park; players can destroy its production chain; no fallback magic spawns conceal failures; browser and native share consistent observed actors, structures and statuses; session recovery does not duplicate effects; authored scenarios remain compatible; DEV has focused passing checks; and the user has performed the expensive final gameplay smoke test.

**Implementation order:** B1 (placement/bootstrap) -> B2 (production) -> B3 (wave conversion/destruction) -> B4 (integration/manual acceptance) -> A1 onward (enemy AI).
