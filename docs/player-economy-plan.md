# StarCoaster milestone: Native player economy

Status: E0 and E1 are complete on authored fixtures. E2 gathering and E3 native worker construction pass their focused native and graphical browser gates on `economy-e3`. The E3 ambiguous-creation policy retains an unresolved reservation; worker-death and concurrent-edit fault probes remain for the E5 integration gate. E4 ordinary-park placement and E5 release remain outstanding. See the stage verification reports for measured coverage and limits.
Date: 2026-11-05
Reviewed baseline: f38e732ab756d47780777a9ea3baa18844a194d3
Repository: /home/pi/Projects/rts-bridge
Preceding milestone: automatic Zerg waves, merged and deployed on DEV.

## 1. Outcome and scope

On a supported ordinary park, the player receives a visible Command Center, four SCVs, nearby mineral fields, a nearby Vespene geyser, and a finite starting balance. The player sends SCVs to mine, delivers resources to the Command Center, trains workers, builds a Depot and Barracks, trains defenders, builds a Refinery, and funds gas-dependent units while automatic Zerg waves continue.

OpenBW owns mining, cargo, delivery, depletion, balances, supply, prerequisites, construction progress, production, cancellation refunds, movement, and combat. The bridge transports commands and observations and coordinates identities and park geometry. Do not recreate economic simulation in Go or JavaScript.

Roadmap remains: automatic waves -> player economy -> productive enemy bases -> enemy AI.

This milestone includes worker construction for all currently exposed player Terran buildings, not just new economy buildings. Otherwise the existing free completed-building path bypasses the economy. Include Command Center, Refinery, Supply Depot, Barracks, Academy, Factory, and Armory; retain native prerequisites. Existing supported combat units remain available through native training.

Defer enemy economy/AI, additional factions' worker economies, add-ons, lift-off/landing, research, general automation of workers, resource trading with park cash, and complete OpenBW save-state serialization. Do not expand the roster beyond what this loop needs.

## 2. Research findings at the reviewed baseline

| Area | Verified source | Consequence |
| --- | --- | --- |
| Unlimited economy | scripts/prepare_existing_defense.py gives 50,000 minerals/gas and unlimited_resources=true; WorldProductionFixture.h refills balances below 10,000 to 50,000 | Disabling the refill alone is insufficient; replace starting fixtures and remove hidden supply |
| Native resources and production | WorldUnitController.h publishes player.resources every 24 frames; WorldBuildingState.h derives production availability from BWAPI | Reuse balances, half-supply representation, native training and existing building command cards |
| Building placement | rts-bridge.js executes largesceneryplace; WorldAdapter.h resolves scenery and calls createUnit for completed native structures | Current construction does not charge native building costs or use an SCV; requires a real lifecycle change |
| Scenario initialization | scenario.go starting_units supports Marines/Zerglings; create-world-base-map.py emits those plus map-only supply fixtures | Add typed economy initialization without proliferating one field per new unit |
| Declarations | generate-starcraft-types.py only accepts unit/building, player/enemy ownership, a fixed command list and fixed animation states | SCV is mostly conventional; neutral resources and worker actions require deliberate schema/generator support |
| Target routing | main.go command validation distinguishes actors and linked park structures; controller handles movement, attack, heal, train, hold, stop | Add resource target resolution and worker verbs through the same authenticated/deduplicated route |
| Native API contract | pinned upstream/bwapi/bwapi/include/BWAPI/Unit.h exposes build, gather, returnCargo, rightClick, cancelConstruction and resource observations | API availability is confirmed; actual fork behavior under park masks must be proven live |
| Rendering | existing actor renderer and scenery-backed building inspector support native state and incomplete Zerg actors | Extend these paths; resource quantities and worker cargo must be observations |
| Recovery | docs/barracks-native-production-design.md distinguishes bridge reconnect from full engine restart | Preserve running native economics through bridge restarts; do not claim full economy save/load |
| Loading | wave release evidence records a 627-second cache hit during swap pressure | Keep tests serial and resource-bounded; measure incremental economy preparation and avoid full asset scans |

Important distinction: research inspected current code and pinned API declarations. It did not run a new mining/construction experiment. Native worker construction, neutral ownership, Refinery replacement, exploration, and projection ordering remain E0 proof obligations.

## 3. Player behavior and initial tuning

Proposed initial configuration, to be validated through play:
- One completed Command Center, four SCVs, 50 minerals, zero gas, six mineral fields with 1,500 each, and one geyser with 5,000 gas.
- No hidden native Supply Depot and no periodic resource grant. Starting supply comes from the real visible native base.
- Workers start idle; the player chooses mining targets. Existing commander ownership remains one shared Terran economy, not one wallet per browser.
- Resource counts, cargo, remaining deposits, construction and training progress come from native observations. Display supply in normal units; retain native half-supply on the wire.
- A compact economy display remains available without opening a production building. SCVs expose Gather, Return Cargo, Build, Stop and movement; incomplete Terran buildings expose native resume/cancel operations where supported.
- Selecting a worker and right-clicking a mineral field or completed friendly Refinery issues gather. Empty ground moves. Friendly incomplete Terran buildings resume construction through the native operation proven in E0. Do not issue gather on a bare geyser.
- Reuse the existing construction palette, requiring one eligible SCV. Multiple selected SCVs use a deterministic eligible worker, shown in the preview; do not issue the same build to all selected workers.
- Native acceptance means an order was accepted, not that a building exists. UI distinguishes requested, travelling, constructing, paused, completed and failed.
- Depleted mineral fields disappear when the native engine removes them. Exhausted gas follows the engine's behavior; do not assume a geyser disappears at zero.
- No automatic grant or respawn after worker/base loss. Show a useful economy-blocked status while leaving ordinary RCT play and wave settings accessible.

Keep the existing 2,880-frame first-wave delay as the initial test baseline, not a promised balanced setting. Measure time to first affordable defense from the proposed start. If a normal player cannot field a small defense before the first wave, adjust the generated economy preparation delay once, based on recorded native-frame evidence. Keep wave composition/difficulty behavior unchanged unless that evidence requires explicit tuning.

## 4. Authority and identity contract

| State | Owner | Adapter responsibility |
| --- | --- | --- |
| Terrain, rides, park geometry and edit permissions | OpenRCT2 | Validate site suitability and synchronize park edits |
| Resource units, quantities, cargo and delivery | OpenBW | Publish resource/worker state and native target bindings |
| Native buildings, costs, progress and refunds | OpenBW | Mirror observed lifecycle into park visuals |
| Build-site reservation and cross-engine linkage | Bridge + ordered park actions | Persist transaction identity, prevent conflicting edits, reconcile observations |
| Resource display and command controls | OpenRCT2 plugin | Show authoritative state and submit authenticated intent |

Add a resource declaration category with neutral ownership, native type, presentation and footprint metadata. Resources are neither hostile combat units nor civilian damage proxies. Derive capability checks from native types wherever possible; do not author mining rates, prices or tech trees in JSON.

Use durable logical IDs for resources and constructed buildings, with a generation-qualified native binding per session. Never identify a resource only by nearest coordinates. Retain refinery/geyser logical site identity across native replacement; record the current native unit and owner. A stale depleted-resource ID or replaced-geyser binding must reject safely.

All new state messages carry existing session, revision/frame and sequencing context. Proposed additions:
- resource.state: logical ID, generation, native ID, native type, position, remaining amount and lifecycle.
- worker observations: native order, target binding, cargo kind and visible state; cargo quantity only if reliably exposed.
- building.state extensions: construction remaining frames/progress and lifecycle; do not reuse training remaining_frames ambiguously.
- Worker verbs through combat.command: unit.gather, unit.return_cargo, unit.build, unit.resume_construction; building cancellation uses one explicit validated command. Final names must be recorded in bridge-protocol/README.md.
- Build intent adds worker ID, registered building type, upper-left park tile, optional geyser site ID, and a durable request ID. The bridge transforms coordinates once; BWAPI build uses native upper-left tile coordinates, not building center pixels.

Reuse commander checks, staged-revision ordering, bounded queues, target generations and duplicate suppression. Publish native failure reasons. Build requests need durable reconciliation beyond the current in-memory command map: losing an acknowledgement must never duplicate a building or deduct twice.

## 5. Construction integration: required design

Use a native-driven construction lifecycle for economy sessions:
1. Validate commander, worker capability, current confirmed revision, park ownership/clearance, native prerequisites and resource target if Refinery.
2. Reserve the site under a durable build transaction. Reservation is not a completed building, native debit, or opaque solid scenery footprint.
3. Issue exactly one worker build order through the owning native participant. OpenBW decides actual acceptance, resource spending, pathing and construction timing.
4. Observe native creation and match it to the transaction using explicit type/owner/site/creation evidence; reject ambiguous matches.
5. Mirror that existing native building into an incomplete park representation through synchronized actions. Bind the observed native ID BEFORE a snapshot can cause generic createUnit reconstruction.
6. Mirror native completion, interruption, cancellation and destruction. Completion enables native production; partial state remains visible and targetable according to the engine.
7. Reconcile late joins/reconnects from current native state and durable links, never by restarting the original build command.

This changes the old assumption that scenery always creates the native building. Introduce an explicit construction-origin marker so economy-native structures cannot fall into the legacy completed-building creation branch.

Collision is an E0 gate: a mirrored structure/resource must not block its own SCV, delivery approach, Refinery placement, or production exit via a duplicate park navigation mask. Use native occupancy for native-owned entities and preserve RCT obstruction of ordinary park edits. Any mask transition still uses both native participants' confirmed-frame lifecycle. Do not globally relax collision or exploration to make the test pass.

Reservation must prevent conflicting synchronized RCT edits while allowing the assigned SCV to approach. Cover rides, paths, scenery, terrain/water changes and direct placement through the stock scenery menu. If durable reservation plus native observation cannot be made safe with current plugin hooks, add the smallest OpenRCT2 action/patch support rather than an optimistic create-and-delete workaround.

Failures:
- Rejected order: release reservation, report native reason; bridge issues no refund.
- Worker killed or redirected before creation: reconcile native order and expire/cancel reservation with a documented bounded policy.
- Worker lost after creation: retain the incomplete building and allow another SCV to resume.
- Cancellation: call native cancellation once; observe engine refund and removal. Never calculate or credit a refund in Go.
- Native building exists but park projection fails: keep a recoverable transaction, block conflicting site edits, retry boundedly and expose failure. Do not create a second building.
- Destruction or user removal: route through the appropriate native cancellation/removal and ordered park reconciliation; never permit RCT refunds or instant scenery replacement to bypass costs.

## 6. Ordinary-park initialization and compatibility

Generate a deterministic economy layout from confirmed source geometry before readiness:
- Search a bounded set of level, dry, usable sites for the Command Center, resource cluster and worker approaches. Check terrain height, existing elements, park ownership/construction rights and native footprints.
- Require real worker routes between mineral approaches and the depot, SCV egress, room for a Refinery, and practical space for initial defenses. A tile-center path alone is insufficient.
- Never flatten terrain or delete existing rides, paths or buildings to force a base into a park.
- Stage into a derived park/session; do not modify the original scenario/save.
- If no usable base fits, keep normal RCT play available, show an explicit placement-blocked state, and hold automatic attacks until economy bootstrap is usable. Do not silently switch to unlimited money. Re-evaluate after relevant confirmed geometry edits with bounded work.
- Start the wave preparation clock only after the base, workers, resource bindings and native participants are ready; no attack backlog during setup.

Persist generated site decisions and bootstrap IDs before initialization. Bootstrap is once per fresh simulation, never per reconnect or bridge restart. Both OpenBW participants must observe the same initialization; use the existing synchronized native creation mechanism or map initialization, not independent local creation loops.

For scenario configuration, add a versioned optional economy block: mode, initial balances, typed starting units/structures, resource sites and generated-layout policy. Define migration before implementation:
- Ordinary generated parks adopt finite economy after all gates pass.
- Authored missions and old fixtures retain explicit legacy behavior unless deliberately migrated.
- Absent economy configuration preserves legacy semantics.
- Economy mode excludes unlimited_resources and hidden supply fixtures; validate contradictory configuration.
- Existing saved RCT parks start a fresh native economy under current fresh-session semantics. Do not pretend their old balances/queues/cargo are restored.
- Imported pre-existing StarCraft scenery requires a declared legacy classification; it must not silently become free economy-owned production. Preserve it as legacy/non-economic scenery or explicitly reject ambiguous conversion. Never silently delete the user's objects.
- Full persistent economy save/load is a separate milestone. Document fresh-session reset in player-facing load behavior and test it.

Version economy layout/bootstrap cache inputs. Reuse source geometry and native-map products where their actual dependencies permit; new units/resource placements may require a different map product. Cache source identity, policy version and layout seed; never bake a running balance or depleted deposit into a reusable preparation cache. Do not invalidate expensive geometry for display-only changes.

## 7. Implementation phases

### E0 — Prove native economy and construction under park navigation

Status (2026-11-05): Native E0 gate passed in an isolated two-participant
fixture. The focused probe proves mining, construction, cancellation, gas,
geyser restoration, mask ordering, and bridge reconnect with native state
continuing. It does not implement or verify park scenery projection of native
resources or buildings; E1/E3 retain that integration work. The test setup
`removeUnit` crash is documented, and the native kill path is verified.

Create one isolated, minimal fixture and focused live probe using existing licensed engines and unique ports. Record commands and native observations.
- Place a real SCV, Command Center, minerals and geyser with correct neutral ownership and initial resource quantities. Verify pinned CHK resource fields or synchronized initialization rather than guessing numeric unit IDs/amount encoding.
- Complete at least two mining/delivery cycles; observe deposit reduction, cargo and native balance increases.
- Build a Depot through SCV build; observe one native debit, incomplete progress, completion and supply increase. Prove park/nav projection does not prevent construction.
- Build a Refinery over the geyser and complete gas delivery. Observe destruction/cancellation and geyser restoration behavior.
- Interrupt/resume construction, cancel once and record native refund; reconnect the bridge without reissuing.
- Verify exploration and canBuildHere behavior on mapped park terrain; identify any minimal engine compatibility patch required.
- Document decisive native IDs, frames, balances, masks and failure cases.

Exit: evidence proves the APIs actually work in this fork and establishes collision, resource ownership, replacement, command attribution and projection ordering. Commit tests and any narrowly necessary native support with the evidence report. Do not proceed with a speculative second economy engine if this gate fails.

### E1 — Entity declarations, state and finite bootstrap

- Extend the one-file generator/schema for neutral resources and worker capabilities/visual states.
- Add SCV, Command Center, Refinery, mineral fields and Vespene geyser declarations; append sprite ledger entries without renumbering existing sprites.
- Extend startup configuration beyond Marine/Zergling arrays compatibly; remove hidden supply and refill only for explicit finite-economy mode.
- Implement resource lifecycle/target bindings, worker state and construction-state observations.
- Reuse player.resources and train-SCV through Command Center production.
- Implement a fixed authored economy fixture first; retain ordinary-park legacy default until E4.

Exit: fixed fixture renders the complete starting economy on native and browser clients; new SCVs train with native cost/supply and bind correctly; reconnect does not duplicate bootstrap.

E1 status (2026-11-05): complete on the fixed `economy-e1` fixture. Both
graphical client types rendered the base, four starting workers, six minerals
and geyser; each observed one native SCV train, debit and binding. A bridge
restart preserved the finite balance and resource IDs, and a fresh browser
reload recovered five workers without reissuing a train order. The remaining
mask-frame offset and unsupported wall proxies are recorded in the E1 report.
No player gathering or construction transaction is claimed here.

### E2 — Playable mineral and gas gathering

- Add worker command validation and native dispatch; implement contextual target selection and Return Cargo.
- Show balances outside building windows, worker order/cargo, resource amounts and useful rejection feedback.
- Implement depletion/removal and refinery/geyser replacement generations using E0 evidence.
- Ensure workers can be attacked/killed, retargeted, stopped and reassigned without synthetic refunds or grants.
- Prove multiple workers contend for resources natively; bound observation traffic to existing cadence/change publication.

Exit: a human can earn minerals and gas through the browser and spend them on native unit production in the controlled fixture. Preplaced test Refinery is allowed here; ordinary gameplay still awaits E3.

E2 status (2026-11-06): focused authored-fixture gate passed. Native and
graphical browser runs proved two mineral workers, Return Cargo, a worker-built
Refinery, gas delivery, SCV training and same-session browser reload without
another order. Generation-qualified resource selection and live worker/cargo/
resource displays use OpenBW observations. The browser probe uses normal player
actions, but did not certify a literal human mouse sequence. See
`docs/player-economy-e2-verification.md`; ordinary parks remain E4.

### E3 — Native worker construction and bypass closure

- Implement durable reservations, native build intents, incomplete projection, binding, completion, resume and cancellation.
- Convert all supported Terran construction options in economy mode to this path.
- Present native costs/prerequisites and prevent illegal placement or unauthorized edits.
- Gate stock scenery placement, legacy free reinforcement commands and other creation routes server-side. Hiding buttons is insufficient.
- Keep explicit legacy/test creation paths for authored scenarios and fixtures; do not globally remove them.
- Cover actual progress, cancellation refunds, native death, stale target IDs, construction overlap and production egress.

Exit: finite funds govern both buildings and units; no ordinary player action creates free military assets; restart/retry does not duplicate construction or charge twice.

E3 status (2026-11-06): focused authored-fixture exit checks passed for native
funds, server-side finite-mode free-asset gates and no duplicate build/debit
on retry or bridge restart. Durable intents, paired binding, park projection,
incomplete lifecycle, resume/cancel and native refunds were exercised. A flat
authored fixture completed all seven supported Terran building types; a
graphical browser built and recovered a Depot. Ambiguous accepted orders
publish `native_creation_unconfirmed` after 2,400 frames and retain their site
reservation for safety. The remaining fault and release limits are in
`docs/player-economy-e3-verification.md`. This does not complete E4/E5.

### E4 — Ordinary-park generation, waves and cache integration

- Add bounded deterministic base/resource placement and blocked-bootstrap UX.
- Migrate ordinary parks to the economy policy; preserve authored missions.
- Tie initial wave readiness to completed bootstrap, measure playable defense timing, and record any tuning change.
- Update preparation cache identities/materialization and source-save compatibility handling.
- Verify stock maps, a crowded/water-heavy map, a no-base-space map, and a 256x256 map; reuse wave/navigation fixtures where practical.

Exit: normal New Game reaches a playable economy with no manual technical setup; impossible placements fail explicitly; map switches reset the economy once and preserve no prior actors/balances.

### E5 — End-to-end verification and DEV release

- Run offline suite then affected native suites sequentially; run final tests on the integrated revision.
- Complete browser plus native-peer gameplay: mine, deliver, train SCV, build Depot/Barracks, train Marine, build Refinery, gather gas, build Academy and train a gas-cost unit, then encounter a normal wave.
- Exercise reconnect, late join, bridge restart, unauthorized commands, pause/readiness interruption, and switch to another park.
- Check final native/browser sprite states, cargo visuals, resource depletion, construction and clear failure messages.
- Measure Pi memory/swap, preparation/cache-hit time, command latency, resource publication volume and repeated-session cleanup.
- Update docs/protocol/local guidance; write docs/player-economy-verification.md with exact commands, revision, failures, evidence paths and limits.
- Merge after all required gates, use canonical DEV release worker, and verify installed revision plus a deployed economy loop. Keep production/Caddy outside this release.
- Preserve long-run/slow-load failures alongside passing short checks; do not call a direct join proof of successful New Game handoff.

Exit: finite player economy is tested, merged, deployed on DEV and playable through the normal browser entry point.

## 8. Required regression matrix

| Case | Required observable result |
| --- | --- |
| Mining | Native deposit falls and player balance rises only after native delivery; two clients agree |
| Multiple workers | Native collection/return behavior, no duplicated rewards |
| Zero funds / insufficient gas / supply cap | Native rejection, unchanged balances, actionable UI |
| Train worker and defender | One native cost/queue, completion, binding and usable actor |
| Construct every supported Terran building | Native cost/prerequisites/time; no completed createUnit shortcut |
| Cancel / resume / worker death | Native refund or retained incomplete building; no fabricated progress |
| Duplicate/reordered commands / lost ack | At most one native construction/training effect; recoverable result |
| Concurrent site edits | No overlapping native/park buildings or stranded irreversible reservation |
| Mineral depletion / gas exhaustion / Refinery loss | Correct native lifecycle and generation updates, no stale target use |
| Bridge restart / client reconnect | Same native balances, cargo, deposits, queues and buildings; no bootstrap replay |
| Full new session / map switch | Explicit fresh economy, no old bindings/commands/settings leaked |
| Unauthorized client / free spawn / scenery bypass | Authority rejects; read-only state remains usable |
| No base site / blocked approach | Park remains playable, explicit blocked status, no attack backlog |
| Native route/build exploration constraints | No global bypass; fixtures demonstrate real reachable build/delivery paths |
| Ordinary park construction during mining | Confirmed geometry affects native routing safely on both participants |
| Sustained waves plus economy | Combat and resource updates remain consistent; no unbounded actor/link/request growth |

Use scripts/project.sh test, entity-generation checks, relevant existing Barracks/Academy/production/live-construction suites, automatic-wave tests and test-wasm. Add focused test_player_economy_native_live.py and test_player_economy_browser_live.py (names proposed). Keep fault injection in tests.

Behavioral tests should establish native outcomes rather than repeat implementation details. Write regressions before corresponding fixes. Record skipped checks as blocked; do not claim them passed.

## 9. Acceptance and delivery boundaries

The milestone is complete when ordinary-park players can sustain and expand defenses using gathered native resources; build costs cannot be bypassed; resource/building state agrees across native and browser clients; same-session recovery does not grant or duplicate anything; and the final DEV release passes the normal entry flow.

Highest-risk work is native-building projection/collision and recovery, followed by valid economy placement on arbitrary parks. E0 resolves these risks early. Neutral entities and worker rendering are integration work, not evidence that native gathering itself needs to be rewritten.

Planning-only work at this revision: no economy code has been changed, no new live experiments have been run, and no deployment is requested by this document's creation.
