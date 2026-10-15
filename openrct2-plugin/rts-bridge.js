/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const COMMAND_ACTION = "rtsbridge.marineCommand";
    const RESULT_ACTION = "rtsbridge.commandResult";
    const OUTCOME_ACTION = "rtsbridge.worldOutcome";
    const SCENARIO_STATUS_ACTION = "rtsbridge.scenarioStatus";
    const TARGET_ACTION = "rtsbridge.targetCatalog";
    const ACTOR_LIFECYCLE_ACTION = "rtsbridge.actorLifecycle";
    const CLIENT_READY_ACTION = "rtsbridge.clientReady";
    const SPAWN_ACTION = "rtsbridge.spawnMarine";
    const SPAWN_STATUS_ACTION = "rtsbridge.spawnStatus";

    function startWorldAdapter(onCommandSender, onCommandResult, onEntities, onTargets, onActor,
                               onSpawnSender, onSpawnStatus) {
        const session = Array.from({ length: 4 }, function () {
            return Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, "0");
        }).join("");
        let revision = 1, serial = 0, socket = null, buffer = "", inFlight = null, lastCombatSeq = 0, retryTicks = 0;
        let inFlightTicks = 0;
        const queue = [], generations = {}, activeKeys = {}, activeItems = {}, entities = {}, completed = {};
        const constructionActions = {
            ridecreate: true, ridedemolish: true, trackplace: true, trackremove: true,
            trackdesign: true, mazeplacetrack: true, mazesettrack: true,
            rideentranceexitplace: true, rideentranceexitremove: true,
            smallsceneryplace: true, smallsceneryremove: true,
            largesceneryplace: true, largesceneryremove: true,
            wallplace: true, wallremove: true, footpathplace: true,
            footpathlayoutplace: true, footpathremove: true,
            landraise: true, landlower: true, landsetheight: true, landsmooth: true,
            waterraise: true, waterlower: true, watersetheight: true,
            surfacesetstyle: true, tilemodify: true, clearscenery: true
        };
        const CONSTRUCTION_DEBOUNCE_TICKS = 6, RECONCILE_TICKS = 1200;
        const MAX_CHANGE_OPERATIONS = 4096, MAX_CHANGE_BYTES = 4194304;
        let constructionTick = 0, dirtySince = -1, publishedWorld = null, snapshotWorld = null;
        let detectedBatch = null, detectedSignature = "", combatRemovalKey = "", patchInFlight = null;
        const queuedCombatEvents = [];
        let patchSerial = 0;
        function envelope(kind, payload, rev) {
            return { v: 1, kind: kind, session: session, op_id: "park:" + (++serial),
                source: "openrct2", revision: rev || revision, payload: payload };
        }
        function sendNext() {
            if (!socket || inFlight || !queue.length) return;
            inFlight = queue.shift();
            inFlightTicks = 0;
            socket.write(JSON.stringify(inFlight) + "\n");
        }
        function send(kind, payload, rev) { queue.push(envelope(kind, payload, rev)); sendNext(); }
        onCommandSender(function (payload) { send("combat.command", payload); });
        const knownSpawns = {};
        onSpawnSender(function (payload) {
            knownSpawns[payload.request_id] = true;
            send("unit.spawn.request", payload);
        });
        function rotate(offset, direction) {
            if (direction === 1) return { x: offset.y, y: -offset.x };
            if (direction === 2) return { x: -offset.x, y: -offset.y };
            if (direction === 3) return { x: -offset.y, y: offset.x };
            return { x: offset.x, y: offset.y };
        }
        function readPark() {
            const grouped = {}, terrain = [], rides = {};
            map.rides.forEach(function (ride) {
                rides[ride.id] = { ride: ride, cells: [], height: null };
            });
            const largeObjects = typeof objectManager === "object" ? objectManager.getAllObjects("large_scenery") : [];
            const largeByIndex = {};
            largeObjects.forEach(function (object) { largeByIndex[object.index] = object; });
            const names = {};
            if (typeof objectManager === "object") ["small_scenery", "wall", "large_scenery"].forEach(function (kind) {
                names[kind] = {};
                objectManager.getAllObjects(kind).forEach(function (object) { names[kind][object.index] = object.identifier; });
            });
            for (let y = 0; y < map.size.y; ++y) for (let x = 0; x < map.size.x; ++x) {
                const tile = map.getTile(x, y), duplicates = {};
                let ground = null;
                const groundPaths = [];
                for (let n = 0; n < tile.numElements; ++n) {
                    const element = tile.getElement(n), kind = element.type;
                    if (kind === "surface") {
                        ground = { x: x, y: y, height: element.baseZ === undefined
                                ? element.baseHeight * 8 : element.baseZ,
                            slope: Number.isInteger(element.slope) ? element.slope : 0,
                            water: element.waterHeight || 0, surface: element.surfaceObject || 0,
                            walkable: !element.waterHeight };
                        continue;
                    }
                    if (kind === "footpath") groundPaths.push({
                        base_height: element.baseZ === undefined ? element.baseHeight * 8 : element.baseZ,
                        slope_direction: Number.isInteger(element.slopeDirection) ? element.slopeDirection : null
                    });
                    if (kind === "track" || (kind === "entrance" && rides[element.ride])) {
                        if (rides[element.ride]) {
                            rides[element.ride].cells.push({ x: x, y: y });
                            if (rides[element.ride].height === null) rides[element.ride].height = element.baseHeight * 8;
                        }
                        continue;
                    }
                    if (!["small_scenery", "large_scenery", "wall", "footpath"].includes(kind)) continue;
                    const z = element.baseHeight * 8, object = Number.isInteger(element.object) ? element.object : 0;
                    const direction = element.direction || 0, quadrant = element.quadrant || 0;
                    let anchorX = x * 32, anchorY = y * 32, anchorZ = z;
                    if (kind === "large_scenery") {
                        const definition = largeByIndex[object];
                        const part = definition && definition.tiles && definition.tiles[element.sequence];
                        if (part) {
                            const offset = rotate(part.offset, direction);
                            anchorX -= offset.x; anchorY -= offset.y; anchorZ -= part.offset.z;
                        }
                    }
                    const base = kind + ":" + object + ":" + anchorX + ":" + anchorY + ":" + anchorZ
                        + ":" + direction + (kind === "small_scenery" ? ":" + quadrant : "");
                    const occurrence = duplicates[base] || 0; duplicates[base] = occurrence + 1;
                    const key = base + (occurrence ? ":" + occurrence : "");
                    if (!grouped[key]) {
                        const removal = kind === "small_scenery" ? { action: "smallsceneryremove", args: { x: x * 32, y: y * 32, z: z, object: object, quadrant: quadrant } }
                            : kind === "large_scenery" ? { action: "largesceneryremove", args: { x: anchorX, y: anchorY, z: anchorZ, direction: direction, tileIndex: 0 } }
                            : kind === "wall" ? { action: "wallremove", args: { x: x * 32, y: y * 32, z: z, direction: direction } }
                            : { action: "footpathremove", args: { x: x * 32, y: y * 32, z: z } };
                        grouped[key] = { key: key, kind: kind === "footpath" ? "path" : kind,
                            type: kind === "footpath" ? String(element.surfaceObject || object)
                                : ((names[kind] && names[kind][object]) || String(object)),
                            x: anchorX, y: anchorY, z: anchorZ, direction: direction,
                            cells: [], rects: [], removal: removal };
                    }
                    grouped[key].cells.push({ x: x, y: y });
                    // Match Paint.Wall.cpp's tile edges: 0 west, 1 south,
                    // 2 east, 3 north. The rectangle is also OpenBW's mask.
                    if (kind === "wall") grouped[key].rects.push(direction === 0
                        ? { x: x * 32, y: y * 32, width: 4, height: 32 }
                        : direction === 1 ? { x: x * 32, y: y * 32 + 28, width: 32, height: 4 }
                        : direction === 2 ? { x: x * 32 + 28, y: y * 32, width: 4, height: 32 }
                        : { x: x * 32, y: y * 32, width: 32, height: 4 });
                }
                if (ground) {
                    if (groundPaths.length) ground.ground_paths = groundPaths;
                    terrain.push(ground);
                }
            }
            Object.keys(rides).forEach(function (id) {
                const item = rides[id], ride = item.ride;
                if (!item.cells.length) return;
                const kind = ride.classification === "stall" ? "shop" : ride.classification === "facility" ? "facility" : "ride";
                const key = "ride:" + id;
                grouped[key] = { key: key, kind: kind, type: ride.object ? ride.object.identifier : String(ride.type),
                    name: ride.name,
                    x: item.cells[0].x * 32, y: item.cells[0].y * 32, z: item.height || 0, direction: 0,
                    cells: item.cells, rects: [], removal: { action: "ridedemolish", args: { ride: ride.id, modifyType: 0 } },
                    rideId: ride.id, rideType: ride.type };
            });
            return { grouped: grouped, terrain: terrain, rides: rides };
        }
        function discover() {
            const read = readPark(), grouped = read.grouped, terrain = read.terrain;
            const now = {}, result = [];
            Object.keys(grouped).sort().forEach(function (key) {
                const item = grouped[key]; now[key] = true;
                if (!activeKeys[key]) generations[key] = (generations[key] || 0) + 1;
                activeKeys[key] = true;
                const cells = item.cells.filter(function (cell, index, all) {
                    return all.findIndex(function (other) { return other.x === cell.x && other.y === cell.y; }) === index;
                });
                const minX = cells.length ? Math.min.apply(null, cells.map(function (cell) { return cell.x * 32; })) : item.x;
                const minY = cells.length ? Math.min.apply(null, cells.map(function (cell) { return cell.y * 32; })) : item.y;
                const sortedCells = cells.slice().sort(function (a, b) { return a.y - b.y || a.x - b.x; });
                const rects = [];
                sortedCells.forEach(function (cell) {
                    const last = rects[rects.length - 1];
                    if (last && last.y === cell.y * 32 && last.x + last.width === cell.x * 32)
                        last.width += 32;
                    else rects.push({ x: cell.x * 32, y: cell.y * 32, width: 32, height: 32 });
                });
                const id = "openrct2:" + key + "#" + generations[key];
                const entity = { id: id, source: "openrct2", source_id: key, kind: item.kind,
                    type: item.type, owner: 0, position: { x: Math.max(0, minX), y: Math.max(0, minY) },
                    rotation: item.direction || 0, elevation: item.z,
                    geometry: { cells: sortedCells, rects: item.kind === "wall" ? item.rects.slice().sort(function (a, b) {
                        return a.y - b.y || a.x - b.x || a.width - b.width || a.height - b.height;
                    }) : rects },
                    collision: { blocks: item.kind !== "path" },
                    destructible: true,
                    combat: { targetable: item.kind !== "path", health: 100 },
                    removal: item.removal, revision: revision };
                if (item.name) entity.name = item.name;
                item.id = id; item.entity = entity;
                item.activeTarget = !!(entities[id] && entities[id].activeTarget);
                entities[id] = item; activeItems[key] = item; result.push(entity);
            });
            // A ride with no remaining track still owns its native ride ID.
            // Its next track edit must retain the same logical generation.
            Object.keys(read.rides).forEach(function (id) { now["ride:" + id] = true; });
            Object.keys(activeKeys).forEach(function (key) { if (!now[key]) { delete activeKeys[key]; delete activeItems[key]; } });
            terrain.forEach(function (cell) {
                if (cell.ground_paths) cell.ground_paths.sort(function (a, b) {
                    return a.base_height - b.base_height
                        || (a.slope_direction === null ? -1 : a.slope_direction)
                        - (b.slope_direction === null ? -1 : b.slope_direction);
                });
            });
            return { entities: result, terrain: terrain };
        }
        function publishActiveTargets() {
            onTargets(session, Object.keys(entities).filter(function (id) {
                return entities[id].activeTarget === true;
            }).sort().map(function (id) {
                return { id: id, rects: entities[id].entity.geometry.rects };
            }));
        }
        function comparableEntity(entity) {
            return JSON.stringify({ id: entity.id, source_id: entity.source_id, kind: entity.kind,
                type: entity.type, owner: entity.owner, position: entity.position,
                rotation: entity.rotation, elevation: entity.elevation, geometry: entity.geometry,
                collision: entity.collision, destructible: entity.destructible,
                targetable: entity.combat.targetable, armor: entity.combat.armor || 0,
                damage_scale: entity.combat.damage_scale || 0, removal: entity.removal });
        }
        function compareWorld(previous, current) {
            const old = {}, next = {}, additions = [], modifications = [], removals = [], changedTerrain = [];
            previous.entities.forEach(function (entity) { old[entity.id] = entity; });
            current.entities.forEach(function (entity) {
                next[entity.id] = entity;
                if (!old[entity.id]) additions.push(entity);
                else if (comparableEntity(old[entity.id]) !== comparableEntity(entity)) modifications.push(entity);
            });
            Object.keys(old).sort().forEach(function (id) {
                if (!next[id] && id !== combatRemovalKey) removals.push(id);
            });
            const oldTerrain = {};
            previous.terrain.forEach(function (cell) { oldTerrain[cell.x + ":" + cell.y] = JSON.stringify(cell); });
            current.terrain.forEach(function (cell) {
                if (oldTerrain[cell.x + ":" + cell.y] !== JSON.stringify(cell)) changedTerrain.push(cell);
            });
            return { additions: additions, modifications: modifications,
                removals: removals, terrain: changedTerrain };
        }
        function markConstruction() { if (dirtySince < 0) dirtySince = constructionTick; }
        function detectConstruction() {
            if (!publishedWorld) return;
            const current = discover(), changes = compareWorld(publishedWorld, current);
            const operations = changes.additions.length + changes.modifications.length
                + changes.removals.length + changes.terrain.length;
            if (operations > MAX_CHANGE_OPERATIONS || JSON.stringify(changes).length > MAX_CHANGE_BYTES) {
                console.log("WORLD_CHANGESET_OVERFLOW operations=" + operations + " recovery=snapshot");
                detectedBatch = null; detectedSignature = ""; dirtySince = -1;
                snapshot();
                return;
            }
            if (changes.additions.length || changes.modifications.length || changes.removals.length
                || changes.terrain.length) {
                detectedBatch = { base_revision: revision, changes: changes, current: current };
                const signature = JSON.stringify({ base_revision: revision, changes: changes });
                if (signature !== detectedSignature) {
                    detectedSignature = signature;
                    console.log("WORLD_CHANGESET " + JSON.stringify({ base_revision: revision,
                        additions: changes.additions.map(function (e) { return e.id; }),
                        modifications: changes.modifications.map(function (e) { return e.id; }),
                        removals: changes.removals, terrain: changes.terrain.length }));
                }
                if (!patchInFlight && !snapshotWorld) publishPatch(detectedBatch);
            } else { detectedBatch = null; detectedSignature = ""; }
            dirtySince = -1;
        }
        function publishPatch(batch) {
            const nextRevision = revision + 1;
            const stamp = function (entity) {
                const copy = Object.assign({}, entity); copy.revision = nextRevision; return copy;
            };
            const changes = batch.changes;
            const payload = { patch_id: session + ":patch:" + (++patchSerial),
                base_revision: revision, result_revision: nextRevision,
                additions: changes.additions.map(stamp), modifications: changes.modifications.map(stamp),
                removals: changes.removals, terrain: changes.terrain,
                counts: { additions: changes.additions.length, modifications: changes.modifications.length,
                    removals: changes.removals.length, terrain: changes.terrain.length } };
            if (JSON.stringify(payload).length > 900000) {
                console.log("WORLD_CHANGESET_OVERFLOW recovery=snapshot");
                snapshot(); return;
            }
            patchInFlight = { id: payload.patch_id, base: revision, current: batch.current };
            send("world.patch", payload, nextRevision);
        }
        context.subscribe("action.execute", function (event) {
            if (!event || !event.result || event.result.error || event.isClientOnly
                || !constructionActions[event.action]) return;
            const action = event.action, args = event.args || {};
            if (action === "ridedemolish" && args.modifyType === 0 && Number.isInteger(args.ride)) {
                activeKeys["ride:" + args.ride] = false;
            }
            if (action === "ridecreate" && Number.isInteger(event.result.ride)) {
                activeKeys["ride:" + event.result.ride] = false;
            }
            markConstruction();
            const kind = action === "smallsceneryplace" || action === "smallsceneryremove" ? "small_scenery"
                : action === "largesceneryplace" || action === "largesceneryremove" ? "large_scenery"
                : action === "wallplace" || action === "wallremove" ? "wall"
                : action === "footpathplace" || action === "footpathremove" ? "path" : "";
            if (!action.endsWith("remove") || !kind || !Number.isInteger(args.x) || !Number.isInteger(args.y)) return;
            const tileX = Math.floor(args.x / 32), tileY = Math.floor(args.y / 32);
            Object.keys(activeItems).forEach(function (key) {
                const item = activeItems[key];
                if (item.kind === kind && (item.cells.some(function (cell) { return cell.x === tileX && cell.y === tileY; })
                    || (item.removal.args && item.removal.args.x === args.x && item.removal.args.y === args.y)))
                    activeKeys[key] = false;
            });
        });
        function snapshot() {
            const current = discover(), chunks = [];
            snapshotWorld = current;
            onEntities(current.entities, session);
            let entityChunk = [];
            current.entities.forEach(function (entity) {
                const next = entityChunk.concat([entity]);
                if (entityChunk.length && (next.length > 32 || JSON.stringify(next).length > 48000)) {
                    chunks.push({ entities: entityChunk }); entityChunk = [entity];
                } else entityChunk = next;
            });
            if (entityChunk.length) chunks.push({ entities: entityChunk });
            for (let i = 0; i < current.terrain.length; i += 128)
                chunks.push({ terrain: current.terrain.slice(i, i + 128) });
            send("world.snapshot.begin", { width: map.size.x, height: map.size.y, chunks: chunks.length });
            chunks.forEach(function (chunk, index) { chunk.index = index; send("world.snapshot.chunk", chunk); });
            send("world.snapshot.end", { entities: current.entities.length, terrain: current.terrain.length });
            console.log("WORLD_SNAPSHOT session=" + session + " entities=" + current.entities.length
                + " terrain=" + current.terrain.length + " chunks=" + chunks.length);
        }
        function combatEvent(message) {
            const event = message.payload, tracked = entities[event.entity_id];
            if (message.session !== session || !tracked || completed[event.id] || event.health !== 0 || event.type !== "destruction") return;
            const fresh = discover(), present = fresh.entities.filter(function (e) { return e.id === tracked.id; })[0];
            if (!present || JSON.stringify(present.geometry.cells) !== JSON.stringify(tracked.entity.geometry.cells)
                || present.type !== tracked.entity.type || !tracked.removal.action) {
                completed[event.id] = true;
                send("combat.result", { event_id: event.id, entity_id: tracked.id,
                    state: "removal_failed", reason: "identity_changed" });
                return;
            }
            completed[event.id] = true;
            combatRemovalKey = tracked.id;
            context.executeAction(tracked.removal.action, tracked.removal.args, function (result) {
                const remaining = discover().entities.some(function (e) { return e.id === tracked.id; });
                const confirmed = !result.error && !remaining;
                if (confirmed) {
                    revision++;
                    activeKeys[tracked.key] = false;
                    if (publishedWorld) publishedWorld = {
                        entities: publishedWorld.entities.filter(function (entity) { return entity.id !== tracked.id; }),
                        terrain: publishedWorld.terrain
                    };
                }
                combatRemovalKey = "";
                send("combat.result", { event_id: event.id, entity_id: tracked.id,
                    state: confirmed ? "removal_confirmed" : "removal_failed",
                    reason: confirmed ? "" : (result.errorMessage || "object_still_present") }, revision);
                console.log("WORLD_REMOVAL id=" + tracked.id + " state=" + (confirmed ? "confirmed" : "failed"));
            });
        }
        function onLine(line) {
            let message; try { message = JSON.parse(line); } catch (_) { return; }
            if (!message || message.v !== 1 || message.session !== session) return;
            if (message.kind === "world.ack") {
                if (!inFlight || message.payload.op_id !== inFlight.op_id) return;
                if (!message.payload.accepted) {
                    if (inFlight.kind === "combat.command") {
                        onCommandResult({ command_id: inFlight.payload.command_id,
                            player_id: inFlight.payload.player_id, request_id: inFlight.payload.request_id,
                            accepted: false, reason: message.payload.error || "command_rejected" });
                        inFlight = null; sendNext(); return;
                    }
                    if (inFlight.kind === "unit.spawn.request") {
                        delete knownSpawns[inFlight.payload.request_id];
                        onSpawnStatus({ request_id: inFlight.payload.request_id, state: "rejected",
                            reason: message.payload.error || "spawn_rejected", units: [] });
                        inFlight = null; sendNext(); return;
                    }
                    if (inFlight.kind === "unit.spawn.query" || inFlight.kind === "unit.spawn.cancel") {
                        onSpawnStatus({ request_id: inFlight.payload.request_id, state: "uncertain",
                            reason: message.payload.error || "status_unavailable", units: [] });
                        inFlight = null; sendNext(); return;
                    }
                    console.log("WORLD_ERROR " + message.payload.error); socket.destroy({}); return;
                }
                if (inFlight.kind === "world.snapshot.end" && snapshotWorld) {
                    publishedWorld = snapshotWorld;
                    snapshotWorld = null;
                    if (dirtySince >= 0) markConstruction();
                }
                inFlight = null; sendNext();
            } else if (message.kind === "world.resync") {
                queue.length = 0; inFlight = null; patchInFlight = null; snapshot();
            }
            else if (message.kind === "world.patch.status" && message.payload && patchInFlight
                && message.payload.patch_id === patchInFlight.id) {
                if (message.payload.state === "synchronized" && message.revision === patchInFlight.base + 1) {
                    publishedWorld = patchInFlight.current;
                    revision = message.revision;
                    patchInFlight = null;
                    detectedSignature = "";
                    publishActiveTargets();
                    markConstruction();
                    while (queuedCombatEvents.length) combatEvent(queuedCombatEvents.shift());
                    console.log("WORLD_PATCH_SYNC revision=" + revision);
                } else if (message.payload.state === "failed" || message.payload.state === "unsynchronized") {
                    console.log("WORLD_PATCH_ERROR " + (message.payload.reason || message.payload.state));
                    queue.length = 0; inFlight = null; patchInFlight = null; snapshot();
                }
            }
            else if (message.kind === "combat.event") {
                if (patchInFlight || snapshotWorld) queuedCombatEvents.push(message);
                else combatEvent(message);
            }
            else if (message.kind === "combat.result" && message.payload.command_id) onCommandResult(message.payload);
            else if (message.kind === "unit.spawn.status" && message.payload) onSpawnStatus(message.payload);
            else if (message.kind === "combat.snapshot") {
                const state = message.payload;
                if (!state || !Number.isSafeInteger(state.seq) || state.seq <= lastCombatSeq
                    || !validAction({ session: session, seq: state.seq, units: state.units })) return;
                lastCombatSeq = state.seq;
                context.executeAction(ACTION, { session: session, seq: state.seq, units: state.units },
                    function (result) { if (result.error) console.log("WORLD_RENDER_ERROR " + result.errorMessage); });
            }
            else if (message.kind === "actor.bind" || message.kind === "actor.despawn") {
                const actor = message.payload || {};
                onActor(session, actor.id, actor.generation,
                    message.kind === "actor.bind" ? "active" : "removed");
            }
            else if (message.kind === "world.ready") {
                lastCombatSeq = 0;
                const targets = (message.payload.target_ids || []).map(function (id) {
                    const item = entities[id];
                    return item ? { id: id, rects: item.entity.geometry.rects } : null;
                }).filter(function (item) { return item !== null; });
                Object.keys(entities).forEach(function (id) { entities[id].activeTarget = false; });
                targets.forEach(function (item) { entities[item.id].activeTarget = true; });
                onTargets(session, targets);
                console.log("WORLD_READY entities=" + message.payload.entities
                    + " targets=" + message.payload.targets + " obstacles=" + message.payload.obstacles
                    + " navigation=" + message.payload.navigation
                    + " unsupported=" + (message.payload.unsupported_total || 0));
                Object.keys(knownSpawns).forEach(function (requestId) {
                    send("unit.spawn.query", { request_id: requestId });
                });
            }
            else if (message.kind === "world.outcome" && message.payload
                && ["victory", "defeat"].includes(message.payload.state))
                context.executeAction(OUTCOME_ACTION, { session: session,
                    scenario_id: message.payload.scenario_id, state: message.payload.state,
                    objective_id: message.payload.objective_id }, function (result) {
                    if (result.error) console.log("WORLD_OUTCOME_ERROR " + result.errorMessage);
                });
            else if (message.kind === "scenario.status" && message.payload)
                context.executeAction(SCENARIO_STATUS_ACTION, message.payload, function (result) {
                    if (result.error) console.log("WORLD_SCENARIO_STATUS_ERROR " + result.errorMessage);
                });
            else if (message.kind === "entity.remove") {
                const removed = message.payload && message.payload.id;
                if (entities[removed]) entities[removed].activeTarget = false;
                if (typeof removed === "string") publishActiveTargets();
            }
            else if (message.kind === "entity.target") {
                const target = message.payload || {};
                if (entities[target.id] && typeof target.proxy_id === "string") {
                    entities[target.id].activeTarget = true;
                    publishActiveTargets();
                }
            }
            else if (message.kind === "world.error")
                console.log("WORLD_NOT_READY " + message.payload.reason);
        }
        function connect() {
            if (socket) return;
            const connection = network.createSocket(); socket = connection; buffer = "";
            connection.on("data", function (data) {
                buffer += data; if (buffer.length > 1048576) { connection.destroy({}); return; }
                let newline; while ((newline = buffer.indexOf("\n")) !== -1) {
                    onLine(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1);
                }
            });
            connection.on("error", function (error) { console.log("WORLD_SOCKET_ERROR " + error); if (socket === connection) socket = null; connection.destroy({}); });
            connection.on("close", function () { if (socket === connection) socket = null; inFlight = null; queue.length = 0; });
            connection.connect(40010, "127.0.0.1", function () {
                retryTicks = 0;
                patchInFlight = null;
                send("world.hello", { capabilities: ["snapshot", "world.patch", "navigation.mask"] });
                snapshot();
            });
        }
        connect();
        context.subscribe("interval.tick", function () {
            constructionTick++;
            if (!socket && ++retryTicks >= 40) { retryTicks = 0; connect(); }
            if (socket && inFlight && inFlight.kind === "world.patch" && ++inFlightTicks >= 120) {
                inFlightTicks = 0;
                socket.write(JSON.stringify(inFlight) + "\n");
            }
            if (socket && patchInFlight && !inFlight && constructionTick % 120 === 0)
                send("world.patch.query", { patch_id: patchInFlight.id }, patchInFlight.base + 1);
            if (dirtySince >= 0 && constructionTick - dirtySince >= CONSTRUCTION_DEBOUNCE_TICKS
                && !snapshotWorld) detectConstruction();
            else if (dirtySince < 0 && constructionTick % RECONCILE_TICKS === 0
                && !snapshotWorld) detectConstruction();
        });
    }

    function validAction(args) {
        if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
            || !Number.isSafeInteger(args.seq) || args.seq < 1 || !Array.isArray(args.units)
            || args.units.length > 256) {
            return false;
        }
        const ids = {};
        return args.units.every(function (unit) {
            if (!unit || typeof unit.id !== "string" || unit.id.length > 32
                || !/^openbw:[0-9]+$/.test(unit.id) || ids[unit.id]) return false;
            ids[unit.id] = true;
            return Number.isInteger(unit.x) && Number.isInteger(unit.y)
                && unit.x >= 0 && unit.y >= 0
                && unit.x < map.size.x * 32 && unit.y < map.size.y * 32
                && Number.isInteger(unit.facing) && unit.facing >= 0 && unit.facing <= 255
                && (unit.motion === "idle" || unit.motion === "walk" || unit.motion === "attack" || unit.motion === "death")
                && ((unit.kind === "zerg_zergling" || unit.kind === "terran_marine")
                    && Number.isInteger(unit.owner) && unit.owner >= 0 && unit.owner <= 11
                    && Number.isInteger(unit.hp) && unit.hp >= 0
                    && Number.isInteger(unit.max_hp) && unit.max_hp >= unit.hp && unit.max_hp <= 10000
                    && Number.isInteger(unit.attack_frames) && unit.attack_frames >= 0);
        });
    }

    function main() {
        if (typeof rtsBridge !== "object" || rtsBridge.version !== 4 || rtsBridge.assetVersion !== 3
            || typeof rtsBridge.applySnapshot !== "function"
            || typeof rtsBridge.invalidateAnimation !== "function") {
            throw new Error("RTS Bridge needs the matching native OpenRCT2 build and asset pack");
        }

        let controlSession = "";
        let controlUnits = {};
        let actorLifecycleSession = "";
        let activeActorGenerations = {};
        let removedActorGenerations = {};
        const retiredActorSessions = {};
        let clientReadySession = "";
        let clientReadyPending = false;
        let pendingClientRefresh = false;
        let onActorRemoved = function () {};
        let terranOwner = -1;
        let commanderPlayer = -1;
        let commandSerial = 0;
        let worldCommandSender = null;
        let worldSpawnSender = null;
        let spawnFeedback = "";
        const spawnStatuses = {};
        let worldTargetIds = {};
        let targetCatalogSession = "";
        let targetCatalogVersion = 0;
        let pendingTargetCatalog = null;
        let publishingTargetVersion = 0;
        let publishingTargetSession = "";
        const retiredTargetSessions = {};
        let publishedTargets = [];
        function publishTargetCatalog(session, targets) {
            if (session !== publishingTargetSession) {
                publishingTargetSession = session;
                publishingTargetVersion = 0;
            }
            publishedTargets = targets.slice();
            const chunks = [];
            let chunk = [];
            targets.forEach(function (target) {
                const next = chunk.concat([target]);
                if (chunk.length && (next.length > 128 || JSON.stringify(next).length > 48000)) {
                    chunks.push(chunk); chunk = [target];
                } else chunk = next;
            });
            if (chunk.length || !chunks.length) chunks.push(chunk);
            if (chunks.length > 512) {
                console.log("WORLD_TARGET_CATALOG_ERROR too_many_chunks");
                return;
            }
            const version = publishingTargetVersion = Math.max(publishingTargetVersion,
                session === targetCatalogSession ? targetCatalogVersion : 0) + 1;
            chunks.forEach(function (items, index) {
                context.executeAction(TARGET_ACTION, { session: session, version: version,
                    index: index, chunks: chunks.length, targets: items }, function (result) {
                    if (result.error) console.log("WORLD_TARGET_CATALOG_ERROR " + result.errorMessage);
                });
            });
        }
        function publishActorLifecycle(session, id, generation, state) {
            context.executeAction(ACTOR_LIFECYCLE_ACTION, { session: session, id: id,
                generation: generation, state: state }, function (result) {
                if (result.error) console.log("WORLD_ACTOR_LIFECYCLE_ERROR " + result.errorMessage);
            });
        }
        let outcomeState = null;
        let missionStatus = null;
        let shownOutcome = "";
        let commandFeedback = "";
        const pendingCommands = {};
        context.registerAction(SPAWN_STATUS_ACTION, function (event) {
            const args = event.args || {};
            if (network.mode === "server" && event.player !== network.currentPlayer.id)
                return { error: 1, errorMessage: "Only the server may report spawn status" };
            if (args.session !== controlSession || typeof args.request_id !== "string"
                || !/^[a-zA-Z0-9_.:/#-]{1,128}$/.test(args.request_id)
                || !["queued", "issued", "created", "ready", "rejected", "failed", "uncertain"].includes(args.state)
                || typeof args.reason !== "string" || args.reason.length > 128
                || !Array.isArray(args.units) || args.units.length > 5
                || !args.units.every(function (unit) {
                    return unit && Number.isInteger(unit.index) && unit.index >= 0 && unit.index < 5
                        && ["queued", "issued", "created", "ready", "rejected", "failed", "uncertain"].includes(unit.state)
                        && (!unit.actor_id || /^openbw:[0-9]+$/.test(unit.actor_id));
                })) return { error: 1, errorMessage: "Invalid spawn status" };
            return {};
        }, function (event) {
            const args = event.args;
            spawnStatuses[args.request_id] = args;
            const ready = args.units.filter(function (unit) { return unit.state === "ready"; });
            const failure = args.units.filter(function (unit) {
                return (unit.state === "failed" || unit.state === "rejected") && unit.reason;
            })[0];
            const reason = args.reason || (failure ? failure.reason : "");
            spawnFeedback = args.state === "ready" && ready.length ? ready.length + " Marines ready ("
                + ready[0].actor_id + " to " + ready[ready.length - 1].actor_id + ")"
                : "Spawn " + args.state + (reason ? ": " + reason : "")
                + (args.units.length ? " (" + ready.length + "/" + args.units.length + " ready)" : "");
            console.log("WORLD_SPAWN_STATUS request=" + args.request_id + " state=" + args.state
                + " ready=" + ready.length + " ids=" + ready.map(function (unit) { return unit.actor_id; }).join(","));
            return {};
        });
        context.registerAction(ACTION, function (event) {
            if (network.mode === "server" && event.player !== network.currentPlayer.id) {
                return { error: 1, errorMessage: "Only the RTS bridge server may publish snapshots" };
            }
            return validAction(event.args) ? {} : { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
        }, function (event) {
            if (!validAction(event.args)) return { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
            const visible = event.args.units.filter(function (unit) {
                const number = /^openbw:([0-9]+)$/.exec(unit.id);
                return !number || Number(number[1]) < 3000
                    || (actorLifecycleSession === event.args.session
                        && activeActorGenerations[unit.id] > 0);
            });
            rtsBridge.applySnapshot({ session: event.args.session, seq: event.args.seq, units: visible });
            if (controlSession !== event.args.session) {
                outcomeState = null; shownOutcome = "";
                if (missionStatus && missionStatus.session !== event.args.session) missionStatus = null;
            }
            controlSession = event.args.session;
            controlUnits = {};
            visible.forEach(function (unit) { controlUnits[unit.id] = unit; });
            const marine = event.args.units.filter(function (unit) { return unit.kind === "terran_marine"; })[0];
            if (marine) terranOwner = marine.owner;
            return {};
        });


            context.registerAction(CLIENT_READY_ACTION, function (event) {
                const args = event.args;
                if (!args || args.session !== controlSession || (network.mode === "server"
                    && (!Array.isArray(network.players)
                        || !network.players.some(function (player) { return player.id === event.player; }))))
                    return { error: 1, errorMessage: "Invalid client readiness" };
                return {};
            }, function () {
                if (network.mode === "server") pendingClientRefresh = true;
                return {};
            });
            context.registerAction(ACTOR_LIFECYCLE_ACTION, function (event) {
                const args = event.args;
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may publish actor lifecycle" };
                if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
                    || !/^openbw:[0-9]+$/.test(args.id)
                    || !Number.isSafeInteger(args.generation) || args.generation < 1
                    || !["active", "removed"].includes(args.state)
                    || retiredActorSessions[args.session]
                    || (actorLifecycleSession === args.session
                        && removedActorGenerations[args.id] !== undefined
                        && (args.state === "active"
                            || removedActorGenerations[args.id] !== args.generation))
                    || (actorLifecycleSession === args.session
                        && activeActorGenerations[args.id] !== undefined
                        && activeActorGenerations[args.id] !== args.generation))
                    return { error: 1, errorMessage: "Invalid actor lifecycle" };
                return {};
            }, function (event) {
                const args = event.args;
                if (actorLifecycleSession !== args.session) {
                    if (actorLifecycleSession) retiredActorSessions[actorLifecycleSession] = true;
                    actorLifecycleSession = args.session;
                    activeActorGenerations = {};
                    removedActorGenerations = {};
                }
                if (args.state === "removed") {
                    delete activeActorGenerations[args.id];
                    removedActorGenerations[args.id] = args.generation;
                    delete controlUnits[args.id];
                    onActorRemoved(args.id);
                } else activeActorGenerations[args.id] = args.generation;
                console.log("WORLD_ACTOR_LIFECYCLE id=" + args.id + " state=" + args.state
                    + " generation=" + args.generation);
                return {};
            });
            context.registerAction(TARGET_ACTION, function (event) {
                const args = event.args;
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may publish structure targets" };
                if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
                    || !Number.isSafeInteger(args.version) || args.version < 1
                    || !Number.isInteger(args.index) || args.index < 0
                    || !Number.isInteger(args.chunks) || args.chunks < 1 || args.chunks > 512
                    || args.index >= args.chunks
                    || !Array.isArray(args.targets) || args.targets.length > 128
                    || (args.targets.length === 0 && (args.chunks !== 1 || args.index !== 0))
                    || !args.targets.every(function (item) {
                        return item && typeof item.id === "string" && item.id.length <= 256
                            && /^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(item.id)
                            && Array.isArray(item.rects) && item.rects.length > 0 && item.rects.length <= 8192
                            && item.rects.every(function (rect) {
                                return Number.isInteger(rect.x) && Number.isInteger(rect.y)
                                    && Number.isInteger(rect.width) && Number.isInteger(rect.height)
                                    && rect.x >= 0 && rect.y >= 0 && rect.width > 0 && rect.height > 0
                                    && rect.x + rect.width <= map.size.x * 32
                                    && rect.y + rect.height <= map.size.y * 32;
                            });
                    })) return { error: 1, errorMessage: "Invalid structure target catalog" };
                if (retiredTargetSessions[args.session]
                    || (args.session !== targetCatalogSession && args.index !== 0
                        && (!pendingTargetCatalog || pendingTargetCatalog.session !== args.session))
                    || (args.session === targetCatalogSession && args.version <= targetCatalogVersion))
                    return { error: 1, errorMessage: "Stale structure target catalog" };
                if (args.session === targetCatalogSession && pendingTargetCatalog
                    && args.version <= pendingTargetCatalog.version && args.index === 0)
                    return { error: 1, errorMessage: "Duplicate structure target catalog" };
                if (args.session === targetCatalogSession && pendingTargetCatalog
                    && args.version < pendingTargetCatalog.version)
                    return { error: 1, errorMessage: "Stale structure target catalog" };
                if (args.index !== 0 && (!pendingTargetCatalog
                    || pendingTargetCatalog.session !== args.session
                    || pendingTargetCatalog.version !== args.version
                    || pendingTargetCatalog.chunks !== args.chunks
                    || pendingTargetCatalog.next !== args.index))
                    return { error: 1, errorMessage: "Incomplete structure target catalog" };
                const existing = args.index === 0 ? {} : pendingTargetCatalog.targets;
                const seen = {};
                if (args.targets.some(function (item) {
                    if (seen[item.id] || Object.prototype.hasOwnProperty.call(existing, item.id)) return true;
                    seen[item.id] = true; return false;
                })) return { error: 1, errorMessage: "Duplicate structure target" };
                return {};
            }, function (event) {
                const args = event.args;
                if (args.index === 0) {
                    if (targetCatalogSession && targetCatalogSession !== args.session)
                        retiredTargetSessions[targetCatalogSession] = true;
                    pendingTargetCatalog = { session: args.session, version: args.version,
                        chunks: args.chunks, next: 0, targets: {} };
                }
                args.targets.forEach(function (item) {
                    pendingTargetCatalog.targets[item.id] = { geometry: { rects: item.rects } };
                });
                pendingTargetCatalog.next++;
                if (pendingTargetCatalog.next === pendingTargetCatalog.chunks) {
                    targetCatalogSession = args.session;
                    targetCatalogVersion = args.version;
                    worldTargetIds = pendingTargetCatalog.targets;
                    pendingTargetCatalog = null;
                    if (network.mode === "server") console.log("WORLD_TARGET_CATALOG session="
                        + targetCatalogSession + " version=" + targetCatalogVersion
                        + " targets=" + Object.keys(worldTargetIds).length);
                }
                return {};
            });
            context.registerAction(OUTCOME_ACTION, function (event) {
                const args = event.args;
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report battle outcomes" };
                return args && args.session === controlSession
                    && typeof args.scenario_id === "string" && /^[a-z0-9-]{1,64}$/.test(args.scenario_id)
                    && ["victory", "defeat"].includes(args.state)
                    && typeof args.objective_id === "string" && args.objective_id.length > 0
                    ? {} : { error: 1, errorMessage: "Invalid battle outcome" };
            }, function (event) {
                outcomeState = event.args.state;
                return {};
            });
            context.registerAction(SCENARIO_STATUS_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report scenario status" };
                if (!/^[0-9a-f]{32}$/.test(args.session || "")
                    || !/^[a-zA-Z0-9_.:/#-]{1,128}$/.test(args.scenario_id || "")
                    || typeof args.display_name !== "string" || args.display_name.length > 128
                    || typeof args.objective !== "string" || args.objective.length > 256
                    || !Number.isInteger(args.wave_ordinal) || args.wave_ordinal < 0 || args.wave_ordinal > 64
                    || !Number.isInteger(args.wave_total) || args.wave_total < 0 || args.wave_total > 64
                    || !["", "pending", "triggered", "spawning", "active", "cleared", "failed"].includes(args.wave_state)
                    || !["", "victory", "defeat"].includes(args.outcome)
                    || typeof args.error !== "string" || args.error.length > 256)
                    return { error: 1, errorMessage: "Invalid scenario status" };
                return {};
            }, function (event) {
                missionStatus = event.args;
                if (missionStatus.outcome) outcomeState = missionStatus.outcome;
                console.log("WORLD_SCENARIO_STATUS scenario=" + missionStatus.scenario_id
                    + " wave=" + missionStatus.wave_ordinal + "/" + missionStatus.wave_total
                    + " state=" + missionStatus.wave_state + " outcome=" + missionStatus.outcome);
                return {};
            });
            context.registerAction(COMMAND_ACTION, function (event) {
                const args = event.args;
                if (outcomeState) return { error: 1, errorMessage: "Battle has ended" };
                if (network.mode === "server" && (!Array.isArray(network.players)
                    || !network.players.some(function (player) { return player.id === event.player; })))
                    return { error: 1, errorMessage: "Player is not connected" };
                if (network.mode === "server") {
                    const connected = network.players.map(function (player) { return player.id; });
                    if (!connected.includes(commanderPlayer)) commanderPlayer = -1;
                    if (commanderPlayer < 0) {
                        const clients = connected.filter(function (id) { return id !== network.currentPlayer.id; }).sort(function (a, b) { return a - b; });
                        commanderPlayer = clients.length ? clients[0] : network.currentPlayer.id;
                    }
                    if (event.player !== commanderPlayer)
                        return { error: 1, errorMessage: "Only the Terran commander may order Marines" };
                }
                if (!args || args.session !== controlSession || !Number.isSafeInteger(args.request)
                    || args.request < 1 || !Array.isArray(args.unit_ids) || args.unit_ids.length < 1
                    || args.unit_ids.length > (32) || !(["move", "attack", "attack_move", "hold", "stop"].includes(args.verb)))
                    return { error: 1, errorMessage: "Invalid Marine command" };
                const unique = {};
                if (!args.unit_ids.every(function (id) {
                    const unit = controlUnits[id];
                    if (!unit || unique[id] || unit.kind !== "terran_marine"
                        || unit.owner !== terranOwner || unit.hp <= 0) return false;
                    unique[id] = true;
                    return true;
                })) return { error: 1, errorMessage: "Marine is unavailable" };
                if ((args.verb === "move" || args.verb === "attack_move")
                    && (!Number.isInteger(args.x) || !Number.isInteger(args.y)
                    || args.x < 0 || args.y < 0 || args.x >= map.size.x * 32 || args.y >= map.size.y * 32))
                    return { error: 1, errorMessage: "Invalid destination" };
                if (args.verb === "attack") {
                    const target = controlUnits[args.target_id];
                    const structure = typeof args.target_entity_id === "string"
                        && /^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(args.target_entity_id)
                        && targetCatalogSession === args.session && worldTargetIds[args.target_entity_id];
                    if ((!target || target.kind !== "zerg_zergling" || target.hp <= 0) && !structure)
                        return { error: 1, errorMessage: "Invalid attack target" };
                }
                if (network.mode === "server" && !(worldCommandSender))
                    return { error: 1, errorMessage: "Terran controller disconnected" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;

                    const commandId = args.session + ":" + (++commandSerial);
                    pendingCommands[commandId] = { player: event.player, request: args.request,
                        unit: args.unit_ids[0] };
                    const payload = { command_id: commandId, player_id: event.player,
                        request_id: args.request, unit_ids: args.unit_ids.slice(), verb: "unit." + args.verb };
                    if (args.verb === "move" || args.verb === "attack_move") {
                        payload.x = args.x; payload.y = args.y;
                    } else if (args.verb === "attack")
                        payload.target_id = args.target_entity_id || args.target_id;
                    worldCommandSender(payload);
                    return {};
            });
            context.registerAction(SPAWN_ACTION, function (event) {
                const args = event.args || {};
                if (outcomeState) return { error: 1, errorMessage: "Battle has ended" };
                if (!Array.isArray(network.players) || !network.players.some(function (player) {
                    return player.id === event.player;
                })) return { error: 1, errorMessage: "Player is not connected" };
                if (network.mode === "server") {
                    const connected = network.players.map(function (player) { return player.id; });
                    if (!connected.includes(commanderPlayer)) commanderPlayer = -1;
                    if (commanderPlayer < 0) {
                        const clients = connected.filter(function (id) { return id !== network.currentPlayer.id; })
                            .sort(function (a, b) { return a - b; });
                        commanderPlayer = clients.length ? clients[0] : network.currentPlayer.id;
                    }
                    if (event.player !== commanderPlayer)
                        return { error: 1, errorMessage: "Only the Terran commander may spawn Marines" };
                    if (!worldSpawnSender)
                        return { error: 1, errorMessage: "Spawn bridge disconnected" };
                }
                if (args.session !== controlSession || typeof args.request_id !== "string"
                    || !/^[a-zA-Z0-9_.:/#-]{1,128}$/.test(args.request_id)
                    || !Number.isInteger(args.count) || args.count < 1 || args.count > 5
                    || !Number.isInteger(args.x) || !Number.isInteger(args.y)
                    || args.x < 0 || args.y < 0 || args.x >= map.size.x * 32 || args.y >= map.size.y * 32)
                    return { error: 1, errorMessage: "Invalid Marine spawn location or count" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;
                worldSpawnSender({ request_id: args.request_id, unit_type: "terran_marine",
                    count: args.count, x: args.x, y: args.y, formation: "compact",
                    player_id: event.player });
                return {};
            });
            context.registerAction(RESULT_ACTION, function (event) {
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server can report Marine commands" };
                const args = event.args;
                return args && Number.isSafeInteger(args.player) && Number.isSafeInteger(args.request)
                    && /^openbw:[0-9]+$/.test(args.unit) && typeof args.accepted === "boolean"
                    && /^[a-z_]{2,64}$/.test(args.reason)
                    ? {} : { error: 1, errorMessage: "Invalid Marine command result" };
            }, function (event) {
                const args = event.args;
                if (args.player === network.currentPlayer.id) {
                    commandFeedback = args.accepted ? "Order " + args.request + " accepted"
                        : "Order " + args.request + " rejected: " + args.reason;
                    console.log("RTS Bridge Marine command request=" + args.request + " unit=" + args.unit
                        + " accepted=" + args.accepted + " reason=" + args.reason);
                }
                return {};
            });


        let animationTicks = 0;
        let cameraSession = "";
        context.subscribe("interval.tick", function () {
            if (++animationTicks % 4 === 0) rtsBridge.invalidateAnimation();
            if (network.mode === "server" && pendingClientRefresh) {
                pendingClientRefresh = false;
                if (publishingTargetSession) publishTargetCatalog(publishingTargetSession, publishedTargets);
                if (actorLifecycleSession) Object.keys(activeActorGenerations).forEach(function (id) {
                    publishActorLifecycle(actorLifecycleSession, id, activeActorGenerations[id], "active");
                });
                Object.keys(spawnStatuses).forEach(function (id) {
                    const status = spawnStatuses[id];
                    if (status.session === controlSession)
                        context.executeAction(SPAWN_STATUS_ACTION, status, function () {});
                });
                if (missionStatus && missionStatus.session === controlSession)
                    context.executeAction(SCENARIO_STATUS_ACTION, missionStatus, function () {});
            }
            if (network.mode === "client" && controlSession
                && clientReadySession !== controlSession && !clientReadyPending
                && animationTicks % 40 === 0) {
                clientReadyPending = true;
                context.executeAction(CLIENT_READY_ACTION, { session: controlSession }, function (result) {
                    clientReadyPending = false;
                    if (!result.error) clientReadySession = controlSession;
                });
            }
            if (network.mode === "client" && controlSession
                && cameraSession !== controlSession && typeof ui !== "undefined" && ui.mainViewport) {
                ui.mainViewport.zoom = 1;
                ui.mainViewport.moveTo({ x: map.size.x * 16, y: map.size.y * 16 });
                cameraSession = controlSession;
            }
        });

        if (typeof ui !== "undefined") {
            let selected = [];
            let highlightedTiles = "";
            let nextRequest = 0;
            let selectingMultiple = false;
            let selectionSession = "";
            let dragStart = null;
            let dragEnd = null;
            let attackMove = false;
            let spawnMode = false;
            let spawnPreview = null;
            let spawnCount = 5;
            let nextSpawnRequest = 0;
            const controlGroups = {};
            const squadWindow = ui.openWindow({ classification: "starcoaster-squad",
                width: 248, height: 164, title: "Frontier Outpost", widgets: [
                    { type: "label", name: "selection", x: 8, y: 19, width: 232, height: 14,
                        text: "Waiting for battlefield" },
                    { type: "label", x: 8, y: 38, width: 232, height: 14,
                        text: "Drag select | A attack move | H hold | S stop" },
                    { type: "label", name: "objective", x: 8, y: 57, width: 232, height: 14,
                        text: "Defend Frontier Carousel" },
                    { type: "label", name: "command", x: 8, y: 75, width: 232, height: 14,
                        text: "Select Marines to issue orders" },
                    { type: "dropdown", name: "spawn-count", x: 8, y: 96, width: 72, height: 14,
                        items: ["1 Marine", "2 Marines", "3 Marines", "4 Marines", "5 Marines"],
                        selectedIndex: 4, onChange: function (index) { spawnCount = index + 1; } },
                    { type: "button", name: "spawn-mode", x: 88, y: 94, width: 152, height: 20,
                        text: "Spawn Marine", onClick: function () { activateSpawnTool(); } },
                    { type: "button", name: "select-mode", x: 8, y: 119, width: 72, height: 20,
                        text: "Select", onClick: function () { ui.activateTool(marineSelectionTool); } },
                    { type: "label", name: "spawn-status", x: 88, y: 121, width: 152, height: 14,
                        text: "Call in reinforcements" },
                    { type: "label", name: "spawn-detail", x: 8, y: 144, width: 232, height: 14,
                        text: "Click Spawn Marine, then a clear tile" }
                ] });
            function pointFrom(event) { return event.mapCoords || rtsBridge.cursorWorld(); }
            function refreshSelection() {
                if (selectionSession !== controlSession) {
                    selectionSession = controlSession; selected = [];
                    Object.keys(controlGroups).forEach(function (number) { delete controlGroups[number]; });
                    commandFeedback = "";
                    spawnFeedback = "";
                }
                selected = selected.filter(function (id) {
                    const unit = controlUnits[id];
                    return unit && unit.kind === "terran_marine" && unit.hp > 0;
                });
                Object.keys(controlGroups).forEach(function (number) {
                    controlGroups[number] = controlGroups[number].filter(function (id) {
                        const unit = controlUnits[id];
                        return unit && unit.kind === "terran_marine" && unit.hp > 0;
                    });
                });

                    const tiles = spawnMode && spawnPreview ? [spawnPreview] : selected.map(function (id) {
                        const unit = controlUnits[id];
                        return { x: Math.floor(unit.x / 32) * 32, y: Math.floor(unit.y / 32) * 32 };
                    });
                    const key = JSON.stringify(tiles);
                    if (key !== highlightedTiles) {
                        ui.tileSelection.tiles = tiles;
                        highlightedTiles = key;
                    }

                if (squadWindow) {
                    if (missionStatus && missionStatus.session === controlSession)
                        squadWindow.title = missionStatus.display_name;
                    const info = squadWindow.findWidget("selection");
                    if (info) info.text = selected.length + " Marine" + (selected.length === 1 ? "" : "s")
                        + " selected" + (selected.length === 1 ? " | HP " + controlUnits[selected[0]].hp : "");
                    const objective = squadWindow.findWidget("objective");
                    if (objective) objective.text = missionStatus && missionStatus.session === controlSession
                        ? (missionStatus.error ? "Wave error: " + missionStatus.error
                            : missionStatus.outcome === "victory" ? "Victory: " + missionStatus.objective
                            : missionStatus.outcome === "defeat" ? "Defeat: " + missionStatus.objective
                            : missionStatus.objective + (missionStatus.wave_total
                                ? " | Wave " + missionStatus.wave_ordinal + "/" + missionStatus.wave_total : ""))
                        : "Waiting for mission status";
                    const command = squadWindow.findWidget("command");
                    if (command) command.text = commandFeedback || "Select Marines to issue orders";
                    const status = squadWindow.findWidget("spawn-status");
                    if (status) status.text = spawnMode ? "Place " + spawnCount + " Marine" + (spawnCount === 1 ? "" : "s")
                        : spawnFeedback || "Call in reinforcements";
                }
                if (outcomeState && shownOutcome !== controlSession + ":" + outcomeState) {
                    shownOutcome = controlSession + ":" + outcomeState;
                    ui.showError(missionStatus ? missionStatus.display_name : "Scenario", outcomeState === "victory"
                        ? "Victory! " + (missionStatus ? missionStatus.objective : "Objective defended")
                        : "Defeat! " + (missionStatus ? missionStatus.objective : "Objective lost"));
                }
            }
            onActorRemoved = function (id) {
                selected = selected.filter(function (entry) { return entry !== id; });
                Object.keys(controlGroups).forEach(function (number) {
                    controlGroups[number] = controlGroups[number].filter(function (entry) { return entry !== id; });
                });
                refreshSelection();
            };
            context.subscribe("interval.tick", refreshSelection);
            function chooseAt(point, shift) {
                refreshSelection();
                const id = point && rtsBridge.hitTest(point.x, point.y, 48);
                const unit = id && controlUnits[id];
                if (!unit || unit.kind !== "terran_marine" || unit.hp <= 0) {
                    if (!shift && !selectingMultiple) selected = [];
                    return;
                }
                if (shift || selectingMultiple) {
                    selected = selected.includes(id) ? selected.filter(function (entry) { return entry !== id; })
                        : selected.concat(id);
                } else selected = [id];
                console.log("RTS Bridge selected Marines=" + selected.join(","));
            }
            function chooseRectangle(start, end, shift) {
                refreshSelection();
                // A screen rectangle is a diamond in park coordinates. The
                // isometric screen axes are x+y and y-x for every rotation.
                const lowSum = Math.min(start.x + start.y, end.x + end.y);
                const highSum = Math.max(start.x + start.y, end.x + end.y);
                const lowDiff = Math.min(start.y - start.x, end.y - end.x);
                const highDiff = Math.max(start.y - start.x, end.y - end.x);
                const inside = Object.keys(controlUnits).filter(function (id) {
                    const unit = controlUnits[id];
                    return unit.kind === "terran_marine" && unit.hp > 0 && unit.owner === terranOwner
                        && unit.x + unit.y >= lowSum && unit.x + unit.y <= highSum
                        && unit.y - unit.x >= lowDiff && unit.y - unit.x <= highDiff;
                });
                selected = shift ? selected.concat(inside.filter(function (id) { return !selected.includes(id); })) : inside;
                console.log("RTS Bridge selected Marines=" + selected.join(","));
            }
            ui.registerShortcut({ id: "starcoaster.select-multiple", text: "Toggle Marine squad selection",
                bindings: ["M"], callback: function () {
                    selectingMultiple = !selectingMultiple;
                    console.log("RTS Bridge multi-select=" + selectingMultiple);
                } });
            ui.registerShortcut({ id: "starcoaster.hold-position", text: "Hold Marine positions",
                bindings: ["H"], callback: function () {
                    refreshSelection();
                    if (selected.length) context.executeAction(COMMAND_ACTION,
                        { session: controlSession, request: ++nextRequest, unit_ids: selected.slice(), verb: "hold" },
                        function (result) { if (result.error) ui.showError("Marine command", result.errorMessage); });
                } });
            ui.registerShortcut({ id: "starcoaster.stop", text: "Stop Marines", bindings: ["S"],
                callback: function () {
                    refreshSelection();
                    if (selected.length) context.executeAction(COMMAND_ACTION,
                        { session: controlSession, request: ++nextRequest, unit_ids: selected.slice(), verb: "stop" },
                        function (result) { if (result.error) ui.showError("Marine command", result.errorMessage); });
                } });
            ui.registerShortcut({ id: "starcoaster.attack-move", text: "Marine attack move", bindings: ["A"],
                callback: function () { attackMove = true; } });
            ui.registerShortcut({ id: "starcoaster.save-group-1", text: "Save Marine group 1", bindings: ["CTRL+1"],
                callback: function () { refreshSelection(); controlGroups[1] = selected.slice(); } });
            ui.registerShortcut({ id: "starcoaster.recall-group-1", text: "Select Marine group 1", bindings: ["1"],
                callback: function () { refreshSelection(); selected = (controlGroups[1] || []).filter(function (id) {
                    return controlUnits[id] && controlUnits[id].hp > 0;
                }); } });
            function orderAt(point) {
                refreshSelection();
                if (!selected.length || !point) return;
                const hit = rtsBridge.hitTest(point.x, point.y, 48);
                const target = hit && controlUnits[hit];
                const structure = Object.keys(worldTargetIds).filter(function (id) {
                    return worldTargetIds[id].geometry.rects.some(function (rect) {
                        return point.x >= rect.x && point.y >= rect.y
                            && point.x < rect.x + rect.width && point.y < rect.y + rect.height;
                    });
                })[0];
                const args = { session: controlSession, request: ++nextRequest,
                    unit_ids: selected.slice(), verb: target && target.kind === "zerg_zergling" ? "attack" : "move" };
                if (args.verb === "attack") args.target_id = hit;
                else if (structure) { args.verb = "attack"; args.target_entity_id = structure; }
                else {
                    if (attackMove) args.verb = "attack_move";
                    args.x = point.x + (0);
                    args.y = point.y + (0);
                }
                attackMove = false;
                context.executeAction(COMMAND_ACTION, args, function (result) {
                    if (result.error) ui.showError("Marine command", result.errorMessage);
                });
            }
            function activateSpawnTool() {
                if (!controlSession || outcomeState) {
                    ui.showError("Marine reinforcements", "The battle is not ready for spawning");
                    return;
                }
                spawnMode = true;
                ui.activateTool({ id: "starcoaster.spawn-marine", cursor: "cross_hair",
                    filter: ["terrain", "footpath", "ride", "wall", "scenery", "large_scenery"],
                    onMove: function (event) {
                        const point = pointFrom(event);
                        spawnPreview = point && point.x >= 0 && point.y >= 0
                            && point.x < map.size.x * 32 && point.y < map.size.y * 32
                            ? { x: Math.floor(point.x / 32) * 32, y: Math.floor(point.y / 32) * 32 } : null;
                        refreshSelection();
                    },
                    onDown: function (event) {
                        const point = pointFrom(event);
                        if (!point || point.x < 0 || point.y < 0 || point.x >= map.size.x * 32
                            || point.y >= map.size.y * 32) {
                            ui.showError("Marine reinforcements", "Choose a location inside the park");
                            return;
                        }
                        const requestId = controlSession + ":spawn:" + network.currentPlayer.id
                            + ":" + (++nextSpawnRequest);
                        context.executeAction(SPAWN_ACTION, { session: controlSession, request_id: requestId,
                            count: spawnCount, x: point.x, y: point.y }, function (result) {
                            if (result.error) ui.showError("Marine reinforcements", result.errorMessage);
                        });
                        spawnMode = false;
                        spawnPreview = null;
                        ui.activateTool(marineSelectionTool);
                    },
                    onFinish: function () { spawnMode = false; spawnPreview = null; refreshSelection(); }
                });
            }
            const marineSelectionTool = { id: "starcoaster.select-marine", cursor: "cross_hair",
                filter: ["terrain", "footpath", "ride", "wall", "scenery", "large_scenery"],
                onDown: function (event) {
                    dragStart = pointFrom(event); dragEnd = dragStart;

                },
                onMove: function (event) {
                    if (dragStart && event.isDown) {
                        dragEnd = pointFrom(event) || dragEnd;
                        if (dragEnd) ui.tileSelection.range = {
                            leftTop: { x: Math.min(dragStart.x, dragEnd.x), y: Math.min(dragStart.y, dragEnd.y) },
                            rightBottom: { x: Math.max(dragStart.x, dragEnd.x), y: Math.max(dragStart.y, dragEnd.y) }
                        };
                    }
                },
                onUp: function (event) {
                    const end = pointFrom(event) || dragEnd;
                    if (dragStart && end) {
                        if (Math.abs(end.x - dragStart.x) >= 24 || Math.abs(end.y - dragStart.y) >= 24)
                            chooseRectangle(dragStart, end, event.shift);
                        else chooseAt(end, event.shift);
                    }
                    ui.tileSelection.range = null;
                    dragStart = null; dragEnd = null;
                },
                onFinish: function () {
                     ui.tileSelection.range = null; ui.tileSelection.tiles = [];
                },
                onRightClick: function (event) { orderAt(pointFrom(event)); } };
            ui.activateTool(marineSelectionTool);
        }

        if (network.mode !== "server") return;

            context.subscribe("network.join", function () {
                if (publishingTargetSession) publishTargetCatalog(publishingTargetSession, publishedTargets);
                if (actorLifecycleSession) Object.keys(activeActorGenerations).forEach(function (id) {
                    publishActorLifecycle(actorLifecycleSession, id, activeActorGenerations[id], "active");
                });
            });
            startWorldAdapter(function (sender) { worldCommandSender = sender; }, function (result) {
                const original = pendingCommands[result.command_id];
                if (!original) return;
                delete pendingCommands[result.command_id];
                context.executeAction(RESULT_ACTION, { player: original.player, request: original.request,
                    unit: original.unit, accepted: result.accepted === true,
                    reason: /^[a-z_]{2,64}$/.test(result.reason || "") ? result.reason : "command_rejected" },
                function (actionResult) {
                    if (actionResult.error) console.log("WORLD_COMMAND_RESULT_ERROR " + actionResult.errorMessage);
                });
            }, function (_discovered, worldSession) {
                publishTargetCatalog(worldSession, []);
            }, publishTargetCatalog, publishActorLifecycle,
            function (sender) { worldSpawnSender = sender; }, function (status) {
                const payload = { session: controlSession, request_id: status.request_id,
                    state: status.state, reason: status.reason || "", units: status.units || [] };
                context.executeAction(SPAWN_STATUS_ACTION, payload, function (result) {
                    if (result.error) console.log("WORLD_SPAWN_STATUS_ERROR " + result.errorMessage);
                });
            });
            return;


    }

    registerPlugin({
        name: "Passthrough RTS Bridge",
        version: "0.3.0",
        authors: ["Passthrough RTS project"],
        type: "remote",
        licence: "MIT",
        targetApiVersion: 124,
        minApiVersion: 124,
        main: main
    });
}());
