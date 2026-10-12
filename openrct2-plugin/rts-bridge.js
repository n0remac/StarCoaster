/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const COMMAND_ACTION = "rtsbridge.marineCommand";
    const RESULT_ACTION = "rtsbridge.commandResult";
    const OUTCOME_ACTION = "rtsbridge.worldOutcome";
    const TARGET_ACTION = "rtsbridge.targetCatalog";
    const PORT = 39999;
    const SIEGE_ENABLED = false;
    const FRONTIER_ENABLED = false;
    const ASSAULT_CONFIG = typeof STARCOASTER_SCENARIO_CONFIG === "object"
        && STARCOASTER_SCENARIO_CONFIG.scenario === "park-assault"
        ? STARCOASTER_SCENARIO_CONFIG : null;
    const ASSAULT_ENABLED = ASSAULT_CONFIG !== null;
    const MAP_ID = ASSAULT_ENABLED ? "park-assault"
        : FRONTIER_ENABLED ? "frontier-defense" : SIEGE_ENABLED ? "ride-siege" : "demo-flat";
    const MAX_LINE = 32768;
    const MAX_UNITS = 32;
    const ORIGIN_X = 0;
    const ORIGIN_Y = 0;
    const SCALE_X = 1;
    const SCALE_Y = 1;
    const WORLD_ENABLED = typeof STARCOASTER_WORLD_BRIDGE !== "undefined" && STARCOASTER_WORLD_BRIDGE === true;

    function startWorldAdapter(onCommandSender, onCommandResult, onEntities) {
        const session = Array.from({ length: 4 }, function () {
            return Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, "0");
        }).join("");
        let revision = 1, serial = 0, socket = null, buffer = "", inFlight = null, lastCombatSeq = 0, retryTicks = 0;
        const queue = [], generations = {}, activeKeys = {}, activeItems = {}, entities = {}, completed = {};
        function envelope(kind, payload, rev) {
            return { v: 1, kind: kind, session: session, op_id: "park:" + (++serial),
                source: "openrct2", revision: rev || revision, payload: payload };
        }
        function sendNext() {
            if (!socket || inFlight || !queue.length) return;
            inFlight = queue.shift();
            socket.write(JSON.stringify(inFlight) + "\n");
        }
        function send(kind, payload, rev) { queue.push(envelope(kind, payload, rev)); sendNext(); }
        onCommandSender(function (payload) { send("combat.command", payload); });
        function rotate(offset, direction) {
            if (direction === 1) return { x: offset.y, y: -offset.x };
            if (direction === 2) return { x: -offset.x, y: -offset.y };
            if (direction === 3) return { x: -offset.y, y: offset.x };
            return { x: offset.x, y: offset.y };
        }
        function discover() {
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
                for (let n = 0; n < tile.numElements; ++n) {
                    const element = tile.getElement(n), kind = element.type;
                    if (kind === "surface") {
                        terrain.push({ x: x, y: y, height: element.baseHeight * 8,
                            water: element.waterHeight || 0, surface: element.surfaceObject || 0,
                            walkable: !element.waterHeight });
                        continue;
                    }
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
                    if (kind === "wall") grouped[key].rects.push(direction === 0
                        ? { x: x * 32, y: y * 32, width: 32, height: 4 }
                        : direction === 1 ? { x: x * 32, y: y * 32, width: 4, height: 32 }
                        : direction === 2 ? { x: x * 32, y: y * 32 + 28, width: 32, height: 4 }
                        : { x: x * 32 + 28, y: y * 32, width: 4, height: 32 });
                }
            }
            Object.keys(rides).forEach(function (id) {
                const item = rides[id], ride = item.ride;
                if (!item.cells.length) return;
                const kind = ride.classification === "stall" ? "shop" : ride.classification === "facility" ? "facility" : "ride";
                const key = "ride:" + id;
                grouped[key] = { key: key, kind: kind, type: ride.object ? ride.object.identifier : String(ride.type),
                    x: item.cells[0].x * 32, y: item.cells[0].y * 32, z: item.height || 0, direction: 0,
                    cells: item.cells, rects: [], removal: { action: "ridedemolish", args: { ride: ride.id, modifyType: 0 } },
                    rideId: ride.id, rideType: ride.type };
            });
            ["guest", "staff"].forEach(function (kind) {
                if (typeof map.getAllEntities !== "function") return;
                map.getAllEntities(kind).forEach(function (actor) {
                    if (!Number.isInteger(actor.x) || !Number.isInteger(actor.y) || actor.x < 0 || actor.y < 0
                        || actor.x >= map.size.x * 32 || actor.y >= map.size.y * 32) return;
                    const key = kind + ":" + actor.id;
                    grouped[key] = { key: key, kind: kind, type: kind, x: actor.x, y: actor.y,
                        z: actor.z || 0, direction: 0, cells: [], rects: [], removal: { action: "" } };
                });
            });
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
                    geometry: { cells: cells, rects: item.kind === "wall" ? item.rects : rects },
                    collision: { blocks: item.kind !== "path" && item.kind !== "guest" && item.kind !== "staff" },
                    destructible: item.kind !== "guest" && item.kind !== "staff",
                    combat: { targetable: item.kind !== "path" && item.kind !== "guest" && item.kind !== "staff", health: 100 },
                    removal: item.removal, revision: revision };
                item.id = id; item.entity = entity; entities[id] = item; activeItems[key] = item; result.push(entity);
            });
            Object.keys(activeKeys).forEach(function (key) { if (!now[key]) { delete activeKeys[key]; delete activeItems[key]; } });
            return { entities: result, terrain: terrain };
        }
        context.subscribe("action.execute", function (event) {
            if (!event || !event.result || event.result.error || !event.args) return;
            const action = event.action, args = event.args;
            if (["ridedemolish", "ridecreate", "trackplace", "trackremove"].includes(action)) {
                if (Number.isInteger(args.ride)) activeKeys["ride:" + args.ride] = false;
                return;
            }
            const kind = action === "smallsceneryplace" || action === "smallsceneryremove" ? "small_scenery"
                : action === "largesceneryplace" || action === "largesceneryremove" ? "large_scenery"
                : action === "wallplace" || action === "wallremove" ? "wall"
                : action === "footpathplace" || action === "footpathremove" ? "path" : "";
            if (!kind || !Number.isInteger(args.x) || !Number.isInteger(args.y)) return;
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
            context.executeAction(tracked.removal.action, tracked.removal.args, function (result) {
                const remaining = discover().entities.some(function (e) { return e.id === tracked.id; });
                const confirmed = !result.error && !remaining;
                if (confirmed) revision++;
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
                    console.log("WORLD_ERROR " + message.payload.error); socket.destroy({}); return;
                }
                inFlight = null; sendNext();
            } else if (message.kind === "world.resync") {
                queue.length = 0; inFlight = null; snapshot();
            }
            else if (message.kind === "combat.event") combatEvent(message);
            else if (message.kind === "combat.result" && message.payload.command_id) onCommandResult(message.payload);
            else if (message.kind === "combat.snapshot") {
                const state = message.payload;
                if (!state || !Number.isSafeInteger(state.seq) || state.seq <= lastCombatSeq
                    || !validAction({ session: session, seq: state.seq, units: state.units })) return;
                lastCombatSeq = state.seq;
                context.executeAction(ACTION, { session: session, seq: state.seq, units: state.units },
                    function (result) { if (result.error) console.log("WORLD_RENDER_ERROR " + result.errorMessage); });
            }
            else if (message.kind === "world.ready") {
                lastCombatSeq = 0;
                const targets = (message.payload.target_ids || []).map(function (id) {
                    const item = entities[id];
                    return item ? { id: id, rects: item.entity.geometry.rects } : null;
                }).filter(function (item) { return item !== null; });
                Object.keys(entities).forEach(function (id) { entities[id].activeTarget = false; });
                targets.forEach(function (item) { entities[item.id].activeTarget = true; });
                context.executeAction(TARGET_ACTION, { session: session, targets: targets }, function (result) {
                    if (result.error) console.log("WORLD_TARGET_CATALOG_ERROR " + result.errorMessage);
                });
                console.log("WORLD_READY entities=" + message.payload.entities
                    + " targets=" + message.payload.targets + " obstacles=" + message.payload.obstacles
                    + " navigation=" + message.payload.navigation
                    + " unsupported=" + (message.payload.unsupported_total || 0));
            }
            else if (message.kind === "world.outcome" && message.payload
                && ["victory", "defeat"].includes(message.payload.state))
                context.executeAction(OUTCOME_ACTION, { session: session,
                    scenario_id: message.payload.scenario_id, state: message.payload.state,
                    objective_id: message.payload.objective_id }, function (result) {
                    if (result.error) console.log("WORLD_OUTCOME_ERROR " + result.errorMessage);
                });
            else if (message.kind === "entity.remove") {
                const removed = message.payload && message.payload.id;
                if (typeof removed === "string") context.executeAction(TARGET_ACTION, {
                    session: session, targets: Object.keys(entities).filter(function (id) {
                        return id !== removed && entities[id].activeTarget === true;
                    }).map(function (id) { return { id: id, rects: entities[id].entity.geometry.rects }; })
                }, function () {});
                if (entities[removed]) entities[removed].activeTarget = false;
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
                send("world.hello", { capabilities: ["snapshot", "entity.upsert", "entity.remove", "navigation.terrain.update"] });
                snapshot();
            });
        }
        connect();
        context.subscribe("interval.tick", function () { if (!socket && ++retryTicks >= 40) { retryTicks = 0; connect(); } });
    }

    function validUnits(args, combat) {
        if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
            || !Number.isSafeInteger(args.seq) || args.seq < 1 || !Array.isArray(args.units)
            || args.units.length > (WORLD_ENABLED && combat ? 256 : MAX_UNITS)) {
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
                && (unit.motion === "idle" || unit.motion === "walk" || (combat && (unit.motion === "attack" || unit.motion === "death")))
                && (!combat || ((unit.kind === "alien_scout" || unit.kind === "zerg_zergling" || unit.kind === "terran_marine")
                    && Number.isInteger(unit.owner) && unit.owner >= 0 && unit.owner <= 11
                    && Number.isInteger(unit.hp) && unit.hp >= 0
                    && Number.isInteger(unit.max_hp) && unit.max_hp >= unit.hp && unit.max_hp <= 10000
                    && Number.isInteger(unit.attack_frames) && unit.attack_frames >= 0));
        });
    }

    function validAction(args) { return validUnits(args, true); }

    function validWire(snapshot) {
        if (!snapshot || snapshot.v !== 1 || snapshot.kind !== "units.snapshot"
            || snapshot.map_id !== "demo-flat" || !validUnits(snapshot, false)
            || !Number.isSafeInteger(snapshot.bw_tick) || snapshot.bw_tick < 0) {
            return false;
        }
        return snapshot.units.every(function (unit) {
            return unit.kind === "alien_scout" && unit.alive === true;
        });
    }

    function validSiegeWire(snapshot) {
        if (!snapshot || snapshot.v !== 2 || snapshot.kind !== "scenario.snapshot"
            || snapshot.map_id !== "ride-siege" || !validUnits(snapshot, false)
            || !Number.isSafeInteger(snapshot.bw_tick) || snapshot.bw_tick < 0
            || snapshot.units.length > 8 || !Array.isArray(snapshot.targets)
            || snapshot.targets.length !== 1) return false;
        if (!snapshot.units.every(function (unit) {
            return unit.kind === "alien_scout" && unit.alive === true;
        })) return false;
        const target = snapshot.targets[0];
        if (!target || target.id !== "carousel-1" || !/^openbw:[0-9]+$/.test(target.proxy_unit_id)
            || target.max_hp !== 200 || !Number.isInteger(target.hp)
            || target.hp < 0 || target.hp > target.max_hp) return false;
        return (target.state === "intact" && target.hp === target.max_hp)
            || (target.state === "damaged" && target.hp > 0 && target.hp < target.max_hp)
            || (target.state === "destroyed" && target.hp === 0);
    }

    function validCombatWire(snapshot) {
        if (!snapshot || snapshot.v !== 3 || snapshot.kind !== "scenario.snapshot"
            || snapshot.map_id !== MAP_ID || !validUnits(snapshot, true)
            || !Number.isSafeInteger(snapshot.bw_tick) || snapshot.bw_tick < 0
            || snapshot.units.length > 12 || !Array.isArray(snapshot.targets)
            || snapshot.targets.length !== (FRONTIER_ENABLED ? 1 : 0)
            || !Array.isArray(snapshot.events) || snapshot.events.length > 64) return false;
        if (!snapshot.units.every(function (unit) {
            return (unit.kind === "terran_marine" || unit.kind === "zerg_zergling")
                && unit.max_hp === (unit.kind === "terran_marine" ? 40 : 35)
                && typeof unit.alive === "boolean" && unit.alive === (unit.hp > 0)
                && (unit.alive ? unit.motion !== "death" : unit.motion === "death")
                && (unit.target_id === null || (typeof unit.target_id === "string" && /^openbw:[0-9]+$/.test(unit.target_id)));
        })) return false;
        const eventIds = {};
        if (!snapshot.events.every(function (event) {
            if (!event || typeof event.id !== "string"
                || !/^[0-9a-f]{32}:[0-9]+:(damage|death|attack_frame|destruction):[0-9]+$/.test(event.id)
                || event.id.slice(0, 32) !== snapshot.session || eventIds[event.id]
                || !["damage", "death", "attack_frame", "destruction"].includes(event.kind)
                || !/^openbw:[0-9]+$/.test(event.unit_id)
                || !Number.isSafeInteger(event.value) || event.value < 0
                || !Number.isSafeInteger(event.bw_tick) || event.bw_tick < 0 || event.bw_tick > snapshot.bw_tick)
                return false;
            eventIds[event.id] = true;
            return true;
        })) return false;
        if (!FRONTIER_ENABLED) return true;
        const target = snapshot.targets[0];
        return !!target && target.id === "carousel-1" && /^openbw:[0-9]+$/.test(target.proxy_unit_id)
            && target.max_hp === 200 && Number.isInteger(target.hp) && target.hp >= 0 && target.hp <= 200
            && ((target.state === "intact" && target.hp === 200)
                || (target.state === "damaged" && target.hp > 0 && target.hp < 200)
                || (target.state === "destroyed" && target.hp === 0));
    }

    function validAssaultWire(snapshot) {
        if (!ASSAULT_ENABLED || !snapshot || snapshot.v !== 3 || snapshot.kind !== "scenario.snapshot"
            || snapshot.map_id !== "park-assault" || !validUnits(snapshot, true)
            || !Number.isSafeInteger(snapshot.bw_tick) || snapshot.bw_tick < 0
            || !Number.isSafeInteger(snapshot.map_revision) || snapshot.map_revision < 1
            || !Array.isArray(snapshot.targets) || snapshot.targets.length !== ASSAULT_CONFIG.targets.length
            || !Array.isArray(snapshot.events) || snapshot.events.length > 64) return false;
        if (!snapshot.units.every(function (unit) {
            return unit.kind === "zerg_zergling" && unit.max_hp === 35
                && typeof unit.alive === "boolean" && unit.alive === (unit.hp > 0)
                && (unit.alive ? unit.motion !== "death" : unit.motion === "death")
                && (unit.target_id === null || (typeof unit.target_id === "string"
                    && /^openbw:[0-9]+$/.test(unit.target_id)));
        })) return false;
        const seenTargets = {}, seenProxies = {};
        if (!snapshot.targets.every(function (target) {
            const configured = ASSAULT_CONFIG.targets.filter(function (entry) { return entry.id === target.id; })[0];
            if (!configured || seenTargets[target.id] || !/^openbw:[0-9]+$/.test(target.proxy_unit_id)
                || seenProxies[target.proxy_unit_id] || target.max_hp !== configured.max_hp
                || !Number.isInteger(target.hp) || target.hp < 0 || target.hp > target.max_hp) return false;
            seenTargets[target.id] = true;
            seenProxies[target.proxy_unit_id] = true;
            return (target.state === "intact" && target.hp === target.max_hp)
                || (target.state === "damaged" && target.hp > 0 && target.hp < target.max_hp)
                || (target.state === "destroyed" && target.hp === 0);
        })) return false;
        const eventIds = {};
        return snapshot.events.every(function (event) {
            if (!event || typeof event.id !== "string" || eventIds[event.id]
                || !/^[0-9a-f]{32}:[0-9]+:(damage|death|attack_frame|destruction):[0-9]+$/.test(event.id)
                || event.id.slice(0, 32) !== snapshot.session
                || !["damage", "death", "attack_frame", "destruction"].includes(event.kind)
                || !/^openbw:[0-9]+$/.test(event.unit_id)
                || !Number.isSafeInteger(event.value) || event.value < 0
                || !Number.isSafeInteger(event.bw_tick) || event.bw_tick < 0
                || event.bw_tick > snapshot.bw_tick) return false;
            eventIds[event.id] = true;
            return true;
        });
    }

    function assaultTracks(rideId) {
        const found = [];
        const bounds = ASSAULT_CONFIG.bounds;
        for (let x = bounds.min_x; x <= bounds.max_x; ++x) {
            for (let y = bounds.min_y; y <= bounds.max_y; ++y) {
                const tile = map.getTile(x, y);
                for (let i = 0; i < tile.numElements; ++i) {
                    const element = tile.getElement(i);
                    if (element.type === "track" && element.ride === rideId)
                        found.push(x + "," + y + "," + element.baseHeight * 8 + "," + element.trackType);
                }
            }
        }
        return found.sort();
    }

    function assaultRide(configured) {
        const matches = map.rides.filter(function (ride) { return ride.name === configured.name; });
        if (matches.length !== 1) return null;
        const ride = matches[0];
        const expected = configured.tiles.map(function (tile) {
            return tile.x + "," + tile.y + "," + tile.z + "," + tile.track_type;
        }).sort();
        if (ride.id !== configured.ride_id || ride.type !== configured.ride_type
            || !ride.object || ride.object.identifier !== configured.object_id
            || ride.status !== "closed" || ride.isEmpty !== true
            || JSON.stringify(assaultTracks(ride.id)) !== JSON.stringify(expected)) return null;
        return ride;
    }

    function assaultScenerySignature() {
        let total = 0, hash = 2166136261;
        const bounds = ASSAULT_CONFIG.bounds;
        for (let x = bounds.min_x; x <= bounds.max_x; ++x) {
            for (let y = bounds.min_y; y <= bounds.max_y; ++y) {
                const tile = map.getTile(x, y);
                for (let i = 0; i < tile.numElements; ++i) {
                    const element = tile.getElement(i);
                    if (!["footpath", "small_scenery", "wall"].includes(element.type)) continue;
                    ++total;
                    const value = x * 4099 + y * 131 + element.baseHeight * 17
                        + (element.object || 0) * 7 + element.type.length;
                    hash = Math.imul(hash ^ value, 16777619) >>> 0;
                }
            }
        }
        return total + ":" + hash;
    }

    function carouselTracks(rideId) {
        const found = [];
        for (let x = 18; x <= 20; ++x) {
            for (let y = 14; y <= 16; ++y) {
                const tile = map.getTile(x, y);
                for (let i = 0; i < tile.numElements; ++i) {
                    const element = tile.getElement(i);
                    if (element.type === "track" && element.ride === rideId)
                        found.push({ x: x, y: y, z: element.baseHeight * 8, type: element.trackType });
                }
            }
        }
        return found;
    }

    function registeredCarousel() {
        const matching = map.rides.filter(function (ride) { return ride.name === "Frontier Carousel"; });
        if (matching.length !== 1) return null;
        const ride = matching[0];
        const tracks = carouselTracks(ride.id);
        if (ride.id !== 100 || ride.type !== 33 || !ride.object
            || ride.object.identifier !== "rct2.ride.mgr1" || ride.status !== "closed"
            || ride.isEmpty !== true || tracks.length !== 9
            || tracks.some(function (track) { return track.z !== 112 || track.type !== 266; })) return null;
        return ride;
    }

    function main() {
        if (typeof rtsBridge !== "object" || rtsBridge.version !== 4 || rtsBridge.assetVersion !== 3
            || typeof rtsBridge.applySnapshot !== "function"
            || typeof rtsBridge.invalidateAnimation !== "function") {
            throw new Error("RTS Bridge needs the matching native OpenRCT2 build and asset pack");
        }

        let controlSession = "";
        let controlUnits = {};
        let terranOwner = -1;
        let commanderPlayer = -1;
        let commandSocket = null;
        let commandConnected = false;
        let commandSerial = 0;
        let worldCommandSender = null;
        let worldTargetIds = {};
        let targetCatalogSession = "";
        let outcomeState = null;
        let shownOutcome = "";
        const pendingCommands = {};
        context.registerAction(ACTION, function (event) {
            if (network.mode === "server" && event.player !== network.currentPlayer.id) {
                return { error: 1, errorMessage: "Only the RTS bridge server may publish snapshots" };
            }
            return validAction(event.args) ? {} : { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
        }, function (event) {
            if (!validAction(event.args)) return { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
            rtsBridge.applySnapshot(event.args);
            if (controlSession !== event.args.session) { outcomeState = null; shownOutcome = ""; }
            controlSession = event.args.session;
            controlUnits = {};
            event.args.units.forEach(function (unit) { controlUnits[unit.id] = unit; });
            const marine = event.args.units.filter(function (unit) { return unit.kind === "terran_marine"; })[0];
            if (marine) terranOwner = marine.owner;
            return {};
        });

        if (FRONTIER_ENABLED || WORLD_ENABLED) {
            if (WORLD_ENABLED) context.registerAction(TARGET_ACTION, function (event) {
                const args = event.args;
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may publish structure targets" };
                if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
                    || !Array.isArray(args.targets) || args.targets.length > 128
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
                return {};
            }, function (event) {
                targetCatalogSession = event.args.session;
                worldTargetIds = {};
                event.args.targets.forEach(function (item) {
                    worldTargetIds[item.id] = { geometry: { rects: item.rects } };
                });
                return {};
            });
            if (WORLD_ENABLED) context.registerAction(OUTCOME_ACTION, function (event) {
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
            context.registerAction(COMMAND_ACTION, function (event) {
                const args = event.args;
                if (WORLD_ENABLED && outcomeState) return { error: 1, errorMessage: "Battle has ended" };
                if (network.mode === "server" && (!Array.isArray(network.players)
                    || !network.players.some(function (player) { return player.id === event.player; })))
                    return { error: 1, errorMessage: "Player is not connected" };
                if (network.mode === "server" && WORLD_ENABLED) {
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
                    || args.unit_ids.length > (WORLD_ENABLED ? 32 : 4) || !(WORLD_ENABLED
                        ? ["move", "attack", "attack_move", "hold", "stop"].includes(args.verb)
                        : ["move", "attack", "hold"].includes(args.verb)))
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
                    const structure = WORLD_ENABLED && typeof args.target_entity_id === "string"
                        && /^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(args.target_entity_id)
                        && targetCatalogSession === args.session && worldTargetIds[args.target_entity_id];
                    if ((!target || target.kind !== "zerg_zergling" || target.hp <= 0) && !structure)
                        return { error: 1, errorMessage: "Invalid Zergling target" };
                }
                if (network.mode === "server" && !(WORLD_ENABLED ? worldCommandSender : commandConnected))
                    return { error: 1, errorMessage: "Terran controller disconnected" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;
                if (WORLD_ENABLED) {
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
                }
                args.unit_ids.forEach(function (id) {
                    const serial = ++commandSerial;
                    const x = args.verb === "attack" ? Number(args.target_id.slice(7))
                        : args.verb === "move" ? args.x : 0;
                    const y = args.verb === "move" ? args.y : 0;
                    pendingCommands[serial] = { player: event.player, request: args.request, unit: id };
                    const wire = "order " + args.session + " " + serial + " " + Number(id.slice(7))
                        + " " + args.verb + " " + x + " " + y + "\n";
                    // OpenRCT2's ScSocket.write returns false when all bytes were sent.
                    // The controller acknowledgement is the only success signal.
                    commandSocket.write(wire);
                });
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
                if (args.player === network.currentPlayer.id)
                    console.log("RTS Bridge Marine command request=" + args.request + " unit=" + args.unit
                        + " accepted=" + args.accepted + " reason=" + args.reason);
                return {};
            });
        }

        let animationTicks = 0;
        let cameraSession = "";
        context.subscribe("interval.tick", function () {
            if (++animationTicks % 4 === 0) rtsBridge.invalidateAnimation();
            if (WORLD_ENABLED && network.mode === "server" && targetCatalogSession
                && animationTicks % 80 === 0) context.executeAction(TARGET_ACTION, {
                    session: targetCatalogSession,
                    targets: Object.keys(worldTargetIds).map(function (id) {
                        return { id: id, rects: worldTargetIds[id].geometry.rects };
                    })
                }, function () {});
            if (WORLD_ENABLED && network.mode === "client" && controlSession
                && cameraSession !== controlSession && typeof ui !== "undefined" && ui.mainViewport) {
                ui.mainViewport.zoom = 1;
                ui.mainViewport.moveTo({ x: map.size.x * 16, y: map.size.y * 16 });
                cameraSession = controlSession;
            }
        });

        if ((FRONTIER_ENABLED || WORLD_ENABLED) && typeof ui !== "undefined") {
            let selected = [];
            let nextRequest = 0;
            let selectingMultiple = false;
            let selectionSession = "";
            let dragStart = null;
            let dragEnd = null;
            let attackMove = false;
            const controlGroups = {};
            const squadWindow = WORLD_ENABLED ? ui.openWindow({ classification: "starcoaster-squad",
                width: 248, height: 88, title: "Frontier Outpost", widgets: [
                    { type: "label", name: "selection", x: 8, y: 19, width: 232, height: 14,
                        text: "Waiting for battlefield" },
                    { type: "label", x: 8, y: 38, width: 232, height: 14,
                        text: "Drag select | A attack move | H hold | S stop" },
                    { type: "label", name: "objective", x: 8, y: 57, width: 232, height: 14,
                        text: "Defend Frontier Carousel" }
                ] }) : null;
            function pointFrom(event) { return event.mapCoords || rtsBridge.cursorWorld(); }
            function refreshSelection() {
                if (selectionSession !== controlSession) {
                    selectionSession = controlSession; selected = [];
                    Object.keys(controlGroups).forEach(function (number) { delete controlGroups[number]; });
                }
                selected = selected.filter(function (id) {
                    const unit = controlUnits[id];
                    return unit && unit.kind === "terran_marine" && unit.hp > 0;
                });
                if (squadWindow) {
                    const info = squadWindow.findWidget("selection");
                    if (info) info.text = selected.length + " Marine" + (selected.length === 1 ? "" : "s")
                        + " selected" + (selected.length === 1 ? " | HP " + controlUnits[selected[0]].hp : "");
                    const objective = squadWindow.findWidget("objective");
                    if (objective) objective.text = outcomeState === "victory" ? "Victory: Outpost defended"
                        : outcomeState === "defeat" ? "Defeat: Outpost lost" : "Defend Frontier Carousel";
                }
                if (outcomeState && shownOutcome !== controlSession + ":" + outcomeState) {
                    shownOutcome = controlSession + ":" + outcomeState;
                    ui.showError("Frontier Outpost", outcomeState === "victory"
                        ? "Victory! The carousel survived." : "Defeat! The outpost has fallen.");
                }
            }
            context.subscribe("interval.tick", refreshSelection);
            function chooseAt(point, shift) {
                refreshSelection();
                const id = point && rtsBridge.hitTest(point.x, point.y, 22);
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
                const lowX = Math.min(start.x, end.x), highX = Math.max(start.x, end.x);
                const lowY = Math.min(start.y, end.y), highY = Math.max(start.y, end.y);
                const inside = Object.keys(controlUnits).filter(function (id) {
                    const unit = controlUnits[id];
                    return unit.kind === "terran_marine" && unit.hp > 0 && unit.owner === terranOwner
                        && unit.x >= lowX && unit.x <= highX && unit.y >= lowY && unit.y <= highY;
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
                    if (selected.length) context.executeAction(COMMAND_ACTION,
                        { session: controlSession, request: ++nextRequest, unit_ids: selected, verb: "hold" },
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
                const hit = rtsBridge.hitTest(point.x, point.y, 22);
                const target = hit && controlUnits[hit];
                const structure = WORLD_ENABLED && Object.keys(worldTargetIds).filter(function (id) {
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
                    args.x = point.x + (WORLD_ENABLED ? 0 : 128);
                    args.y = point.y + (WORLD_ENABLED ? 0 : 96);
                }
                attackMove = false;
                context.executeAction(COMMAND_ACTION, args, function (result) {
                    if (result.error) ui.showError("Marine command", result.errorMessage);
                });
            }
            ui.activateTool({ id: "starcoaster.select-marine", cursor: "cross_hair", filter: ["terrain", "footpath"],
                onDown: function (event) {
                    dragStart = pointFrom(event); dragEnd = dragStart;
                    if (!WORLD_ENABLED) chooseAt(dragStart, event.shift);
                },
                onMove: function (event) { if (dragStart && event.isDown) dragEnd = pointFrom(event) || dragEnd; },
                onUp: function (event) {
                    const end = pointFrom(event) || dragEnd;
                    if (WORLD_ENABLED && dragStart && end) {
                        if (Math.abs(end.x - dragStart.x) >= 24 || Math.abs(end.y - dragStart.y) >= 24)
                            chooseRectangle(dragStart, end, event.shift);
                        else chooseAt(end, event.shift);
                    }
                    dragStart = null; dragEnd = null;
                },
                onRightClick: function (event) { orderAt(pointFrom(event)); } });
        }

        if (network.mode !== "server") return;
        if (WORLD_ENABLED) {
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
                worldTargetIds = {};
                targetCatalogSession = worldSession;
                context.executeAction(TARGET_ACTION, { session: worldSession, targets: [] }, function () {});
            });
            return;
        }
        const siegeRide = (SIEGE_ENABLED || FRONTIER_ENABLED) ? registeredCarousel() : null;
        if ((SIEGE_ENABLED || FRONTIER_ENABLED) && !siegeRide) {
            console.log("RIDE_SIEGE_ERROR expected closed empty Frontier Carousel fixture is missing or changed");
            return;
        }
        if (SIEGE_ENABLED || FRONTIER_ENABLED) console.log("RIDE_SIEGE_READY ride=" + siegeRide.id + " tracks=9 target=carousel-1");
        const assaultRegistry = {};
        let assaultScenery = "";
        let assaultOtherRides = "";
        if (ASSAULT_ENABLED) {
            if (!ASSAULT_CONFIG.transform || !Number.isInteger(ASSAULT_CONFIG.transform.x)
                || !Number.isInteger(ASSAULT_CONFIG.transform.y)
                || !Array.isArray(ASSAULT_CONFIG.targets)
                || ASSAULT_CONFIG.targets.length < 3 || ASSAULT_CONFIG.targets.length > 8) {
                console.log("PARK_ASSAULT_ERROR malformed scenario configuration");
                return;
            }
            for (const configured of ASSAULT_CONFIG.targets) {
                if (!assaultRide(configured) || assaultRegistry[configured.id]) {
                    console.log("PARK_ASSAULT_ERROR target fixture missing or changed id=" + configured.id);
                    return;
                }
                assaultRegistry[configured.id] = { configured: configured, proxyId: "",
                    hp: configured.max_hp, state: "intact", demolitionAttempted: false,
                    failed: false, removalRevision: null };
            }
            assaultScenery = assaultScenerySignature();
            const targetIds = ASSAULT_CONFIG.targets.map(function (target) { return target.ride_id; });
            assaultOtherRides = JSON.stringify(map.rides.filter(function (ride) {
                return !targetIds.includes(ride.id);
            }).map(function (ride) { return ride.id; }).sort(function (a, b) { return a - b; }));
            console.log("PARK_ASSAULT_READY " + JSON.stringify({ targets: ASSAULT_CONFIG.targets.map(function (target) {
                return { id: target.id, ride_id: target.ride_id, tiles: target.tiles.length };
            }), scenery: assaultScenery }));
        }
        context.subscribe("network.join", function (event) {
            console.log("RTS Bridge player joined: " + event.player + "; active=" + network.numPlayers);
        });
        context.subscribe("network.leave", function (event) {
            console.log("RTS Bridge player left: " + event.player + "; active=" + network.numPlayers);
        });
        let session = "";
        let lastSeq = 0;
        let lastBwTick = -1;
        const retiredSessions = {};
        const seenEvents = {};
        const eventOrder = [];
        const siege = { rideId: siegeRide ? siegeRide.id : -1, proxyId: "", hp: 200,
            state: "intact", demolitionAttempted: false };
        let navigationRevision = 1;
        let lastReportedRevision = 1;
        const pendingNavigation = [];
        let socket = null;
        let reconnectTicks = 0;

        function connectCommands() {
            if (!FRONTIER_ENABLED || commandSocket !== null) return;
            const connection = network.createSocket();
            commandSocket = connection;
            let pending = "";
            connection.on("data", function (data) {
                pending += data;
                if (pending.length > 2048) { connection.destroy({}); return; }
                let newline;
                while ((newline = pending.indexOf("\n")) !== -1) {
                    const line = pending.slice(0, newline);
                    pending = pending.slice(newline + 1);
                    const match = /^ack ([0-9a-f]{32}) ([0-9]+) (accepted|rejected) (ok|invalid_marine|invalid_target|bwapi_rejected)$/.exec(line);
                    if (!match || match[1] !== controlSession) continue;
                    const original = pendingCommands[Number(match[2])];
                    if (!original) continue;
                    delete pendingCommands[Number(match[2])];
                    context.executeAction(RESULT_ACTION, { player: original.player, request: original.request,
                        unit: original.unit, accepted: match[3] === "accepted", reason: match[4] },
                        function (result) { if (result.error) console.log("RTS Bridge result action failed"); });
                }
            });
            connection.on("error", function (error) {
                console.log("RTS Bridge Terran controller socket error: " + error);
                commandConnected = false;
                if (commandSocket === connection) commandSocket = null;
                connection.destroy({});
            });
            connection.on("close", function () {
                commandConnected = false;
                if (commandSocket === connection) commandSocket = null;
            });
            connection.connect(40000, "127.0.0.1", function () {
                commandConnected = true;
                console.log("RTS Bridge connected to Terran BWAPI controller");
            });
        }

        function onLine(line) {
            let snapshot;
            try {
                snapshot = JSON.parse(line);
            } catch (error) {
                console.log("RTS Bridge dropped malformed JSON: " + error);
                return;
            }
            if (!(ASSAULT_ENABLED ? validAssaultWire(snapshot) : FRONTIER_ENABLED ? validCombatWire(snapshot) : SIEGE_ENABLED ? validSiegeWire(snapshot)
                : (snapshot && snapshot.v === 3 ? validCombatWire(snapshot) : validWire(snapshot)))) {
                console.log("RTS Bridge dropped invalid snapshot");
                return;
            }
            if (snapshot.session !== session) {
                if (retiredSessions[snapshot.session]) return;
                if ((SIEGE_ENABLED || FRONTIER_ENABLED) && (siege.demolitionAttempted || siege.state === "destroyed")) {
                    console.log("RIDE_SIEGE_ERROR new session requires a fresh, intact park");
                    return;
                }
                if (ASSAULT_ENABLED && ASSAULT_CONFIG.targets.some(function (target) {
                    return assaultRegistry[target.id].demolitionAttempted;
                })) {
                    console.log("PARK_ASSAULT_ERROR new session requires a fresh, intact park");
                    return;
                }
                if (session) retiredSessions[session] = true;
                session = snapshot.session;
                lastSeq = 0;
                lastBwTick = -1;
                if (ASSAULT_ENABLED) {
                    navigationRevision = 1;
                    lastReportedRevision = 1;
                    pendingNavigation.length = 0;
                    ASSAULT_CONFIG.targets.forEach(function (target) {
                        const tracked = assaultRegistry[target.id];
                        tracked.proxyId = "";
                        tracked.hp = target.max_hp;
                        tracked.state = "intact";
                        tracked.failed = false;
                    });
                }
                if (SIEGE_ENABLED || FRONTIER_ENABLED) {
                    siege.hp = 200;
                    siege.proxyId = "";
                    siege.state = "intact";
                }
                console.log("RTS Bridge session " + session);
            }
            if (snapshot.seq <= lastSeq || snapshot.bw_tick < lastBwTick) return;
            if (ASSAULT_ENABLED) {
                if (snapshot.map_revision < lastReportedRevision || snapshot.map_revision > navigationRevision) {
                    console.log("PARK_ASSAULT_ERROR mismatched map revision=" + snapshot.map_revision
                        + " expected_at_most=" + navigationRevision);
                    return;
                }
                // Check the entire target set before mutating any ride or HP state.
                if (!snapshot.targets.every(function (target) {
                    const tracked = assaultRegistry[target.id];
                    return tracked && (!tracked.proxyId || tracked.proxyId === target.proxy_unit_id)
                        && target.hp <= tracked.hp
                        && (tracked.state !== "destroyed" || target.state === "destroyed");
                })) {
                    console.log("PARK_ASSAULT_ERROR rejected target identity or HP regression");
                    return;
                }
                lastReportedRevision = snapshot.map_revision;
                snapshot.targets.forEach(function (target) {
                    const tracked = assaultRegistry[target.id];
                    tracked.proxyId = target.proxy_unit_id;
                    if (target.hp < tracked.hp)
                        console.log("PARK_ASSAULT_DAMAGE id=" + target.id + " from=" + tracked.hp
                            + " to=" + target.hp + " bw_tick=" + snapshot.bw_tick);
                    tracked.hp = target.hp;
                    if (target.state === "destroyed" && !tracked.demolitionAttempted && !tracked.failed) {
                        if (!assaultRide(tracked.configured)) {
                            tracked.failed = true;
                            tracked.state = "demolition_failed";
                            console.log("PARK_ASSAULT_DEMOLITION_FAILED id=" + target.id + " reason=ride_identity");
                            return;
                        }
                        tracked.demolitionAttempted = true;
                        tracked.state = "destruction_pending";
                        console.log("PARK_ASSAULT_DEMOLITION_PENDING id=" + target.id
                            + " ride=" + tracked.configured.ride_id + " bw_tick=" + snapshot.bw_tick);
                        context.executeAction("ridedemolish", { ride: tracked.configured.ride_id, modifyType: 0 }, function (result) {
                            const targetIds = ASSAULT_CONFIG.targets.map(function (entry) { return entry.ride_id; });
                            const otherRides = JSON.stringify(map.rides.filter(function (ride) {
                                return !targetIds.includes(ride.id);
                            }).map(function (ride) { return ride.id; }).sort(function (a, b) { return a - b; }));
                            if (result.error || map.getRide(tracked.configured.ride_id)
                                || assaultTracks(tracked.configured.ride_id).length
                                || assaultScenerySignature() !== assaultScenery || otherRides !== assaultOtherRides) {
                                tracked.failed = true;
                                tracked.state = "demolition_failed";
                                console.log("PARK_ASSAULT_DEMOLITION_FAILED id=" + target.id + " reason="
                                    + (result.errorMessage || "ride, track, or unrelated park state changed"));
                                return;
                            }
                            tracked.state = "destroyed";
                            tracked.removalRevision = ++navigationRevision;
                            const wire = "nav " + session + " " + navigationRevision + " " + target.id + "\n";
                            if (socket) socket.write(wire);
                            else pendingNavigation.push(wire);
                            console.log("PARK_ASSAULT_DEMOLITION_SUCCEEDED id=" + target.id
                                + " ride=" + tracked.configured.ride_id
                                + " revision=" + navigationRevision + " bw_tick=" + snapshot.bw_tick);
                        });
                    } else if (target.state !== "destroyed" && !tracked.failed) {
                        tracked.state = target.state;
                    }
                });
            }
            if (snapshot.v === 3) {
                snapshot.events.forEach(function (event) {
                    if (seenEvents[event.id]) return;
                    seenEvents[event.id] = true;
                    eventOrder.push(event.id);
                    if (eventOrder.length > 512) delete seenEvents[eventOrder.shift()];
                    console.log("RTS Bridge combat event=" + event.kind + " id=" + event.unit_id
                        + " value=" + event.value + " bw_tick=" + event.bw_tick);
                });
            }
            if (SIEGE_ENABLED || FRONTIER_ENABLED) {
                const target = snapshot.targets[0];
                if ((siege.proxyId && target.proxy_unit_id !== siege.proxyId)
                    || target.hp > siege.hp || (siege.state === "destroyed" && target.state !== "destroyed")) {
                    console.log("RIDE_SIEGE_ERROR rejected target identity or HP regression");
                    return;
                }
                siege.proxyId = target.proxy_unit_id;
                if (target.hp < siege.hp) {
                    console.log("RIDE_SIEGE_DAMAGE target=carousel-1 hp=" + target.hp
                        + " from=" + siege.hp + " bw_tick=" + snapshot.bw_tick);
                    siege.state = "damaged";
                }
                siege.hp = target.hp;
                if (target.state === "destroyed" && !siege.demolitionAttempted) {
                    if (!registeredCarousel() || registeredCarousel().id !== siege.rideId) {
                        console.log("RIDE_SIEGE_ERROR carousel identity changed before demolition");
                        return;
                    }
                    siege.demolitionAttempted = true;
                    siege.state = "destruction_pending";
                    console.log("RIDE_SIEGE_DEMOLITION_PENDING ride=" + siege.rideId
                        + " bw_tick=" + snapshot.bw_tick);
                    context.executeAction("ridedemolish", { ride: siege.rideId, modifyType: 0 }, function (result) {
                        if (result.error || map.getRide(siege.rideId) || carouselTracks(siege.rideId).length) {
                            siege.state = "damaged";
                            console.log("RIDE_SIEGE_DEMOLITION_FAILED ride=" + siege.rideId
                                + " error=" + (result.errorMessage || "ride or track remains"));
                        } else {
                            siege.state = "destroyed";
                            console.log("RIDE_SIEGE_DEMOLITION_SUCCEEDED ride=" + siege.rideId
                                + " bw_tick=" + snapshot.bw_tick);
                        }
                    });
                }
            }
            lastSeq = snapshot.seq;
            lastBwTick = snapshot.bw_tick;

            const units = snapshot.units.map(function (unit) {
                return {
                    id: unit.id,
                    kind: unit.kind,
                    owner: snapshot.v === 3 ? unit.owner : 0,
                    hp: snapshot.v === 3 ? unit.hp : 35,
                    max_hp: snapshot.v === 3 ? unit.max_hp : 35,
                    attack_frames: snapshot.v === 3 ? unit.attack_frames : 0,
                    x: Math.round((ASSAULT_ENABLED ? ASSAULT_CONFIG.transform.x
                        : (SIEGE_ENABLED || FRONTIER_ENABLED) ? -128 : ORIGIN_X) + unit.x * SCALE_X),
                    y: Math.round((ASSAULT_ENABLED ? ASSAULT_CONFIG.transform.y
                        : (SIEGE_ENABLED || FRONTIER_ENABLED) ? -96 : ORIGIN_Y) + unit.y * SCALE_Y),
                    facing: unit.facing,
                    motion: unit.motion
                };
            });
            const args = { session: session, seq: snapshot.seq, units: units };
            context.executeAction(ACTION, args, function (result) {
                if (result.error) console.log("RTS Bridge action failed: " + result.errorMessage);
            });
        }

        function connect() {
            if (socket !== null) return;
            let pending = "";
            const connection = network.createSocket();
            let connected = false;
            socket = connection;
            connection.on("data", function (data) {
                pending += data;
                if (pending.length > MAX_LINE * 2) {
                    console.log("RTS Bridge dropped oversized TCP buffer");
                    connection.destroy({});
                    return;
                }
                let newline;
                while ((newline = pending.indexOf("\n")) !== -1) {
                    const line = pending.slice(0, newline);
                    pending = pending.slice(newline + 1);
                    if (line.length > MAX_LINE || /[^\x20-\x7e]/.test(line)) {
                        console.log("RTS Bridge dropped oversized or non-ASCII snapshot");
                    } else if (line.length > 0) {
                        onLine(line);
                    }
                }
            });
            connection.on("error", function (error) {
                console.log("RTS Bridge socket error: " + error);
                // A refused connect need not deliver a close event by itself.
                // Destroy it so interval.tick can create a fresh socket.
                if (socket === connection) socket = null;
                connection.destroy({});
            });
            connection.on("close", function () {
                if (socket === connection) socket = null;
                if (connected && session) {
                    const clear = { session: session, seq: ++lastSeq, units: [] };
                    context.executeAction(ACTION, clear, function (result) {
                        if (result.error) console.log("RTS Bridge removal action failed: " + result.errorMessage);
                    });
                    console.log("RTS Bridge publisher disconnected; removed actors");
                }
            });
            connection.connect(PORT, "127.0.0.1", function () {
                connected = true;
                reconnectTicks = 0;
                console.log("RTS Bridge connected to BWAPI publisher on localhost");
                while (pendingNavigation.length) connection.write(pendingNavigation.shift());
            });
        }

        connect();
        connectCommands();
        context.subscribe("interval.tick", function () {
            if (socket === null && ++reconnectTicks >= 40) {
                reconnectTicks = 0;
                connect();
            }
            if (FRONTIER_ENABLED && commandSocket === null && animationTicks % 40 === 0)
                connectCommands();
        });
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
