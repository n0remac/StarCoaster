/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const COMMAND_ACTION = "rtsbridge.marineCommand";
    const RESULT_ACTION = "rtsbridge.commandResult";
    const BUILDING_ACTION = "rtsbridge.buildingState";
    const RESOURCE_ACTION = "rtsbridge.playerResources";
    const OUTCOME_ACTION = "rtsbridge.worldOutcome";
    const SCENARIO_STATUS_ACTION = "rtsbridge.scenarioStatus";
    const TARGET_ACTION = "rtsbridge.targetCatalog";
    const ACTOR_LIFECYCLE_ACTION = "rtsbridge.actorLifecycle";
    const CLIENT_READY_ACTION = "rtsbridge.clientReady";
    const SPAWN_ACTION = "rtsbridge.spawnMarine";
    const SPAWN_STATUS_ACTION = "rtsbridge.spawnStatus";
    const WAVE_ACTION = "rtsbridge.requestWave";
    const WAVE_STATUS_ACTION = "rtsbridge.waveStatus";
    const DEFENSE_ACTION = "rtsbridge.configureDefense";
    const DEFENSE_RESULT_ACTION = "rtsbridge.defenseResult";
    const PARK_CATALOG_ACTION = "rtsbridge.parkCatalog";
    const PARK_LOAD_ACTION = "rtsbridge.loadPark";
    const PARK_LOAD_STATUS_ACTION = "rtsbridge.parkLoadStatus";
    // Supported integration types only. Native rules remain in OpenBW.
    // BEGIN GENERATED STARCRAFT TYPES
    const UNIT_TYPES = Object.freeze({
        terran_marine: { name: "Marine", visual: "terran_marine", race: "terran", controllable: true, movement: "ground", spawnable: true, commands: ["move", "attack", "attack_move", "hold", "stop"] },
        terran_firebat: { name: "Firebat", visual: "terran_firebat", race: "terran", controllable: true, movement: "ground", spawnable: false, commands: ["move", "attack", "attack_move", "hold", "stop"] },
        terran_medic: { name: "Medic", visual: "terran_medic", race: "terran", controllable: true, movement: "ground", spawnable: false, commands: ["move", "attack_move", "hold", "stop", "heal"] },
        terran_vulture: { name: "Vulture", visual: "terran_vulture", race: "terran", controllable: true, movement: "ground", spawnable: false, commands: ["move", "attack", "attack_move", "hold", "stop"] },
        terran_goliath: { name: "Goliath", visual: "terran_goliath", race: "terran", controllable: true, movement: "ground", spawnable: false, commands: ["move", "attack", "attack_move", "hold", "stop"] },
        zerg_zergling: { name: "Zergling", visual: "zerg_zergling", race: "zerg", controllable: false, movement: "ground", spawnable: true, commands: [] },
        zerg_hydralisk: { name: "Hydralisk", visual: "zerg_hydralisk", race: "zerg", controllable: false, movement: "ground", spawnable: true, commands: [] },
        zerg_ultralisk: { name: "Ultralisk", visual: "zerg_ultralisk", race: "zerg", controllable: false, movement: "ground", spawnable: true, commands: [] },
        zerg_larva: { name: "Larva", visual: "zerg_larva", race: "zerg", controllable: false, movement: "ground", spawnable: false, commands: [] },
        zerg_egg: { name: "Egg", visual: "zerg_egg", race: "zerg", controllable: false, movement: "ground", spawnable: false, commands: [] },
    });
    const BUILDING_TYPES = Object.freeze({
        terran_barracks: { name: "Terran Barracks", objectID: "starcoaster.scenery_large.terran_barracks", width: 4, height: 3, maxHealth: 1000, production: ["terran_marine", "terran_firebat", "terran_medic"], animation: {"trigger":"training","frames":7,"ticks_per_frame":3} },
        terran_academy: { name: "Terran Academy", objectID: "starcoaster.scenery_large.terran_academy", width: 3, height: 2, maxHealth: 600, production: [], animation: null },
        terran_supply_depot: { name: "Terran Supply Depot", objectID: "starcoaster.scenery_large.terran_supply_depot", width: 3, height: 2, maxHealth: 500, production: [], animation: null },
        terran_factory: { name: "Terran Factory", objectID: "starcoaster.scenery_large.terran_factory", width: 4, height: 3, maxHealth: 1250, production: ["terran_vulture", "terran_goliath"], animation: null },
        terran_armory: { name: "Terran Armory", objectID: "starcoaster.scenery_large.terran_armory", width: 3, height: 2, maxHealth: 750, production: [], animation: null },
        zerg_hatchery: { name: "Zerg Hatchery", objectID: "starcoaster.scenery_large.zerg_hatchery", width: 4, height: 3, maxHealth: 1250, production: ["zerg_zergling"], animation: null },
        zerg_spawning_pool: { name: "Zerg Spawning Pool", objectID: "starcoaster.scenery_large.zerg_spawning_pool", width: 3, height: 2, maxHealth: 750, production: [], animation: null },
    });
    // END GENERATED STARCRAFT TYPES
    const COMMAND_ICON_IMAGES = Object.freeze({"empty": 29357, "terran_firebat": 30696, "terran_goliath": 30697, "terran_marine": 30698, "terran_medic": 30699, "terran_vulture": 30700, "zerg_zergling": 30701});
    const buildingByObject = {};
    Object.keys(BUILDING_TYPES).forEach(function (id) {
        const definition = BUILDING_TYPES[id];
        if (!definition.objectID || definition.width < 1 || definition.height < 1
            || buildingByObject[definition.objectID]
            || definition.production.some(function (unit) { return !UNIT_TYPES[unit]; }))
            throw new Error("Invalid StarCraft building definition: " + id);
        buildingByObject[definition.objectID] = id;
    });
    function controllable(unit, owner) {
        return !!unit && !!UNIT_TYPES[unit.kind] && UNIT_TYPES[unit.kind].controllable
            && unit.owner === owner && unit.hp > 0;
    }
    let terranOwner = 1, markOwnerChange = function () {};
    let commanderPlayer = -1;
    function electCommander() {
        if (network.mode !== "server" || !Array.isArray(network.players)) return commanderPlayer;
        const connected = network.players.map(function (player) { return player.id; });
        const host = network.currentPlayer.id;
        const clients = connected.filter(function (id) { return id !== host; }).sort(function (a, b) { return a - b; });
        if (commanderPlayer >= 0 && connected.includes(commanderPlayer)) return commanderPlayer;
        commanderPlayer = clients.length ? clients[0] : -1;
        return commanderPlayer;
    }

    function startWorldAdapter(onCommandSender, onCommandResult, onEntities, onTargets, onActor,
                               onSpawnSender, onSpawnStatus, onWaveSender, onWaveStatus, onDefenseSender, onDefenseResult,
                               onParkSender, onParkCatalog, onParkLoadStatus) {
        const session = Array.from({ length: 4 }, function () {
            return Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, "0");
        }).join("");
        let revision = 1, serial = 0, socket = null, buffer = "", inFlight = null, lastCombatSeq = 0, retryTicks = 0;
        let parkCatalogAvailable = false;
        let inFlightTicks = 0;
        const queue = [], generations = {}, activeKeys = {}, activeItems = {}, entities = {}, completed = {};
        const parkStorage = typeof context.getParkStorage === "function" ? context.getParkStorage() : null;
        const savedBarracksGenerations = parkStorage ? (parkStorage.get("barracksGenerations", {}) || {}) : {};
        const savedBarracksHealth = parkStorage ? (parkStorage.get("barracksHealth", {}) || {}) : {};
        const scenarioStructures = parkStorage ? (parkStorage.get("scenarioStructures", []) || []) : [];
        const scenarioAt = {};
        scenarioStructures.forEach(function (structure) {
            if (!structure || typeof structure.id !== "string" || !BUILDING_TYPES[structure.type]
                || !Number.isInteger(structure.x) || !Number.isInteger(structure.y)
                || !Number.isInteger(structure.z) || ![0, 1].includes(structure.owner))
                throw new Error("Invalid scenario structure ownership");
            scenarioAt[structure.type + ":" + structure.x + ":" + structure.y + ":" + structure.z] = structure;
        });
        if (parkStorage && parkStorage.get("barracksHealthMode", "proxy") !== "native") {
            const barracksObject = typeof objectManager === "object"
                ? objectManager.getAllObjects("large_scenery").find(function (object) {
                    return object.identifier === BUILDING_TYPES.terran_barracks.objectID;
                }) : null;
            Object.keys(savedBarracksHealth).forEach(function (id) {
                const hp = savedBarracksHealth[id];
                if (barracksObject && id.startsWith("openrct2:large_scenery:"
                    + barracksObject.index + ":") && Number.isInteger(hp) && hp > 0)
                    savedBarracksHealth[id] = Math.min(1000, hp * 25);
            });
            parkStorage.set("barracksHealth", savedBarracksHealth);
            parkStorage.set("barracksHealthMode", "native");
        }
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
        context.subscribe("action.query", function (event) {
            if (!event || !event.result || event.result.error || !constructionActions[event.action]
                || (network.mode === "server" && event.player === network.currentPlayer.id)
                || !scenarioStructures.length) return;
            const args = event.args || {};
            if (!Number.isInteger(args.x) && !Number.isInteger(args.x1)) return;
            const x1 = Number.isInteger(args.x1) ? args.x1 : args.x;
            const y1 = Number.isInteger(args.y1) ? args.y1 : args.y;
            const x2 = Number.isInteger(args.x2) ? args.x2 : x1;
            const y2 = Number.isInteger(args.y2) ? args.y2 : y1;
            if (![x1, y1, x2, y2].every(Number.isInteger)) return;
            const left = Math.floor(Math.min(x1, x2) / 32), right = Math.floor(Math.max(x1, x2) / 32);
            const top = Math.floor(Math.min(y1, y2) / 32), bottom = Math.floor(Math.max(y1, y2) / 32);
            if (scenarioStructures.some(function (structure) {
                const building = BUILDING_TYPES[structure.type];
                if (structure.owner === terranOwner || !building) return false;
                const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                    return item.identifier === building.objectID;
                });
                if (!object) return false;
                const tile = map.getTile(structure.x, structure.y);
                let present = false;
                for (let i = 0; i < tile.numElements; i++) {
                    const element = tile.getElement(i);
                    if (element.type === "large_scenery" && element.object === object.index
                        && element.baseHeight * 8 === structure.z) present = true;
                }
                return present
                    && left < structure.x + building.width && right >= structure.x
                    && top < structure.y + building.height && bottom >= structure.y;
            })) {
                console.log("WORLD_ENEMY_STRUCTURE_BLOCK player=" + event.player
                    + " action=" + event.action);
                event.result.error = 1;
                event.result.errorTitle = "Enemy structure";
                event.result.errorMessage = "Enemy structures must be destroyed in combat";
            }
        });
        const CONSTRUCTION_DEBOUNCE_TICKS = 6, RECONCILE_TICKS = 1200;
        const MAX_CHANGE_OPERATIONS = 4096, MAX_CHANGE_BYTES = 4194304;
        const MAX_WIRE_PAYLOAD_BYTES = 900000;
        function serializedBytes(value) {
            const json = JSON.stringify(value);
            if (!/[^\x00-\x7f]/.test(json)) return json.length;
            let bytes = 0;
            for (let i = 0; i < json.length; i++) {
                const code = json.charCodeAt(i);
                if (code < 0x80) bytes++;
                else if (code < 0x800) bytes += 2;
                else if (code >= 0xd800 && code <= 0xdbff && i + 1 < json.length
                    && json.charCodeAt(i + 1) >= 0xdc00 && json.charCodeAt(i + 1) <= 0xdfff) {
                    bytes += 4; i++;
                } else bytes += 3;
            }
            return bytes;
        }
        let constructionTick = 0, dirtySince = -1, publishedWorld = null, snapshotWorld = null;
        let detectedBatch = null, detectedSignature = "", combatRemovalKey = "", patchInFlight = null;
        let combatSyncID = "", recoveringRejectedBarracks = false, retryRejectedBarracks = null;
        const queuedCombatEvents = [];
        const pendingCommands = [];
        let patchSerial = 0;
        let firstConstructionAt = 0;
        function envelope(kind, payload, rev) {
            return { v: 1, kind: kind, session: session, op_id: "park:" + (++serial),
                source: "openrct2", revision: rev || revision, payload: payload };
        }
        function sendNext() {
            if (!socket || inFlight || !queue.length) return;
            inFlight = queue.shift();
            inFlightTicks = 0;
            if (inFlight.kind === "combat.command")
                console.log("WORLD_COMMAND_SENT id=" + inFlight.payload.command_id
                    + " request=" + inFlight.payload.request_id + " queue=" + queue.length);
            socket.write(JSON.stringify(inFlight) + "\n");
        }
        function send(kind, payload, rev) { queue.push(envelope(kind, payload, rev)); sendNext(); }
        function flushCommands() {
            if (!socket || patchInFlight || combatSyncID || snapshotWorld) return;
            while (pendingCommands.length) send("combat.command", pendingCommands.shift());
        }
        onCommandSender(function (payload) {
            if (!socket || patchInFlight || combatSyncID || snapshotWorld) {
                console.log("WORLD_COMMAND_WAIT id=" + payload.command_id
                    + " patch=" + !!patchInFlight + " combat=" + !!combatSyncID
                    + " snapshot=" + !!snapshotWorld + " socket=" + !!socket);
                if (pendingCommands.length >= 128) {
                    onCommandResult({ command_id: payload.command_id, player_id: payload.player_id,
                        request_id: payload.request_id, accepted: false, reason: "update_command_queue_full" });
                    return;
                }
                pendingCommands.push(payload);
            } else send("combat.command", payload);
        });
        const knownSpawns = {};
        onSpawnSender(function (payload) {
            knownSpawns[payload.request_id] = true;
            send("unit.spawn.request", payload);
        });
        onWaveSender(function (payload) { send("scenario.wave.request", payload); });
        onDefenseSender(function (payload) { send("scenario.defense.request", payload); });
        onParkSender(function (payload) { send("park.load.request", payload); });
        function rotate(offset, direction) {
            if (direction === 1) return { x: offset.y, y: -offset.x };
            if (direction === 2) return { x: -offset.x, y: -offset.y };
            if (direction === 3) return { x: -offset.y, y: offset.x };
            return { x: offset.x, y: offset.y };
        }
        function rideCollisionVolumes(element, ride, x, y, groundHeight) {
            // Entrance elements share this geometry path but OpenRCT2 logs a
            // scripting error when a TrackElement-only property is read.
            const trackType = element.type === "track" && Number.isInteger(element.trackType)
                ? element.trackType : -1;
            const sequence = Number.isInteger(element.sequence) ? element.sequence : 0;
            const direction = Number.isInteger(element.direction) ? element.direction : 0;
            const baseZ = Number.isInteger(element.baseZ) ? element.baseZ : element.baseHeight * 8;
            const clearanceZ = Number.isInteger(element.clearanceZ) ? element.clearanceZ
                : Number.isInteger(element.clearanceHeight) ? element.clearanceHeight * 8 : baseZ + 32;
            const quadrants = (element.occupiedQuadrants & 15) || 15;
            const rect = { x: x * 32, y: y * 32, width: 32, height: 32 };
            const tag = element.type === "entrance" ? "entrance:" : "track:";
            const source = tag + trackType + ":" + sequence + ":" + direction;
            const building = ride.classification === "stall" || ride.classification === "facility";
            // Ride type 19 uses the pinned CorkscrewRollerCoaster painter whose
            // flat and 25-degree rail geometry is inspected for this profile.
            const verifiedCoaster = ride.type === 19;
            const station = trackType >= 1 && trackType <= 3;
            // Entrances have a 28x28 painted body and an object-specific support.
            // Shops and facilities have substantial bodies even if a ride uses a
            // flat internal track tile. Their unknown support shape stays blocked.
            if (element.type === "entrance" || building || station) return [{
                rect: rect, base_z: Math.min(baseZ, groundHeight),
                clearance_z: Math.max(baseZ + 32, clearanceZ), occupied_quadrants: quadrants,
                classification: "approximate", source: source + (element.type === "entrance"
                    ? ":ride_entrance_exit" : building ? ":solid_building" : ":station_approx")
            }];
            const flatCurve = (trackType === 16 || trackType === 17) && sequence >= 0 && sequence <= 6
                || (trackType === 42 || trackType === 43) && sequence >= 0 && sequence <= 3;
            if (trackType === 0 || verifiedCoaster && flatCurve) return [{
                rect: rect, base_z: baseZ, clearance_z: baseZ + 8,
                occupied_quadrants: quadrants, classification: "approximate",
                source: source + (flatCurve ? ":flat_curve_unrepresented_supports" : ":unrepresented_supports")
            }];
            // The pinned descriptor gives up25/down25 a 16-Z endpoint delta.
            // Four strips enclose the rail's local rise; +8 retains the same
            // conservative rail thickness used for flat track. Direction is
            // OpenRCT2 travel direction (0=-X, 1=+Y, 2=+X, 3=-Y).
            if (verifiedCoaster && (trackType === 4 || trackType === 10)
                    && sequence === 0 && direction >= 0 && direction <= 3) {
                const volumes = [];
                for (let strip = 0; strip < 4; strip++) {
                    const r = { x: x * 32, y: y * 32, width: 32, height: 32 };
                    if (direction === 0 || direction === 2) { r.x += strip * 8; r.width = 8; }
                    else { r.y += strip * 8; r.height = 8; }
                    const progress = direction === 0 || direction === 3 ? 3 - strip : strip;
                    const lowStep = trackType === 4 ? progress : 3 - progress;
                    volumes.push({ rect: r, base_z: baseZ + lowStep * 4,
                        clearance_z: baseZ + (lowStep + 1) * 4 + 8,
                        occupied_quadrants: 15, classification: "approximate",
                        source: source + ":slope_25_rail:" + strip + ":unrepresented_supports" });
                }
                return volumes;
            }
            return [{ rect: rect, base_z: Math.min(baseZ, groundHeight),
                clearance_z: Math.max(baseZ + 32, clearanceZ), occupied_quadrants: quadrants,
                classification: "approximate", source: source + ":unknown_track_shape" }];
        }
        function readPark() {
            const grouped = {}, terrain = [], rides = {};
            map.rides.forEach(function (ride) {
                rides[ride.id] = { ride: ride, cells: [], volumes: [], height: null };
            });
            const largeObjects = typeof objectManager === "object" ? objectManager.getAllObjects("large_scenery") : [];
            const largeByIndex = {};
            largeObjects.forEach(function (object) { largeByIndex[object.index] = object; });
            const smallByIndex = {};
            if (typeof objectManager === "object") objectManager.getAllObjects("small_scenery").forEach(function (object) {
                smallByIndex[object.index] = object;
            });
            const names = {};
            if (typeof objectManager === "object") ["small_scenery", "wall", "large_scenery"].forEach(function (kind) {
                names[kind] = {};
                objectManager.getAllObjects(kind).forEach(function (object) { names[kind][object.index] = object.identifier; });
            });
            for (let y = 0; y < map.size.y; ++y) for (let x = 0; x < map.size.x; ++x) {
                const tile = map.getTile(x, y), duplicates = {};
                let ground = null;
                const pathLayers = [];
                for (let s = 0; s < tile.numElements; ++s) {
                    const surface = tile.getElement(s);
                    if (surface.type === "surface") {
                        ground = { x: x, y: y, height: surface.baseZ === undefined
                                ? surface.baseHeight * 8 : surface.baseZ,
                            slope: Number.isInteger(surface.slope) ? surface.slope : 0,
                            water: surface.waterHeight || 0, surface: surface.surfaceObject || 0,
                            walkable: !surface.waterHeight };
                        break;
                    }
                }
                for (let n = 0; n < tile.numElements; ++n) {
                    const element = tile.getElement(n), kind = element.type;
                    if (element.isGhost) continue;
                    if (kind === "surface") continue;
                    if (kind === "footpath") pathLayers.push({
                        base_height: element.baseZ === undefined ? element.baseHeight * 8 : element.baseZ,
                        slope_direction: Number.isInteger(element.slopeDirection) ? element.slopeDirection : null,
                        clearance_height: Number.isInteger(element.clearanceZ) ? element.clearanceZ
                            : Number.isInteger(element.clearanceHeight) ? element.clearanceHeight * 8
                                : (element.baseHeight * 8 + 32),
                        occupied_quadrants: (element.occupiedQuadrants & 15) || 15
                    });
                    if (kind === "track" || (kind === "entrance" && rides[element.ride])) {
                        if (rides[element.ride]) {
                            rides[element.ride].cells.push({ x: x, y: y });
                            if (rides[element.ride].height === null) rides[element.ride].height = element.baseHeight * 8;
                            rides[element.ride].volumes.push.apply(rides[element.ride].volumes,
                                rideCollisionVolumes(element, rides[element.ride].ride, x, y,
                                    ground ? ground.height : element.baseHeight * 8));
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
                        const identifier = (names[kind] && names[kind][object]) || String(object);
                        const buildingID = kind === "large_scenery" ? buildingByObject[identifier] : null;
                        const building = buildingID && BUILDING_TYPES[buildingID];
                        grouped[key] = { key: key, kind: building ? "structure" : kind === "footpath" ? "path" : kind,
                            type: building ? buildingID : kind === "footpath" ? String(element.surfaceObject || object)
                                : identifier,
                            name: building ? building.name : "",
                            x: anchorX, y: anchorY, z: anchorZ, direction: direction,
                            cells: [], rects: [], volumes: [], removal: removal };
                    }
                    grouped[key].cells.push({ x: x, y: y });
                    // Match Paint.Wall.cpp's tile edges: 0 west, 1 south,
                    // 2 east, 3 north. The rectangle is also OpenBW's mask.
                    if (kind === "wall") grouped[key].rects.push(direction === 0
                        ? { x: x * 32, y: y * 32, width: 4, height: 32 }
                        : direction === 1 ? { x: x * 32, y: y * 32 + 28, width: 32, height: 4 }
                        : direction === 2 ? { x: x * 32 + 28, y: y * 32, width: 4, height: 32 }
                        : { x: x * 32, y: y * 32, width: 32, height: 4 });
                    if (kind === "wall") grouped[key].volumes.push({
                        rect: grouped[key].rects[grouped[key].rects.length - 1],
                        base_z: z,
                        clearance_z: Number.isInteger(element.clearanceZ) ? element.clearanceZ
                            : Number.isInteger(element.clearanceHeight) ? element.clearanceHeight * 8 : z + 32,
                        occupied_quadrants: 15, classification: "physical", source: "wall:" + object + ":" + direction
                    });
                    if (kind === "small_scenery" || kind === "large_scenery") {
                        const definition = kind === "small_scenery" ? smallByIndex[object] : largeByIndex[object];
                        const part = kind === "large_scenery" && definition && definition.tiles
                            ? definition.tiles[element.sequence] : null;
                        // SmallSceneryFlag::hasNoSupports is bit 20 in the pinned enum.
                        const noSupports = kind === "small_scenery" ? !!(definition && (definition.flags & (1 << 20)))
                            : !!(part && part.hasSupports === false);
                        const clearanceZ = Number.isInteger(element.clearanceZ) ? element.clearanceZ
                            : Number.isInteger(element.clearanceHeight) ? element.clearanceHeight * 8 : z + 32;
                        grouped[key].volumes.push({
                            rect: { x: x * 32, y: y * 32, width: 32, height: 32 },
                            base_z: noSupports ? z : Math.min(z, ground ? ground.height : z),
                            clearance_z: Math.max(z + 8, clearanceZ),
                            occupied_quadrants: (element.occupiedQuadrants & 15) || 15,
                            classification: "approximate",
                            source: kind + ":" + object + ":" + (kind === "large_scenery" ? element.sequence : quadrant)
                                + (noSupports ? ":no_supports" : ":unknown_scenery_shape:support_fallback")
                        });
                    }
                }
                if (ground) {
                    if (pathLayers.length) ground.path_layers = pathLayers;
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
                    cells: item.cells, rects: [], volumes: item.volumes, removal: { action: "ridedemolish", args: { ride: ride.id, modifyType: 0 } },
                    rideId: ride.id, rideType: ride.type };
            });
            return { grouped: grouped, terrain: terrain, rides: rides };
        }
        function discover() {
            const read = readPark(), grouped = read.grouped, terrain = read.terrain;
            const now = {}, result = [];
            Object.keys(grouped).sort().forEach(function (key) {
                const item = grouped[key]; now[key] = true;
                if (!activeKeys[key]) {
                    generations[key] = item.kind === "structure"
                        ? Math.max((generations[key] || 0) + 1, savedBarracksGenerations[key] || 1)
                        : (generations[key] || 0) + 1;
                    if (item.kind === "structure" && parkStorage) {
                        savedBarracksGenerations[key] = generations[key];
                        parkStorage.set("barracksGenerations", savedBarracksGenerations);
                    }
                }
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
                const authored = item.kind === "structure"
                    ? scenarioAt[item.type + ":" + Math.floor(item.x / 32) + ":"
                        + Math.floor(item.y / 32) + ":" + item.z] : null;
                const id = authored ? "scenario:" + authored.id : "openrct2:" + key + "#" + generations[key];
                const entity = { id: id, source: "openrct2", source_id: key, kind: item.kind,
                    type: item.type, owner: item.kind === "structure"
                        ? (authored ? authored.owner : terranOwner) : 0,
                    position: { x: Math.max(0, minX), y: Math.max(0, minY) },
                    rotation: item.direction || 0, elevation: item.z,
                    geometry: { cells: sortedCells, rects: item.kind === "wall" ? item.rects.slice().sort(function (a, b) {
                        return a.y - b.y || a.x - b.x || a.width - b.width || a.height - b.height;
                    }) : rects },
                    collision: { blocks: item.kind !== "path" },
                    destructible: true,
                    combat: { targetable: item.kind !== "path",
                        health: item.kind === "structure" ? savedBarracksHealth[id]
                            || BUILDING_TYPES[item.type].maxHealth : 100 },
                    removal: item.removal, revision: revision };
                if (item.name) entity.name = item.name;
                if (item.kind !== "path" && item.volumes && item.volumes.length) {
                    const volumes = item.volumes.slice().sort(function (a, b) {
                        return a.rect.y - b.rect.y || a.rect.x - b.rect.x || a.base_z - b.base_z
                            || a.clearance_z - b.clearance_z || a.occupied_quadrants - b.occupied_quadrants
                            || a.source.localeCompare(b.source);
                    });
                    entity.collision = { blocks: true, mode: "height_aware", volumes: volumes.filter(function (v, i) {
                        return !i || JSON.stringify(v) !== JSON.stringify(volumes[i - 1]);
                    }) };
                }
                item.id = id; item.entity = entity;
                item.activeTarget = !!(entities[id] && entities[id].activeTarget);
                entities[id] = item; activeItems[key] = item; result.push(entity);
            });
            // A ride with no remaining track still owns its native ride ID.
            // Its next track edit must retain the same logical generation.
            Object.keys(read.rides).forEach(function (id) { now["ride:" + id] = true; });
            Object.keys(activeKeys).forEach(function (key) { if (!now[key]) {
                if (activeItems[key] && activeItems[key].kind === "structure" && parkStorage) {
                    savedBarracksGenerations[key] = (generations[key] || 1) + 1;
                    parkStorage.set("barracksGenerations", savedBarracksGenerations);
                    delete savedBarracksHealth[activeItems[key].id];
                    parkStorage.set("barracksHealth", savedBarracksHealth);
                }
                delete activeKeys[key]; delete activeItems[key];
            } });
            terrain.forEach(function (cell) {
                if (cell.path_layers) cell.path_layers.sort(function (a, b) {
                    return a.base_height - b.base_height
                        || (a.slope_direction === null ? -1 : a.slope_direction)
                        - (b.slope_direction === null ? -1 : b.slope_direction)
                        || a.occupied_quadrants - b.occupied_quadrants;
                });
            });
            return { entities: result, terrain: terrain };
        }
        function publishActiveTargets() {
            onTargets(session, Object.keys(entities).filter(function (id) {
                return entities[id].activeTarget === true;
            }).sort().map(function (id) {
                return { id: id, type: entities[id].entity.type, rects: entities[id].entity.geometry.rects,
                    health: entities[id].health === undefined ? entities[id].entity.combat.health : entities[id].health };
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
        markOwnerChange = markConstruction;
        function detectConstruction() {
            if (!publishedWorld) return;
            const discoveryStarted = Date.now();
            const current = discover(), changes = compareWorld(publishedWorld, current);
            const operations = changes.additions.length + changes.modifications.length
                + changes.removals.length + changes.terrain.length;
            if (operations > MAX_CHANGE_OPERATIONS || serializedBytes(changes) > MAX_CHANGE_BYTES) {
                console.log("WORLD_CHANGESET_OVERFLOW operations=" + operations + " recovery=snapshot");
                detectedBatch = null; detectedSignature = ""; dirtySince = -1;
                snapshot();
                return;
            }
            if (changes.additions.length || changes.modifications.length || changes.removals.length
                || changes.terrain.length) {
                detectedBatch = { base_revision: revision, changes: changes, current: current,
                    detectedAt: Date.now(), actionAt: firstConstructionAt };
                const signature = JSON.stringify({ base_revision: revision, changes: changes });
                if (signature !== detectedSignature) {
                    detectedSignature = signature;
                    console.log("WORLD_CHANGESET " + JSON.stringify({ base_revision: revision,
                        additions: changes.additions.map(function (e) { return e.id; }),
                        modifications: changes.modifications.map(function (e) { return e.id; }),
                        removals: changes.removals, terrain: changes.terrain.length }));
                    console.log("WORLD_GEOMETRY_METRIC discovery_ms=" + (Date.now() - discoveryStarted)
                        + " volumes=" + current.entities.reduce(function (sum, entity) {
                            return sum + ((entity.collision.volumes || []).length);
                        }, 0));
                }
                if (!patchInFlight && !combatSyncID && !snapshotWorld) publishPatch(detectedBatch);
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
            const payloadBytes = serializedBytes(payload);
            if (payloadBytes > MAX_WIRE_PAYLOAD_BYTES) {
                console.log("WORLD_CHANGESET_OVERFLOW bytes=" + payloadBytes + " recovery=snapshot");
                snapshot(); return;
            }
            patchInFlight = { id: payload.patch_id, base: revision, current: batch.current,
                additions: payload.additions.filter(function (entity) {
                    return entity.kind === "structure" && !!BUILDING_TYPES[entity.type];
                }) };
            console.log("WORLD_PATCH_METRIC patch=" + payload.patch_id
                + " action_to_detection_ms=" + (batch.actionAt ? batch.detectedAt - batch.actionAt : -1)
                + " detection_to_patch_ms=" + (Date.now() - batch.detectedAt)
                + " payload_bytes=" + payloadBytes
                + " operations=" + (payload.counts.additions + payload.counts.modifications
                    + payload.counts.removals + payload.counts.terrain));
            firstConstructionAt = 0;
            send("world.patch", payload, nextRevision);
        }
        context.subscribe("action.execute", function (event) {
            if (!event || !event.result || event.result.error || event.isClientOnly
                || !constructionActions[event.action]) return;
            const action = event.action, args = event.args || {};
            if (!firstConstructionAt) firstConstructionAt = Date.now();
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
                if ((item.kind === kind || (kind === "large_scenery" && item.kind === "structure"))
                    && (item.cells.some(function (cell) { return cell.x === tileX && cell.y === tileY; })
                    || (item.removal.args && item.removal.args.x === args.x && item.removal.args.y === args.y)))
                    activeKeys[key] = false;
            });
        });
        function snapshot() {
            const discoveryStarted = Date.now();
            const current = discover(), chunks = [];
            let largestEntity = 0, largestEntityID = "", volumeCount = 0;
            current.entities.forEach(function (entity) {
                const bytes = serializedBytes(entity);
                if (bytes > largestEntity) { largestEntity = bytes; largestEntityID = entity.id; }
                volumeCount += (entity.collision.volumes || []).length;
            });
            if (largestEntity > MAX_WIRE_PAYLOAD_BYTES) {
                console.log("WORLD_ERROR entity_too_large id=" + largestEntityID + " bytes=" + largestEntity);
                if (socket) socket.destroy({});
                return;
            }
            snapshotWorld = current;
            onEntities(current.entities, session);
            let entityChunk = [];
            current.entities.forEach(function (entity) {
                const next = entityChunk.concat([entity]);
                if (entityChunk.length && (next.length > 32 || serializedBytes(next) > 48000)) {
                    chunks.push({ entities: entityChunk }); entityChunk = [entity];
                } else entityChunk = next;
            });
            if (entityChunk.length) chunks.push({ entities: entityChunk });
            for (let i = 0; i < current.terrain.length; i += 128)
                chunks.push({ terrain: current.terrain.slice(i, i + 128) });
            const maxChunk = chunks.reduce(function (size, chunk) {
                return Math.max(size, serializedBytes(chunk));
            }, 0);
            if (maxChunk > MAX_WIRE_PAYLOAD_BYTES) {
                console.log("WORLD_ERROR snapshot_chunk_too_large bytes=" + maxChunk);
                snapshotWorld = null;
                if (socket) socket.destroy({});
                return;
            }
            console.log("WORLD_GEOMETRY_METRIC discovery_ms=" + (Date.now() - discoveryStarted)
                + " volumes=" + volumeCount + " largest_entity_bytes=" + largestEntity
                + " max_snapshot_chunk_bytes=" + maxChunk);
            send("world.snapshot.begin", { width: map.size.x, height: map.size.y, chunks: chunks.length });
            chunks.forEach(function (chunk, index) { chunk.index = index; send("world.snapshot.chunk", chunk); });
            send("world.snapshot.end", { entities: current.entities.length, terrain: current.terrain.length });
            console.log("WORLD_SNAPSHOT session=" + session + " entities=" + current.entities.length
                + " terrain=" + current.terrain.length + " chunks=" + chunks.length);
        }
        function combatEvent(message) {
            const event = message.payload, tracked = entities[event.entity_id];
            if (message.session !== session || !tracked || completed[event.id] || event.health !== 0 || event.type !== "destruction") return;
            // Lock the ordered park revision before the OpenRCT2 action runs.
            // Its callback may arrive on a later tick, while other native
            // destruction events are already waiting in the socket buffer.
            combatSyncID = "combat:" + event.id;
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
        function rollbackRejectedBarracks(patch) {
            if (!patch.additions.length) return false;
            recoveringRejectedBarracks = true;
            const additions = patch.additions.slice();
            function removeNext() {
                if (!additions.length) {
                    recoveringRejectedBarracks = false;
                    console.log("WORLD_BARRACKS_ROLLBACK_COMPLETE patch=" + patch.id);
                    snapshot();
                    return;
                }
                const entity = additions.shift();
                const present = discover().entities.some(function (current) {
                    return current.source_id === entity.source_id && current.kind === "structure";
                });
                if (!present) { removeNext(); return; }
                const item = activeItems[entity.source_id];
                if (!item || item.kind !== "structure" || !item.removal) {
                    additions.unshift(entity);
                    retryRejectedBarracks = removeNext;
                    return;
                }
                context.executeAction(item.removal.action, item.removal.args, function (result) {
                    const remains = discover().entities.some(function (current) {
                        return current.source_id === entity.source_id && current.kind === "structure";
                    });
                    if (result.error || remains) {
                        console.log("WORLD_BARRACKS_ROLLBACK_ERROR id=" + entity.id
                            + " reason=" + (result.errorMessage || "object_still_present"));
                        additions.unshift(entity);
                        retryRejectedBarracks = removeNext;
                        return;
                    }
                    console.log("WORLD_BARRACKS_ROLLBACK id=" + entity.id);
                    removeNext();
                });
            }
            removeNext();
            return true;
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
                if (recoveringRejectedBarracks) return;
                console.log("WORLD_RESYNC reason=" + ((message.payload && message.payload.reason) || "unspecified"));
                queue.length = 0; inFlight = null; patchInFlight = null; combatSyncID = ""; snapshot();
            }
            else if (message.kind === "world.patch.status" && message.payload && combatSyncID
                && message.payload.patch_id === combatSyncID) {
                if (message.payload.state === "synchronized" && message.revision === revision) {
                    console.log("WORLD_COMBAT_PATCH_SYNC revision=" + revision + " id=" + combatSyncID);
                    combatSyncID = "";
                    markConstruction();
                    while (queuedCombatEvents.length && !combatSyncID) combatEvent(queuedCombatEvents.shift());
                    flushCommands();
                } else if (message.payload.state === "failed" || message.payload.state === "unsynchronized") {
                    console.log("WORLD_COMBAT_PATCH_ERROR " + (message.payload.reason || message.payload.state));
                    queue.length = 0; inFlight = null; combatSyncID = ""; snapshot();
                }
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
                    while (queuedCombatEvents.length && !combatSyncID) combatEvent(queuedCombatEvents.shift());
                    flushCommands();
                    console.log("WORLD_PATCH_SYNC revision=" + revision);
                    if (message.payload.unsupported_total)
                        console.log("WORLD_TARGET_UNSUPPORTED total=" + message.payload.unsupported_total
                            + " reasons=" + JSON.stringify(message.payload.unsupported_reasons || {}));
                } else if (message.payload.state === "failed" || message.payload.state === "unsynchronized") {
                    const failed = patchInFlight;
                    const reason = message.payload.reason || message.payload.state;
                    console.log("WORLD_PATCH_ERROR " + reason);
                    queue.length = 0; inFlight = null; patchInFlight = null;
                    if (!reason.includes("occupied_construction_geometry")
                        || !rollbackRejectedBarracks(failed)) snapshot();
                }
            }
            else if (message.kind === "combat.event") {
                if (patchInFlight || combatSyncID || snapshotWorld) queuedCombatEvents.push(message);
                else combatEvent(message);
            }
            else if (message.kind === "combat.result" && message.payload.command_id) onCommandResult(message.payload);
            else if (message.kind === "building.state" && message.payload)
                context.executeAction(BUILDING_ACTION, Object.assign({ session: session }, message.payload),
                    function (result) {
                        if (result.error) console.log("WORLD_BUILDING_STATE_ERROR " + result.errorMessage);
                    });
            else if (message.kind === "player.resources" && message.payload)
                context.executeAction(RESOURCE_ACTION, Object.assign({ session: session }, message.payload),
                    function (result) {
                        if (result.error) console.log("WORLD_PLAYER_RESOURCES_ERROR " + result.errorMessage);
                    });
            else if (message.kind === "unit.spawn.status" && message.payload) onSpawnStatus(message.payload);
            else if (message.kind === "scenario.wave.status" && message.payload) onWaveStatus(message.payload);
            else if (message.kind === "scenario.defense.result" && message.payload) onDefenseResult(message.payload);
            else if (message.kind === "park.catalog" && message.payload) {
                parkCatalogAvailable = true;
                onParkCatalog(message.payload);
            }
            else if (message.kind === "park.load.status" && message.payload) {
                onParkLoadStatus(message.payload);
                if (!message.payload.accepted) send("park.catalog.request", {});
            }
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
                    return item ? { id: id, type: item.entity.type, rects: item.entity.geometry.rects,
                        health: item.health === undefined ? item.entity.combat.health : item.health } : null;
                }).filter(function (item) { return item !== null; });
                Object.keys(entities).forEach(function (id) { entities[id].activeTarget = false; });
                targets.forEach(function (item) { entities[item.id].activeTarget = true; });
                onTargets(session, targets);
                send("park.catalog.request", {});
                console.log("WORLD_READY entities=" + message.payload.entities
                    + " targets=" + message.payload.targets + " obstacles=" + message.payload.obstacles
                    + " navigation=" + message.payload.navigation
                    + " unsupported=" + (message.payload.unsupported_total || 0));
                Object.keys(knownSpawns).forEach(function (requestId) {
                    send("unit.spawn.query", { request_id: requestId });
                });
                flushCommands();
            }
            else if (message.kind === "world.outcome" && message.payload
                && ["victory", "defeat"].includes(message.payload.state))
                context.executeAction(OUTCOME_ACTION, { session: session,
                    scenario_id: message.payload.scenario_id, state: message.payload.state,
                    objective_id: message.payload.objective_id }, function (result) {
                    if (result.error) console.log("WORLD_OUTCOME_ERROR " + result.errorMessage);
                });
            else if (message.kind === "scenario.status" && message.payload)
                context.executeAction(SCENARIO_STATUS_ACTION, Object.assign({ commander_player: electCommander() }, message.payload), function (result) {
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
                    if (Number.isInteger(target.health)) {
                        entities[target.id].health = target.health;
                        if (entities[target.id].kind === "structure" && parkStorage) {
                            savedBarracksHealth[target.id] = target.health;
                            parkStorage.set("barracksHealth", savedBarracksHealth);
                        }
                    }
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
            connection.on("error", function (error) {
                console.log("WORLD_SOCKET_ERROR " + error);
                if (socket === connection) {
                    socket = null; inFlight = null; queue.length = 0;
                }
                connection.destroy({});
            });
            connection.on("close", function () {
                if (socket === connection) {
                    socket = null; inFlight = null; queue.length = 0;
                }
            });
            connection.connect(40010, "127.0.0.1", function () {
                retryTicks = 0;
                inFlight = null;
                queue.length = 0;
                patchInFlight = null;
                combatSyncID = "";
                queuedCombatEvents.length = 0;
                send("world.hello", { capabilities: ["snapshot", "world.patch", "navigation.mask"] });
                if (!recoveringRejectedBarracks) snapshot();
            });
        }
        connect();
        context.subscribe("interval.tick", function () {
            constructionTick++;
            if (retryRejectedBarracks && constructionTick % 120 === 0) {
                const retry = retryRejectedBarracks;
                retryRejectedBarracks = null;
                retry();
            }
            if (!socket && ++retryTicks >= 40) { retryTicks = 0; connect(); }
            if (socket && inFlight && inFlight.kind === "world.patch" && ++inFlightTicks >= 120) {
                inFlightTicks = 0;
                socket.write(JSON.stringify(inFlight) + "\n");
            }
            if (socket && patchInFlight && !inFlight && constructionTick % 120 === 0)
                send("world.patch.query", { patch_id: patchInFlight.id }, patchInFlight.base + 1);
            if (socket && combatSyncID && !inFlight && constructionTick % 120 === 0)
                send("world.patch.query", { patch_id: combatSyncID }, revision);
            if (socket && parkCatalogAvailable && constructionTick % 120 === 0)
                send("park.catalog.request", {});
            if (recoveringRejectedBarracks) return;
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
                && (unit.aim_facing === undefined || Number.isInteger(unit.aim_facing)
                    && unit.aim_facing >= 0 && unit.aim_facing <= 255)
                && (unit.motion === "idle" || unit.motion === "walk" || unit.motion === "attack"
                    || unit.motion === "heal" || unit.motion === "morph"
                    || unit.motion === "hatch" || unit.motion === "death")
                && (UNIT_TYPES[unit.kind]
                    && Number.isInteger(unit.owner) && unit.owner >= 0 && unit.owner <= 11
                    && Number.isInteger(unit.hp) && unit.hp >= 0
                    && Number.isInteger(unit.max_hp) && unit.max_hp >= unit.hp && unit.max_hp <= 10000
                    && (unit.energy === undefined || Number.isInteger(unit.energy) && unit.energy >= 0)
                    && Number.isInteger(unit.attack_frames) && unit.attack_frames >= 0);
        });
    }

    function main() {
        if (typeof rtsBridge !== "object" || rtsBridge.version !== 5 || rtsBridge.assetVersion !== 4
            || typeof rtsBridge.applySnapshot !== "function"
            || typeof rtsBridge.clearSnapshot !== "function"
            || typeof rtsBridge.invalidateAnimation !== "function"
            || typeof rtsBridge.setBuildingAnimations !== "function"
            || typeof rtsBridge.actorScreenPosition !== "function") {
            throw new Error("RTS Bridge needs the matching native OpenRCT2 build and asset pack");
        }
        rtsBridge.clearSnapshot();

        const buildingObjects = {};
        if (typeof objectManager === "object") {
            Object.keys(BUILDING_TYPES).forEach(function (id) {
                const identifier = BUILDING_TYPES[id].objectID;
                buildingObjects[id] = objectManager.getAllObjects("large_scenery").find(function (entry) {
                    return entry.identifier === identifier;
                }) || (typeof objectManager.load === "function" ? objectManager.load(identifier) : null);
            });
        }
        function targetBuildingID(id, target) {
            if (target && BUILDING_TYPES[target.type]) return target.type;
            return Object.keys(buildingObjects).filter(function (type) {
                const object = buildingObjects[type];
                return object && id.startsWith("openrct2:large_scenery:" + object.index + ":");
            })[0] || "";
        }

        let controlSession = "";
        let clearUiForMap = function () {};
        context.subscribe("map.change", function () {
            rtsBridge.clearSnapshot();
            controlSession = "";
            controlUnits = {};
            occupancyUnits = {};
            actorLifecycleSession = "";
            activeActorGenerations = {};
            removedActorGenerations = {};
            buildingStates = {};
            playerResources = {};
            worldTargetIds = {};
            targetCatalogSession = "";
            missionStatus = null;
            outcomeState = null;
            parkCatalog = null;
            parkLoadStatus = null;
            latestSnapshot = null;
            clientReadySession = "";
            pendingClientRefresh = false;
            pendingClientSnapshot = false;
            commandSerial = 0;
            targetCatalogVersion = 0;
            publishedTargets = [];
            queuedTargetCatalog = null;
            pendingTargetCatalog = null;
            defenseFeedback = "";
            waveFeedback = "";
            Object.keys(pendingCommands).forEach(function (id) { delete pendingCommands[id]; });
            Object.keys(seenCommandRequests).forEach(function (id) { delete seenCommandRequests[id]; });
            Object.keys(spawnStatuses).forEach(function (id) { delete spawnStatuses[id]; });
            Object.keys(productionFeedback).forEach(function (id) { delete productionFeedback[id]; });
            Object.keys(pendingTrainTypes).forEach(function (id) { delete pendingTrainTypes[id]; });
            clearUiForMap();
        });
        let controlUnits = {};
        let occupancyUnits = {};
        let actorLifecycleSession = "";
        let activeActorGenerations = {};
        let removedActorGenerations = {};
        const retiredActorSessions = {};
        let clientReadySession = "";
        let clientReadyPending = false;
        let pendingClientRefresh = false;
        let pendingClientSnapshot = false;
        let latestSnapshot = null;
        let onActorRemoved = function () {};
        function mayCommandBuilding(native) {
            return !!native && native.command_authorized;
        }
        let commandSerial = 0;
        let worldCommandSender = null;
        let worldSpawnSender = null;
        let worldWaveSender = null;
        let worldDefenseSender = null;
        let worldParkSender = null;
        let parkCatalog = null;
        let parkLoadStatus = null;
        let defenseFeedback = "";
        let waveFeedback = "";
        let waveFeedbackUntil = 0;
        const spawnStatuses = {};
        let worldTargetIds = {};
        let targetCatalogSession = "";
        let targetCatalogVersion = 0;
        let pendingTargetCatalog = null;
        let publishingTargetVersion = 0;
        let publishingTargetSession = "";
        let targetCatalogPublishing = false;
        let queuedTargetCatalog = null;
        const retiredTargetSessions = {};
        let publishedTargets = [];
        function publishTargetCatalog(session, targets) {
            publishedTargets = targets.slice();
            queuedTargetCatalog = { session: session, targets: publishedTargets };
            if (targetCatalogPublishing) return;
            publishNextTargetCatalog();
        }
        function publishNextTargetCatalog() {
            if (!queuedTargetCatalog) return;
            const request = queuedTargetCatalog;
            queuedTargetCatalog = null;
            const session = request.session, targets = request.targets;
            targetCatalogPublishing = true;
            if (session !== publishingTargetSession) {
                publishingTargetSession = session;
                publishingTargetVersion = 0;
            }
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
                targetCatalogPublishing = false;
                return;
            }
            const version = publishingTargetVersion = Math.max(publishingTargetVersion,
                session === targetCatalogSession ? targetCatalogVersion : 0) + 1;
            function sendChunk(index) {
                const items = chunks[index];
                context.executeAction(TARGET_ACTION, { session: session, version: version,
                    index: index, chunks: chunks.length, targets: items }, function (result) {
                    if (result.error) console.log("WORLD_TARGET_CATALOG_ERROR " + result.errorMessage);
                    if (!result.error && index + 1 < chunks.length) {
                        sendChunk(index + 1);
                    } else {
                        targetCatalogPublishing = false;
                        if (queuedTargetCatalog) publishNextTargetCatalog();
                    }
                });
            }
            sendChunk(0);
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
        const productionFeedback = {};
        const pendingTrainTypes = {};
        let buildingStates = {};
        let playerResources = {};
        function refreshBuildingAnimations() {
            if (!controlSession) return;
            Object.keys(BUILDING_TYPES).forEach(function (type) {
                const building = BUILDING_TYPES[type], object = buildingObjects[type];
                if (!object || !building.animation) return;
                const prefix = "openrct2:large_scenery:" + object.index + ":";
                const tiles = [];
                Object.keys(buildingStates).forEach(function (id) {
                    const state = buildingStates[id], target = worldTargetIds[id];
                    if (!id.startsWith(prefix) || !target || !state || state.session !== controlSession
                        || targetCatalogSession !== controlSession || state.health < 1 || state.queue < 1) return;
                    target.geometry.rects.forEach(function (rect) {
                        for (let y = rect.y; y < rect.y + rect.height; y += 32)
                            for (let x = rect.x; x < rect.x + rect.width; x += 32)
                                tiles.push({ x: x, y: y });
                    });
                });
                rtsBridge.setBuildingAnimations({ session: controlSession,
                    object: object.index, tiles: tiles, frames: building.animation.frames,
                    ticks_per_frame: building.animation.ticks_per_frame,
                    bank_stride: building.width * building.height * 4 });
            });
        }
        const pendingCommands = {};
        const seenCommandRequests = {};
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
            console.log("WORLD_SPAWN_STATUS request=" + args.request_id + " state=" + args.state
                + " ready=" + args.units.filter(function (unit) { return unit.state === "ready"; }).length);
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
                        && (activeActorGenerations[unit.id] > 0
                            || (removedActorGenerations[unit.id] > 0
                                && unit.motion === "death" && unit.hp === 0)));
            });
            rtsBridge.applySnapshot({ session: event.args.session, seq: event.args.seq, units: visible });
            if (network.mode === "server") latestSnapshot = { session: event.args.session,
                seq: event.args.seq, units: event.args.units };
            const sessionChanged = controlSession !== event.args.session;
            if (sessionChanged) {
                outcomeState = null; shownOutcome = "";
                buildingStates = {};
                if (missionStatus && missionStatus.session !== event.args.session) missionStatus = null;
            }
            controlSession = event.args.session;
            if (sessionChanged) playerResources = {};
            if (sessionChanged) refreshBuildingAnimations();
            controlUnits = {};
            visible.forEach(function (unit) { controlUnits[unit.id] = unit; });
            occupancyUnits = {};
            event.args.units.forEach(function (unit) { occupancyUnits[unit.id] = unit; });
            const playerUnit = event.args.units.filter(function (unit) {
                return UNIT_TYPES[unit.kind] && UNIT_TYPES[unit.kind].controllable;
            })[0];
            if (playerUnit && terranOwner !== playerUnit.owner) {
                terranOwner = playerUnit.owner;
                if (network.mode === "server") markOwnerChange();
            }
            return {};
        });


            context.registerAction(CLIENT_READY_ACTION, function (event) {
                const args = event.args;
                if (!args || (args.session !== controlSession && args.session !== "")
                    || (network.mode === "server" && args.session === "" && !latestSnapshot)
                    || (network.mode === "server"
                    && (!Array.isArray(network.players)
                        || !network.players.some(function (player) { return player.id === event.player; }))))
                    return { error: 1, errorMessage: "Invalid client readiness" };
                return {};
            }, function (event) {
                if (network.mode === "server") {
                    pendingClientRefresh = true;
                    if (event.args.session === "") pendingClientSnapshot = true;
                }
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
                            && (/^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(item.id)
                                || /^scenario:[a-z0-9-]{1,64}$/.test(item.id))
                            && (item.type === undefined || typeof item.type === "string")
                            && (item.health === undefined || (Number.isInteger(item.health)
                                && item.health >= 0 && item.health <= 1000000))
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
                    pendingTargetCatalog.targets[item.id] = { type: item.type || "", geometry: { rects: item.rects },
                        health: item.health === undefined ? 100 : item.health };
                });
                pendingTargetCatalog.next++;
                if (pendingTargetCatalog.next === pendingTargetCatalog.chunks) {
                    targetCatalogSession = args.session;
                    targetCatalogVersion = args.version;
                    worldTargetIds = pendingTargetCatalog.targets;
                    pendingTargetCatalog = null;
                    refreshBuildingAnimations();
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
                    || (args.mode !== undefined && !["", "park_defense"].includes(args.mode))
                    || !Number.isInteger(args.wave_ordinal) || args.wave_ordinal < 0 || args.wave_ordinal > 1000000000
                    || !Number.isInteger(args.wave_total) || args.wave_total < 0 || args.wave_total > 64
                    || (args.mode === "park_defense" && (
                        !Number.isInteger(args.total_triggered) || args.total_triggered < 0 || args.total_triggered > 1000000000
                        || !Number.isInteger(args.next_wave_seconds) || args.next_wave_seconds < 0 || args.next_wave_seconds > 1000000000
                        || !Number.isInteger(args.active_zerglings) || args.active_zerglings < 0 || args.active_zerglings > 256
                        || (args.active_enemies !== undefined && (!Number.isInteger(args.active_enemies)
                            || args.active_enemies < 0 || args.active_enemies > 256))
                        || !Number.isInteger(args.manual_cooldown_seconds) || args.manual_cooldown_seconds < 0 || args.manual_cooldown_seconds > 1000000000
                        || typeof args.manual_eligible !== "boolean"
                        || (args.defense_enabled !== undefined && typeof args.defense_enabled !== "boolean")
                        || (args.unlimited_resources !== undefined && typeof args.unlimited_resources !== "boolean")
                        || (args.wave_interval_seconds !== undefined && (!Number.isInteger(args.wave_interval_seconds) || args.wave_interval_seconds < 1))
                        || (args.wave_difficulty !== undefined && !["easy", "standard", "hard"].includes(args.wave_difficulty))
                        || (args.spawn_anchor !== undefined && (!Array.isArray(args.spawn_anchor) || args.spawn_anchor.length !== 2
                            || args.spawn_anchor.some(function (n) { return !Number.isInteger(n) || n < 0 || n > 256; })))
                        || (args.commander_player !== undefined && !Number.isInteger(args.commander_player))))
                    || (args.defense_configurable !== undefined && typeof args.defense_configurable !== "boolean")
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
            context.registerAction(WAVE_ACTION, function (event) {
                const args = event.args || {};
                if (parkCatalog && parkCatalog.phase !== "ready")
                    return { error: 1, errorMessage: "Park is changing" };
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
                        return { error: 1, errorMessage: "Only the Terran commander may spawn a wave" };
                    if (!worldWaveSender)
                        return { error: 1, errorMessage: "Wave bridge disconnected" };
                }
                if (args.session !== controlSession || !missionStatus
                    || missionStatus.session !== controlSession || missionStatus.mode !== "park_defense"
                    || !Number.isSafeInteger(args.request) || args.request < 1
                    || typeof args.request_id !== "string"
                    || args.request_id !== args.session + ":wave:" + event.player + ":" + args.request)
                    return { error: 1, errorMessage: "Invalid wave request" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                worldWaveSender({ request_id: event.args.request_id, player_id: event.player,
                    commander_id: commanderPlayer });
                return {};
            });
            context.registerAction(DEFENSE_ACTION, function (event) {
                const args = event.args || {};
                if (parkCatalog && parkCatalog.phase !== "ready")
                    return { error: 1, errorMessage: "Park is changing" };
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
                    if (event.player !== commanderPlayer) {
                        console.log("WORLD_DEFENSE_DENIED player=" + event.player
                            + " commander=" + commanderPlayer);
                        return { error: 1, errorMessage: "Only the Terran commander may configure defense" };
                    }
                    if (!worldDefenseSender)
                        return { error: 1, errorMessage: "Defense bridge disconnected" };
                }
                if (args.session !== controlSession || !missionStatus
                    || missionStatus.mode !== "park_defense"
                    || (typeof args.enabled !== "boolean" && args.anchor === undefined
                        && args.interval_seconds === undefined && args.difficulty === undefined)
                    || (args.anchor !== undefined && (!Array.isArray(args.anchor) || args.anchor.length !== 2
                        || args.anchor.some(function (n) { return !Number.isInteger(n) || n < 0 || n > 256; })))
                    || (args.interval_seconds !== undefined && (!Number.isInteger(args.interval_seconds)
                        || args.interval_seconds < 30 || args.interval_seconds > 600 || args.interval_seconds % 30 !== 0))
                    || (args.difficulty !== undefined && !["easy", "standard", "hard"].includes(args.difficulty)))
                    return { error: 1, errorMessage: "Invalid defense setting" };
                return {};
            }, function (event) {
                if (network.mode === "server") worldDefenseSender({ player_id: event.player,
                    commander_id: commanderPlayer, enabled: event.args.enabled, anchor: event.args.anchor,
                    interval_seconds: event.args.interval_seconds, difficulty: event.args.difficulty });
                return {};
            });
            context.registerAction(DEFENSE_RESULT_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report defense settings" };
                return typeof args.accepted === "boolean" && typeof args.reason === "string" && args.reason.length <= 128
                    ? {} : { error: 1, errorMessage: "Invalid defense result" };
            }, function (event) {
                defenseFeedback = event.args.accepted ? "Defense settings saved" : "Defense: " + event.args.reason;
                return {};
            });
            context.registerAction(PARK_CATALOG_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report available parks" };
                return ["running", "preparing", "switching", "starting", "ready", "failed"].includes(args.phase)
                    && typeof args.current === "string" && typeof args.pending === "string"
                    && typeof args.generation === "string" && /^[0-9a-f]{32}$/.test(args.generation)
                    && typeof args.error === "string" && args.error.length < 256
                    && Array.isArray(args.parks) && args.parks.length <= 256
                    && args.parks.every(function (name) {
                        return typeof name === "string" && /^[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.park$/.test(name);
                    }) ? {} : { error: 1, errorMessage: "Invalid park catalog" };
            }, function (event) {
                parkCatalog = event.args;
                return {};
            });
            context.registerAction(PARK_LOAD_STATUS_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report park changes" };
                return typeof args.accepted === "boolean" && typeof args.reason === "string"
                    && args.reason.length <= 128 && typeof args.park === "string"
                    && typeof args.generation === "string"
                    ? {} : { error: 1, errorMessage: "Invalid park transition status" };
            }, function (event) {
                parkLoadStatus = event.args;
                if (event.args.accepted && parkCatalog
                    && parkCatalog.generation === event.args.generation)
                    parkCatalog = Object.assign({}, parkCatalog,
                        { phase: "preparing", pending: event.args.park });
                if (event.args.accepted && typeof ui !== "undefined")
                    ui.showError("StarCoaster: changing park",
                        "Preparing " + event.args.park + ". Native clients can reconnect at the same server address when ready.");
                return {};
            });
            context.registerAction(PARK_LOAD_ACTION, function (event) {
                const args = event.args || {};
                if (!Array.isArray(network.players) || !network.players.some(function (player) {
                    return player.id === event.player;
                })) return { error: 1, errorMessage: "Player is not connected" };
                if (network.mode === "server") {
                    electCommander();
                    if (event.player !== commanderPlayer && event.player !== network.currentPlayer.id)
                        return { error: 1, errorMessage: "Only the commander or host may load a park" };
                    if (!worldParkSender) return { error: 1, errorMessage: "Park supervisor disconnected" };
                }
                if (!parkCatalog || parkCatalog.phase !== "ready"
                    || args.session !== controlSession || args.generation !== parkCatalog.generation
                    || !parkCatalog.parks.includes(args.park)
                    || !["save", "discard"].includes(args.decision))
                    return { error: 1, errorMessage: "Invalid or busy park transition" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;
                let saveName = "";
                if (args.decision === "save") {
                    const token = Array.from({ length: 4 }, function () {
                        return Math.floor(Math.random() * 0x10000).toString(16).padStart(4, "0");
                    }).join("");
                    saveName = "starcoaster-switch-" + token + ".park";
                    context.saveGame({ filename: saveName.slice(0, -5) });
                }
                worldParkSender({ park: args.park, decision: args.decision,
                    generation: args.generation, save_name: saveName,
                    player_id: event.player, commander_id: event.player });
                parkCatalog = Object.assign({}, parkCatalog, { phase: "preparing", pending: args.park });
                context.executeAction(PARK_CATALOG_ACTION, parkCatalog, function () {});
                return {};
            });
            context.registerAction(WAVE_STATUS_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may report wave requests" };
                return args.session === controlSession
                    && typeof args.request_id === "string" && args.request_id.length <= 128
                    && typeof args.accepted === "boolean" && typeof args.wave_id === "string"
                    && args.wave_id.length <= 64 && ["queued", "rejected"].includes(args.state)
                    && typeof args.reason === "string" && args.reason.length <= 128
                    ? {} : { error: 1, errorMessage: "Invalid wave status" };
            }, function (event) {
                const args = event.args;
                waveFeedback = args.accepted ? "Wave " + args.wave_id + " queued" : "Wave rejected: " + args.reason;
                waveFeedbackUntil = Date.now() + 5000;
                return {};
            });
            context.registerAction(COMMAND_ACTION, function (event) {
                const args = event.args;
                if (parkCatalog && parkCatalog.phase !== "ready")
                    return { error: 1, errorMessage: "Park is changing" };
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
                        return { error: 1, errorMessage: "Only the authorized commander may order this unit" };
                }
                if (!args || args.session !== controlSession || !Number.isSafeInteger(args.request)
                    || args.request < 1 || !Array.isArray(args.unit_ids)
                    || args.unit_ids.length > 32
                    || !(["move", "attack", "attack_move", "hold", "stop", "heal", "train"].includes(args.verb))
                    || (args.verb === "train" ? args.unit_ids.length !== 0 : args.unit_ids.length < 1))
                    return { error: 1, errorMessage: "Invalid unit command" };
                if (seenCommandRequests[args.session + ":" + event.player + ":" + args.request])
                    return { error: 1, errorMessage: "Duplicate command request" };
                if (args.verb === "train") {
                    const id = args.target_entity_id;
                    const building = BUILDING_TYPES[targetBuildingID(id, worldTargetIds[id])];
                    const requested = args.unit_type || "terran_marine";
                    if (typeof id !== "string" || !(/^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(id)
                        || /^scenario:[a-z0-9-]{1,64}$/.test(id))
                        || targetCatalogSession !== args.session || !worldTargetIds[id]
                        || !building || !building.production.includes(requested) || !UNIT_TYPES[requested]
                        || !buildingStates[id] || !buildingStates[id].command_authorized
                        || !buildingStates[id].commands.some(function (command) {
                            return command.action === "unit.train" && command.unit_type === requested
                                && command.ready;
                        })
                        || buildingStates[id].health < 1)
                        return { error: 1, errorMessage: "Production building is unavailable" };
                }
                const unique = {};
                if (!args.unit_ids.every(function (id) {
                    const unit = controlUnits[id];
                    if (!controllable(unit, terranOwner) || unique[id]
                        || !UNIT_TYPES[unit.kind].commands.includes(args.verb)) return false;
                    unique[id] = true;
                    return true;
                })) return { error: 1, errorMessage: "Unit is unavailable" };
                if ((args.verb === "move" || args.verb === "attack_move")
                    && (!Number.isInteger(args.x) || !Number.isInteger(args.y)
                    || args.x < 0 || args.y < 0 || args.x >= map.size.x * 32 || args.y >= map.size.y * 32))
                    return { error: 1, errorMessage: "Invalid destination" };
                if (args.verb === "attack") {
                    const target = controlUnits[args.target_id];
                    const structure = typeof args.target_entity_id === "string"
                        && (/^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(args.target_entity_id)
                            || /^scenario:[a-z0-9-]{1,64}$/.test(args.target_entity_id))
                        && targetCatalogSession === args.session && worldTargetIds[args.target_entity_id];
                    if ((!target || !UNIT_TYPES[target.kind] || target.owner === terranOwner || target.hp <= 0) && !structure)
                        return { error: 1, errorMessage: "Invalid attack target" };
                }
                if (args.verb === "heal") {
                    const target = controlUnits[args.target_id];
                    if (!target || !UNIT_TYPES[target.kind] || target.owner !== terranOwner
                        || target.hp <= 0 || target.hp >= target.max_hp)
                        return { error: 1, errorMessage: "Invalid heal target" };
                }
                if (network.mode === "server" && !(worldCommandSender))
                    return { error: 1, errorMessage: "Terran controller disconnected" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;
                seenCommandRequests[args.session + ":" + event.player + ":" + args.request] = true;

                    const commandId = args.session + ":" + (++commandSerial);
                    pendingCommands[commandId] = { player: event.player, request: args.request,
                        unit: args.verb === "train" ? args.target_entity_id : args.unit_ids[0] };
                    const payload = { command_id: commandId, player_id: event.player,
                        request_id: args.request, unit_ids: args.unit_ids.slice(), verb: "unit." + args.verb };
                    if (args.verb === "train") payload.unit_type = args.unit_type || "terran_marine";
                    if (args.verb === "move" || args.verb === "attack_move") {
                        payload.x = args.x; payload.y = args.y;
                    } else if (args.verb === "attack" || args.verb === "heal" || args.verb === "train")
                        payload.target_id = args.target_entity_id || args.target_id;
                    console.log("WORLD_COMMAND_ACTION id=" + commandId + " request=" + args.request
                        + " units=" + args.unit_ids.length + " verb=" + args.verb);
                    worldCommandSender(payload);
                    return {};
            });
            context.registerAction(SPAWN_ACTION, function (event) {
                const args = event.args || {};
                if (missionStatus && missionStatus.mode === "park_defense"
                    && missionStatus.defense_configurable)
                    return { error: 1, errorMessage: "Train Marines at a Barracks" };
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
                    && (/^openbw:[0-9]+$/.test(args.unit)
                        || /^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(args.unit)
                        || /^scenario:[a-z0-9-]{1,64}$/.test(args.unit))
                    && typeof args.accepted === "boolean"
                    && /^[a-z_]{2,64}$/.test(args.reason)
                    ? {} : { error: 1, errorMessage: "Invalid Marine command result" };
            }, function (event) {
                const args = event.args;
                if (args.player === network.currentPlayer.id) {
                    const pending = pendingTrainTypes[args.request];
                    if (pending) {
                        delete pendingTrainTypes[args.request];
                        productionFeedback[pending.target] = args.accepted ? pending.label + " training started"
                            : "Training rejected: " + args.reason;
                        console.log("WORLD_TRAIN_RESULT id=" + args.unit + " accepted="
                            + args.accepted + " reason=" + args.reason);
                        return {};
                    }
                    commandFeedback = args.accepted ? "Order " + args.request + " accepted"
                        : "Order " + args.request + " rejected: " + args.reason;
                    console.log("RTS Bridge Marine command request=" + args.request + " unit=" + args.unit
                        + " accepted=" + args.accepted + " reason=" + args.reason);
                }
                return {};
            });
            context.registerAction(BUILDING_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may publish native building state" };
                return args.session === controlSession
                    && (/^openrct2:[a-z_]+:[a-zA-Z0-9:_-]+#[0-9]+$/.test(args.id || "")
                        || /^scenario:[a-z0-9-]{1,64}$/.test(args.id || ""))
                    && /^openbw:[0-9]+$/.test(args.native_id || "")
                    && ["owner", "health", "queue", "remaining_frames", "minerals", "gas",
                        "supply_used", "supply_total"].every(function (field) {
                        return Number.isInteger(args[field]) && args[field] >= 0;
                    }) && args.health <= 1000000
                    && ["Terran", "Zerg", "Protoss"].includes(args.race)
                    && typeof args.completed === "boolean"
                    && (args.larva_count === undefined || (Number.isInteger(args.larva_count)
                        && args.larva_count >= 0 && args.larva_count <= 3))
                    && ["morph_count", "morph_remaining_frames", "supply_provided"].every(function (field) {
                        return args[field] === undefined || (Number.isInteger(args[field]) && args[field] >= 0);
                    })
                    && typeof args.command_authorized === "boolean"
                    && (args.max_health === undefined || (Number.isInteger(args.max_health)
                        && args.max_health >= args.health && args.max_health <= 1000000))
                    && args.queue <= 5
                    && args.availability && typeof args.availability === "object"
                    && Object.keys(args.availability).every(function (unitID) {
                        const status = args.availability[unitID];
                        return !!UNIT_TYPES[unitID] && status && typeof status.ready === "boolean"
                            && typeof status.reason === "string" && status.reason.length > 0
                            && status.reason.length <= 64 && typeof status.requirement === "string"
                            && status.requirement.length <= 64;
                    })
                    && Array.isArray(args.commands) && args.commands.length <= 9
                    && args.commands.every(function (command, slot) {
                        return command && command.slot === slot && command.action === "unit.train"
                            && !!UNIT_TYPES[command.unit_type]
                            && typeof command.label === "string" && command.label.length > 0
                            && command.label.length <= 64 && typeof command.ready === "boolean"
                            && typeof command.reason === "string" && command.reason.length > 0
                            && command.reason.length <= 64
                            && typeof command.requirement === "string"
                            && command.requirement.length <= 64
                            && args.availability[command.unit_type]
                            && args.availability[command.unit_type].ready === command.ready
                            && args.availability[command.unit_type].reason === command.reason;
                    })
                    ? {} : { error: 1, errorMessage: "Invalid native building state" };
            }, function (event) {
                if (!buildingStates[event.args.id]) console.log("WORLD_BUILDING_RECEIVED id="
                    + event.args.id + " session=" + event.args.session + " mode=" + network.mode);
                buildingStates[event.args.id] = event.args;
                refreshBuildingAnimations();
                return {};
            });
            context.registerAction(RESOURCE_ACTION, function (event) {
                const args = event.args || {};
                if (network.mode === "server" && event.player !== network.currentPlayer.id)
                    return { error: 1, errorMessage: "Only the server may publish native resources" };
                return /^[0-9a-f]{32}$/.test(args.session || "")
                    && (!controlSession || args.session === controlSession)
                    && ["owner", "minerals", "gas", "supply_used", "supply_total"].every(function (field) {
                        return Number.isInteger(args[field]) && args[field] >= 0;
                    }) ? {} : { error: 1, errorMessage: "Invalid native resources" };
            }, function (event) {
                playerResources[event.args.owner] = event.args;
                return {};
            });


        let animationTicks = 0;
        let cameraSession = "";
        context.subscribe("interval.tick", function () {
            if (++animationTicks % 4 === 0) rtsBridge.invalidateAnimation();
            if (network.mode === "server" && missionStatus) {
                const previousCommander = commanderPlayer;
                electCommander();
                if (previousCommander !== commanderPlayer)
                    context.executeAction(SCENARIO_STATUS_ACTION,
                        Object.assign({}, missionStatus, { commander_player: commanderPlayer }), function () {});
            }
            if (network.mode === "server" && pendingClientRefresh) {
                pendingClientRefresh = false;
                console.log("WORLD_CLIENT_REFRESH buildings=" + Object.keys(buildingStates).length
                    + " resources=" + Object.keys(playerResources).length
                    + " session=" + controlSession);
                if (pendingClientSnapshot && latestSnapshot) {
                    pendingClientSnapshot = false;
                    context.executeAction(ACTION, latestSnapshot, function (result) {
                        if (result.error) console.log("WORLD_CLIENT_SNAPSHOT_ERROR " + result.errorMessage);
                    });
                }
                if (publishingTargetSession) publishTargetCatalog(publishingTargetSession, publishedTargets);
                if (actorLifecycleSession) Object.keys(activeActorGenerations).forEach(function (id) {
                    publishActorLifecycle(actorLifecycleSession, id, activeActorGenerations[id], "active");
                });
                Object.keys(buildingStates).forEach(function (id) {
                    const state = buildingStates[id];
                    if (state.session === controlSession)
                        context.executeAction(BUILDING_ACTION, state, function (result) {
                            if (result.error) console.log("WORLD_CLIENT_BUILDING_ERROR " + result.errorMessage);
                        });
                });
                Object.keys(playerResources).forEach(function (owner) {
                    const state = playerResources[owner];
                    if (state.session === controlSession)
                        context.executeAction(RESOURCE_ACTION, state, function (result) {
                            if (result.error) console.log("WORLD_CLIENT_RESOURCE_ERROR " + result.errorMessage);
                        });
                });
                Object.keys(spawnStatuses).forEach(function (id) {
                    const status = spawnStatuses[id];
                    if (status.session === controlSession)
                        context.executeAction(SPAWN_STATUS_ACTION, status, function () {});
                });
                if (missionStatus && missionStatus.session === controlSession)
                    context.executeAction(SCENARIO_STATUS_ACTION, missionStatus, function () {});
                if (parkCatalog)
                    context.executeAction(PARK_CATALOG_ACTION, parkCatalog, function () {});
            }
            if (network.mode === "client"
                && (!controlSession || clientReadySession !== controlSession) && !clientReadyPending
                && animationTicks % 40 === 0) {
                clientReadyPending = true;
                const readySession = controlSession;
                context.executeAction(CLIENT_READY_ACTION, { session: readySession }, function (result) {
                    clientReadyPending = false;
                    if (!result.error && readySession) clientReadySession = readySession;
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
            // A remote plugin is restarted on reconnect while the server keeps
            // its command and spawn deduplication journals for this session.
            // Native OpenBW echoes command request IDs through a 32-bit integer.
            // Seed each plugin instance from the clock so reconnects do not
            // reuse IDs already recorded by the still-running server session.
            const requestEpoch = Date.now() % 2000000000;
            let nextRequest = requestEpoch;
            let selectingMultiple = false;
            let selectionSession = "";
            let dragStart = null;
            let dragEnd = null;
            let attackMove = false;
            let nextWaveRequest = requestEpoch;
            let constructionWindow = null;
            let buildingInfoWindow = null;
            let buildingInfoID = "";
            let barracksPreview = null;
            let barracksPreviewStatus = "Select Barracks to place";
            let barracksQuery = 0;
            let selectedBuildingID = "terran_barracks";
            function selectedBuilding() { return BUILDING_TYPES[selectedBuildingID]; }
            function selectedObject() { return buildingObjects[selectedBuildingID]; }
            function placementToolID() { return selectedBuildingID === "terran_barracks"
                ? "starcoaster.place-barracks" : "starcoaster.place-" + selectedBuildingID.replace(/_/g, "-"); }
            function usingBuildingTool() { return !!ui.tool && ui.tool.id.startsWith("starcoaster.place-"); }
            const controlGroups = {};
            function footprintAt(point) {
                if (!point) return null;
                const x = Math.floor(point.x / 32), y = Math.floor(point.y / 32);
                const building = selectedBuilding();
                if (x < 1 || y < 1 || x + building.width >= map.size.x
                    || y + building.height >= map.size.y) return null;
                return { x: x, y: y, tiles: Array.from({ length: building.width * building.height }, function (_, index) {
                    return { x: x + index % building.width, y: y + Math.floor(index / building.width) };
                }) };
            }
            function footprintReason(footprint) {
                if (!footprint) return "Outside the park";
                if (!controlSession) return "Waiting for native units";
                let height = null;
                for (const tile of footprint.tiles) {
                    const elements = map.getTile(tile.x, tile.y);
                    let surface = null;
                    for (let index = 0; index < elements.numElements; index++) {
                        const element = elements.getElement(index);
                        if (element.isGhost) continue;
                        if (element.type === "surface") surface = element;
                        else return "Ground is obstructed";
                    }
                    if (!surface || surface.waterHeight || surface.slope) return "Requires dry, flat ground";
                    const z = Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8;
                    if (height !== null && height !== z) return "Requires level ground";
                    height = z;
                }
                if (Object.keys(occupancyUnits).some(function (id) {
                    const unit = occupancyUnits[id];
                    const margin = 16;
                    return unit.hp > 0 && unit.x + margin > footprint.x * 32
                        && unit.y + margin > footprint.y * 32
                        && unit.x - margin < (footprint.x + selectedBuilding().width) * 32
                        && unit.y - margin < (footprint.y + selectedBuilding().height) * 32;
                })) return "A unit occupies this site";
                return "";
            }
            function barracksArgs(footprint) {
                const tile = map.getTile(footprint.x, footprint.y);
                let surface = null;
                for (let index = 0; index < tile.numElements; index++) {
                    if (tile.getElement(index).type === "surface") { surface = tile.getElement(index); break; }
                }
                return { x: footprint.x * 32, y: footprint.y * 32,
                    z: Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8,
                    direction: 0, object: selectedObject().index,
                    primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
            }
            function updateConstructionStatus() {
                if (!constructionWindow) return;
                const widget = constructionWindow.findWidget("barracks-status");
                if (widget) widget.text = barracksPreviewStatus;
            }
            function previewBarracks(event) {
                const footprint = footprintAt(pointFrom(event));
                barracksPreview = footprint;
                barracksPreviewStatus = footprintReason(footprint) || "Checking park clearance...";
                const query = ++barracksQuery;
                updateConstructionStatus();
                refreshSelection();
                if (!footprint || barracksPreviewStatus !== "Checking park clearance...") return;
                context.queryAction("largesceneryplace", barracksArgs(footprint), function (result) {
                    if (query !== barracksQuery || !barracksPreview) return;
                    barracksPreviewStatus = result.error ? result.errorMessage || "Blocked" : "Valid site - click to build";
                    updateConstructionStatus();
                });
            }
            function activateBarracksTool() {
                if (!selectedObject() || typeof context.queryAction !== "function") {
                    ui.showError(selectedBuilding().name, "Construction object is unavailable");
                    return;
                }
                ui.activateTool({ id: placementToolID(), cursor: "cross_hair",
                    filter: ["terrain", "footpath", "ride", "wall", "scenery", "large_scenery"],
                    onMove: previewBarracks,
                    onDown: function (event) {
                        const footprint = footprintAt(pointFrom(event));
                        const reason = footprintReason(footprint);
                        if (reason) { barracksPreviewStatus = reason; updateConstructionStatus(); return; }
                        const args = barracksArgs(footprint);
                        context.queryAction("largesceneryplace", args, function (query) {
                            if (query.error) {
                                barracksPreviewStatus = query.errorMessage || "Blocked";
                                updateConstructionStatus(); return;
                            }
                            if (footprintReason(footprint)) return;
                            context.executeAction("largesceneryplace", args, function (result) {
                                if (result.error) {
                                    barracksPreviewStatus = result.errorMessage || "Construction failed";
                                    updateConstructionStatus();
                                } else {
                                    barracksPreviewStatus = selectedBuilding().name + " constructed";
                                    updateConstructionStatus();
                                    if (usingBuildingTool()) ui.tool.cancel();
                                }
                            });
                        });
                    },
                    onFinish: function () {
                        barracksPreview = null;
                        barracksQuery++;
                        refreshSelection();
                    } });
            }
            function openConstructionWindow() {
                if (constructionWindow) { constructionWindow.bringToFront(); return; }
                const catalog = missionStatus && missionStatus.defense_configurable
                    ? Object.keys(BUILDING_TYPES).filter(function (id) { return id.startsWith("terran_"); })
                    : Object.keys(BUILDING_TYPES);
                const extraHeight = Math.max(0, catalog.length - 1) * 29;
                constructionWindow = ui.openWindow({ classification: "starcoaster-construction",
                    width: 238, height: 164 + extraHeight, title: "StarCraft Construction",
                    onClose: function () {
                        constructionWindow = null;
                        if (usingBuildingTool()) ui.tool.cancel();
                    }, widgets: [
                        { type: "label", x: 8, y: 19, width: 220, height: 14, text: "Terran" },
                    ].concat(catalog.map(function (id, index) {
                        const building = BUILDING_TYPES[id];
                        return { type: "button", x: 8, y: 35 + index * 29, width: 220, height: 26,
                            text: building.name.replace(/^(Terran|Zerg|Protoss) /, "") + "  |  "
                                + building.width + " x " + building.height + " tiles",
                            onClick: function () { selectedBuildingID = id; activateBarracksTool(); } };
                    }), [
                        { type: "label", name: "barracks-status", x: 8,
                            y: 93 + extraHeight, width: 220, height: 28,
                            text: barracksPreviewStatus },
                        { type: "button", name: "open-defense", x: 8, y: 121 + extraHeight,
                            width: 220, height: 26, text: "StarCraft Defense...",
                            onClick: openDefenseWindow }
                    ]) });
            }
            let defenseWindow = null;
            function defenseCommander() {
                return !missionStatus || missionStatus.commander_player === undefined
                    || missionStatus.commander_player === network.currentPlayer.id;
            }
            function configureDefense(settings) {
                if (!defenseCommander()) {
                    ui.showError("StarCraft Defense", "Only the Terran commander may change defense settings");
                    return;
                }
                if (!missionStatus || !missionStatus.defense_configurable) return;
                context.executeAction(DEFENSE_ACTION, Object.assign({ session: controlSession }, settings),
                    function (result) {
                        if (result.error) ui.showError("StarCraft Defense", result.errorMessage);
                    });
            }
            function selectDefenseSpawn() {
                if (!defenseCommander() || !missionStatus || missionStatus.defense_enabled) {
                    ui.showError("StarCraft Defense", "Disable waves before selecting a spawn point");
                    return;
                }
                if (ui.tool) ui.tool.cancel();
                ui.activateTool({ id: "starcoaster.defense-spawn", cursor: "cross_hair",
                    onDown: function (event) {
                        const point = event.mapCoords || rtsBridge.cursorWorld();
                        if (!point) return;
                        configureDefense({ anchor: [Math.floor(point.x / 32), Math.floor(point.y / 32)] });
                        if (ui.tool) ui.tool.cancel();
                    } });
            }
            function openDefenseWindow() {
                if (!missionStatus || !missionStatus.defense_configurable) {
                    ui.showError("StarCraft Defense", "Open an existing park in defense mode first");
                    return;
                }
                if (defenseWindow) { defenseWindow.bringToFront(); return; }
                defenseWindow = ui.openWindow({ classification: "starcoaster-defense",
                    width: 258, height: 256, title: "StarCraft Defense",
                    onClose: function () { defenseWindow = null; }, widgets: [
                        { type: "button", name: "defense-toggle", x: 8, y: 19, width: 118, height: 24,
                            text: "Enable Zerg Waves", onClick: function () {
                                if (missionStatus) configureDefense({ enabled: !missionStatus.defense_enabled });
                            } },
                        { type: "button", x: 132, y: 19, width: 118, height: 24,
                            text: "Select Spawn Point", onClick: selectDefenseSpawn },
                        { type: "label", name: "defense-spawn", x: 8, y: 50, width: 242, height: 14, text: "Spawn: none" },
                        { type: "button", name: "defense-interval", x: 8, y: 69, width: 242, height: 22,
                            text: "Wave interval: 120s", onClick: function () {
                                if (!missionStatus) return;
                                const options = [60, 90, 120, 180, 240, 300];
                                const current = options.indexOf(missionStatus.wave_interval_seconds);
                                configureDefense({ interval_seconds: options[(current + 1) % options.length] });
                            } },
                        { type: "button", name: "defense-difficulty", x: 8, y: 94, width: 242, height: 22,
                            text: "Wave difficulty: Standard", onClick: function () {
                                if (!missionStatus) return;
                                const options = ["easy", "standard", "hard"];
                                const current = options.indexOf(missionStatus.wave_difficulty || "standard");
                                configureDefense({ difficulty: options[(current + 1) % options.length] });
                            } },
                        { type: "label", name: "defense-next", x: 8, y: 122, width: 242, height: 14, text: "Next wave: disabled" },
                        { type: "label", name: "defense-current", x: 8, y: 141, width: 242, height: 14, text: "Current wave: 0" },
                        { type: "button", x: 8, y: 163, width: 118, height: 24,
                            text: "Spawn Wave Now", onClick: requestWave },
                        { type: "label", name: "defense-resources", x: 8, y: 199, width: 242, height: 14,
                            text: "Minerals: Unlimited | Gas: Unlimited" },
                        { type: "label", name: "defense-feedback", x: 8, y: 218, width: 242, height: 28,
                            text: "" }
                    ] });
            }
            clearUiForMap = function () {
                if (ui.tool) ui.tool.cancel();
                selected = [];
                Object.keys(controlGroups).forEach(function (number) { delete controlGroups[number]; });
                selectionSession = "";
                attackMove = false;
                dragStart = null;
                dragEnd = null;
                highlightedTiles = "";
                ui.tileSelection.tiles = [];
                ui.tileSelection.range = null;
                if (constructionWindow) constructionWindow.close();
                if (buildingInfoWindow) buildingInfoWindow.close();
                if (defenseWindow) defenseWindow.close();
            };
            if (typeof ui.registerMenuItem === "function") {
                ui.registerMenuItem("StarCraft Construction", openConstructionWindow);
                ui.registerMenuItem("StarCraft Defense", openDefenseWindow);
            }
            context.subscribe("interval.tick", function () {
                if (!defenseWindow) return;
                const status = missionStatus;
                if (!status) return;
                const setText = function (name, value) {
                    const widget = defenseWindow.findWidget(name);
                    if (widget) widget.text = value;
                };
                setText("defense-toggle", "Zerg Waves: " + (status.defense_enabled ? "On" : "Off"));
                setText("defense-spawn", "Spawn: " + (status.spawn_anchor
                    ? status.spawn_anchor.join(", ") : "select a park edge"));
                setText("defense-interval", "Wave interval: " + status.wave_interval_seconds + "s");
                setText("defense-difficulty", "Wave difficulty: " + (status.wave_difficulty || "standard"));
                setText("defense-next", status.defense_enabled
                    ? "Next wave: " + status.next_wave_seconds + "s" : "Next wave: disabled");
                setText("defense-current", "Current wave: " + status.wave_ordinal + " | "
                    + status.active_enemies + " enemies (" + status.wave_state + ")");
                setText("defense-resources", status.unlimited_resources
                    ? "Minerals: Unlimited | Gas: Unlimited" : "Resources: native balance");
                if (waveFeedback && Date.now() >= waveFeedbackUntil) waveFeedback = "";
                setText("defense-feedback", status.error ? "Wave placement: " + status.error
                    : waveFeedback || defenseFeedback);
            });
            function requestWave() {
                if (!controlSession || !missionStatus || missionStatus.mode !== "park_defense"
                    || !missionStatus.manual_eligible) {
                    ui.showError("Spawn Wave", "Manual waves are unavailable");
                    return;
                }
                const request = ++nextWaveRequest;
                const requestId = controlSession + ":wave:" + network.currentPlayer.id + ":" + request;
                waveFeedback = "Requesting an extra wave";
                waveFeedbackUntil = Date.now() + 5000;
                context.executeAction(WAVE_ACTION, { session: controlSession, request: request,
                    request_id: requestId }, function (result) {
                    if (result.error) {
                        waveFeedback = result.errorMessage;
                        waveFeedbackUntil = Date.now() + 5000;
                        ui.showError("Spawn Wave", result.errorMessage);
                    }
                });
            }
            function pointFrom(event) { return event.mapCoords || rtsBridge.cursorWorld(); }
            function refreshSelection() {
                if (selectionSession !== controlSession) {
                    selectionSession = controlSession; selected = [];
                    Object.keys(controlGroups).forEach(function (number) { delete controlGroups[number]; });
                    commandFeedback = "";
                    waveFeedback = "";
                    waveFeedbackUntil = 0;
                }
                selected = selected.filter(function (id) {
                    const unit = controlUnits[id];
                    return controllable(unit, terranOwner);
                });
                Object.keys(controlGroups).forEach(function (number) {
                    controlGroups[number] = controlGroups[number].filter(function (id) {
                        const unit = controlUnits[id];
                        return controllable(unit, terranOwner);
                    });
                });

                    const tiles = usingBuildingTool() && barracksPreview
                        ? barracksPreview.tiles.map(function (tile) { return { x: tile.x * 32, y: tile.y * 32 }; })
                        : selected.map(function (id) {
                        const unit = controlUnits[id];
                        return { x: Math.floor(unit.x / 32) * 32, y: Math.floor(unit.y / 32) * 32 };
                    });
                    const key = JSON.stringify(tiles);
                    if (ui.tool && !usingBuildingTool()) highlightedTiles = "";
                    else if (key !== highlightedTiles) {
                        ui.tileSelection.tiles = tiles;
                        highlightedTiles = key;
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
            context.subscribe("interval.tick", function () {
                refreshSelection();
                if (ui.tool && dragStart) clearDrag();
            });
            function unitAtScreen(point, ownedOnly) {
                if (!point) return null;
                let closest = null, best = Infinity;
                Object.keys(controlUnits).forEach(function (id) {
                    const unit = controlUnits[id];
                    if (unit.hp <= 0 || !UNIT_TYPES[unit.kind]
                        || (ownedOnly && !controllable(unit, terranOwner))) return;
                    const screen = rtsBridge.actorScreenPosition(id);
                    if (!screen) return;
                    const scale = screen.scale || 1;
                    // A compact footprint around the rendered body and feet, in screen pixels.
                    const halfWidth = Math.max(4, 12 * scale), height = Math.max(8, 28 * scale);
                    const dx = point.x - screen.x, dy = point.y - screen.y;
                    if (Math.abs(dx) > halfWidth || dy < -height || dy > Math.max(3, 4 * scale)) return;
                    const distance = dx * dx + (dy + height / 2) * (dy + height / 2);
                    if (distance <= best) { best = distance; closest = id; }
                });
                return closest;
            }
            function chooseAt(id, shift) {
                refreshSelection();
                if (shift || selectingMultiple) {
                    selected = selected.includes(id) ? selected.filter(function (entry) { return entry !== id; })
                        : selected.concat(id);
                } else selected = [id];
                console.log("RTS Bridge selected units=" + selected.join(","));
            }
            function chooseRectangle(start, end, shift) {
                refreshSelection();
                const left = Math.min(start.x, end.x), right = Math.max(start.x, end.x);
                const top = Math.min(start.y, end.y), bottom = Math.max(start.y, end.y);
                const inside = Object.keys(controlUnits).filter(function (id) {
                    const unit = controlUnits[id];
                    if (!controllable(unit, terranOwner))
                        return false;
                    const screen = rtsBridge.actorScreenPosition(id);
                    return screen && screen.x >= left && screen.x <= right
                        && screen.y >= top && screen.y <= bottom;
                });
                selected = shift ? selected.concat(inside.filter(function (id) { return !selected.includes(id); })) : inside;
                console.log("RTS Bridge selected units=" + selected.join(","));
            }
            function commandSquad(verb, extras, ids) {
                refreshSelection();
                const commanded = (ids || selected).filter(function (id) {
                    const unit = controlUnits[id];
                    return controllable(unit, terranOwner)
                        && UNIT_TYPES[unit.kind].commands.includes(verb);
                });
                for (let index = 0; index < commanded.length; index += 32) {
                    const args = Object.assign({ session: controlSession, request: ++nextRequest,
                        unit_ids: commanded.slice(index, index + 32), verb: verb }, extras);
                    context.executeAction(COMMAND_ACTION, args, function (result) {
                        if (result.error) ui.showError("Unit command", result.errorMessage);
                    });
                }
            }
            ui.registerShortcut({ id: "starcoaster.select-multiple", text: "Toggle squad selection",
                bindings: ["M"], callback: function () {
                    selectingMultiple = !selectingMultiple;
                    console.log("RTS Bridge multi-select=" + selectingMultiple);
                } });
            ui.registerShortcut({ id: "starcoaster.hold-position", text: "Hold selected positions",
                bindings: ["H"], callback: function () {
                    commandSquad("hold");
                } });
            ui.registerShortcut({ id: "starcoaster.stop", text: "Stop selected units", bindings: ["S"],
                callback: function () {
                    commandSquad("stop");
                } });
            ui.registerShortcut({ id: "starcoaster.attack-move", text: "Squad attack move", bindings: ["A"],
                callback: function () { attackMove = true; } });
            ui.registerShortcut({ id: "starcoaster.save-group-1", text: "Save squad group 1", bindings: ["CTRL+1"],
                callback: function () { refreshSelection(); controlGroups[1] = selected.slice(); } });
            ui.registerShortcut({ id: "starcoaster.recall-group-1", text: "Select squad group 1", bindings: ["1"],
                callback: function () { refreshSelection(); selected = (controlGroups[1] || []).filter(function (id) {
                    return controlUnits[id] && controlUnits[id].hp > 0;
                }); } });
            function orderAt(point, screen) {
                refreshSelection();
                if (!selected.length || !point) return false;
                const hit = screen ? unitAtScreen(screen, false) : rtsBridge.hitTest(point.x, point.y, 48);
                const target = hit && controlUnits[hit];
                const structure = Object.keys(worldTargetIds).filter(function (id) {
                    return worldTargetIds[id].geometry.rects.some(function (rect) {
                        return point.x >= rect.x && point.y >= rect.y
                            && point.x < rect.x + rect.width && point.y < rect.y + rect.height;
                    });
                })[0];
                const medics = selected.filter(function (id) {
                    return controlUnits[id] && controlUnits[id].kind === "terran_medic";
                });
                const others = selected.filter(function (id) { return !medics.includes(id); });
                if (target && target.owner === terranOwner && target.hp > 0
                    && target.hp < target.max_hp && medics.length) {
                    commandSquad("heal", { target_id: hit }, medics);
                    if (others.length) commandSquad("move", { x: point.x, y: point.y }, others);
                    attackMove = false;
                    return true;
                }
                let verb = target && UNIT_TYPES[target.kind] && target.owner !== terranOwner ? "attack" : "move";
                const extras = {};
                if (verb === "attack") extras.target_id = hit;
                else if (structure) { verb = "attack"; extras.target_entity_id = structure; }
                else {
                    if (attackMove) verb = "attack_move";
                    extras.x = point.x; extras.y = point.y;
                }
                attackMove = false;
                if (verb === "attack" && medics.length) {
                    commandSquad(verb, extras, others);
                    commandSquad("attack_move", { x: point.x, y: point.y }, medics);
                } else commandSquad(verb, extras);
                return true;
            }
            function clearDrag() {
                dragStart = null; dragEnd = null;
                ui.tileSelection.range = null;
            }
            function buildingAt(event) {
                if (!event || !event.mapCoords || event.alt) return null;
                const point = event.mapCoords;
                const x = Math.floor(point.x / 32), y = Math.floor(point.y / 32);
                if (x < 0 || y < 0 || x >= map.size.x || y >= map.size.y) return null;
                const tile = map.getTile(x, y);
                for (let index = 0; index < tile.numElements; index++) {
                    const element = tile.getElement(index);
                    if (element.type === "large_scenery" && !element.isGhost) {
                        const id = Object.keys(buildingObjects).filter(function (type) {
                            return buildingObjects[type] && buildingObjects[type].index === element.object;
                        })[0];
                        if (id) return { x: point.x, y: point.y,
                            z: element.baseZ === undefined ? element.baseHeight * 8 : element.baseZ,
                            buildingID: id };
                    }
                }
                return null;
            }
            function buildingTargetAt(point) {
                return Object.keys(worldTargetIds).filter(function (id) {
                    return !!targetBuildingID(id, worldTargetIds[id])
                        && worldTargetIds[id].geometry.rects.some(function (rect) {
                        return point.x >= rect.x && point.x < rect.x + rect.width
                            && point.y >= rect.y && point.y < rect.y + rect.height;
                    });
                })[0] || "";
            }
            function openBuildingInspector(point) {
                buildingInfoID = buildingTargetAt(point);
                const initial = worldTargetIds[buildingInfoID];
                const buildingID = targetBuildingID(buildingInfoID, initial) || point.buildingID;
                const building = BUILDING_TYPES[buildingID];
                if (!building) return;
                const rects = initial && initial.geometry ? initial.geometry.rects : [];
                const bounds = rects.length ? {
                    left: Math.min.apply(null, rects.map(function (rect) { return rect.x; })),
                    top: Math.min.apply(null, rects.map(function (rect) { return rect.y; })),
                    right: Math.max.apply(null, rects.map(function (rect) { return rect.x + rect.width; })),
                    bottom: Math.max.apply(null, rects.map(function (rect) { return rect.y + rect.height; }))
                } : { left: Math.floor(point.x / 32) * 32, top: Math.floor(point.y / 32) * 32,
                    right: Math.floor(point.x / 32) * 32 + building.width * 32,
                    bottom: Math.floor(point.y / 32) * 32 + building.height * 32 };
                const centre = { x: Math.floor((bounds.left + bounds.right) / 2),
                    y: Math.floor((bounds.top + bounds.bottom) / 2),
                    z: (point.z || 0) + Math.floor(Math.max(bounds.right - bounds.left,
                        bounds.bottom - bounds.top) / 3) };
                const reasonLabels = { building_unavailable: "Building unavailable",
                    insufficient_minerals: "Insufficient minerals", insufficient_gas: "Insufficient gas",
                    supply_limit: "Supply limit", queue_full: "Queue full",
                    native_unavailable: "Unavailable" };
                function commandText(command) {
                    if (!command) return "";
                    return command.label.replace(/^(Terran|Zerg|Protoss)[ _]/, "");
                }
                function nativeReason(command) {
                    if (!command) return "";
                    if (command.reason === "requires_building")
                        return "Requires " + command.requirement.replace(/_/g, " ");
                    return reasonLabels[command.reason] || command.reason.replace(/_/g, " ");
                }
                if (buildingInfoWindow) buildingInfoWindow.close();
                const card = Array.from({ length: 9 }, function (_, slot) {
                    return { type: "button", name: "building-command-" + slot,
                        x: 289 + (slot % 3) * 49, y: 35 + Math.floor(slot / 3) * 48,
                        width: 46, height: 34, image: COMMAND_ICON_IMAGES.empty, border: true,
                        text: "", isDisabled: true,
                        onClick: function () {
                            const native = buildingStates[buildingInfoID];
                            const command = native && native.commands ? native.commands[slot] : null;
                            if (!command || !command.ready || !mayCommandBuilding(native)
                                || command.action !== "unit.train") return;
                            const request = ++nextRequest;
                            const targetID = buildingInfoID;
                            pendingTrainTypes[request] = { label: commandText(command),
                                target: targetID };
                            productionFeedback[targetID] = "Requesting " + commandText(command) + "...";
                            context.executeAction(COMMAND_ACTION, { session: controlSession,
                                request: request, unit_ids: [], verb: "train",
                                unit_type: command.unit_type, target_entity_id: targetID },
                            function (result) {
                                if (result.error) {
                                    delete pendingTrainTypes[request];
                                    productionFeedback[targetID] = result.errorMessage;
                                }
                            });
                        } };
                });
                const cardLabels = Array.from({ length: 9 }, function (_, slot) {
                    return { type: "label", name: "building-label-" + slot,
                        x: 289 + (slot % 3) * 49, y: 69 + Math.floor(slot / 3) * 48,
                        width: 46, height: 11, text: "" };
                });
                buildingInfoWindow = ui.openWindow({ classification: "starcoaster-building-info",
                    width: 445, height: 300, title: building.name,
                    onClose: function () { buildingInfoWindow = null; buildingInfoID = ""; },
                    onUpdate: function () {
                        if (!buildingInfoWindow) return;
                        if (!buildingInfoID) buildingInfoID = buildingTargetAt(point);
                        const target = worldTargetIds[buildingInfoID];
                        if (!target && initial) { buildingInfoWindow.close(); return; }
                        const native = buildingStates[buildingInfoID];
                        const resources = native ? (playerResources[native.owner] || native) : null;
                        const camera = buildingInfoWindow.findWidget("building-camera");
                        if (camera && camera.viewport) {
                            const viewport = camera.viewport;
                            if (ui.mainViewport && viewport.rotation !== ui.mainViewport.rotation)
                                viewport.rotation = ui.mainViewport.rotation;
                            if (viewport.zoom !== 0) viewport.zoom = 0;
                            viewport.moveTo(centre);
                        }
                        const fields = {
                            "building-owner": native ? "Owner: " + native.race + " (player " + native.owner + ")"
                                : "Owner: awaiting native state",
                            "building-health": native ? "HP: " + native.health + "/" + native.max_health
                                : "HP: awaiting native state",
                            "building-status": native ? (native.completed ? "Complete" : "Constructing")
                                + "  Queue: " + native.queue
                                + (native.remaining_frames ? "  Remaining: " + native.remaining_frames + " frames" : "")
                                + (Number.isInteger(native.larva_count) ? "  Larvae: " + native.larva_count : "")
                                + (native.morph_count ? "  Eggs: " + native.morph_count
                                    + " (" + native.morph_remaining_frames + " frames)" : "")
                                + (native.supply_provided ? "  Provides: " + (native.supply_provided / 2) + " supply" : "")
                                : "Native status: synchronizing",
                            "building-resources": resources ? "Minerals: " + resources.minerals + "  Gas: " + resources.gas
                                + "  Supply: " + (resources.supply_used / 2) + "/" + (resources.supply_total / 2) : "",
                            "building-feedback": productionFeedback[buildingInfoID] || ""
                        };
                        Object.keys(fields).forEach(function (name) {
                            const widget = buildingInfoWindow.findWidget(name);
                            if (widget) widget.text = fields[name];
                        });
                        for (let slot = 0; slot < 9; slot++) {
                            const widget = buildingInfoWindow.findWidget("building-command-" + slot);
                            const command = native && native.commands ? native.commands[slot] : null;
                            if (!widget) continue;
                            const image = command && COMMAND_ICON_IMAGES[command.unit_type];
                            widget.image = image || COMMAND_ICON_IMAGES.empty;
                            const label = buildingInfoWindow.findWidget("building-label-" + slot);
                            if (label) label.text = commandText(command);
                            widget.isDisabled = !target || !native || native.health < 1
                                || !mayCommandBuilding(native) || !command || !command.ready;
                            widget.tooltip = command ? (!mayCommandBuilding(native) ? "Read-only building"
                                : command.ready ? "Train " + command.label
                                : nativeReason(command)) : "";
                        }
                    }, widgets: [
                        { type: "viewport", name: "building-camera", x: 8, y: 20,
                            width: 268, height: 194 },
                        { type: "groupbox", name: "building-card-frame", x: 281, y: 20,
                            width: 155, height: 164, text: "Commands" },
                        { type: "label", name: "building-owner", x: 8, y: 222, width: 430,
                            height: 14, text: "Owner: awaiting native state" },
                        { type: "label", name: "building-health", x: 8, y: 239, width: 430,
                            height: 14, text: "HP: awaiting native state" },
                        { type: "label", name: "building-status", x: 8, y: 256, width: 430,
                            height: 14, text: "Native status: synchronizing" },
                        { type: "label", name: "building-resources", x: 8, y: 273, width: 430,
                            height: 14, text: "" },
                        { type: "label", name: "building-feedback", x: 283, y: 190, width: 155,
                            height: 27, text: "" }
                    ].concat(card, cardLabels) });
            }
            if (typeof ui.registerViewportInteraction !== "function")
                throw new Error("RTS Bridge needs the native shared viewport input build");
            const marineSelection = { id: "starcoaster.select-marine",
                filter: ["terrain", "water", "footpath", "ride", "wall", "scenery", "large_scenery"],
                onHover: function (event) {
                    return !event.alt && (!!unitAtScreen(event.screenCoords, true) || !!buildingAt(event));
                },
                onDown: function (event) {
                    clearDrag();
                    if (event.alt) return;
                    dragStart = { world: pointFrom(event), screen: event.screenCoords };
                    dragEnd = dragStart;
                },
                onMove: function (event) {
                    if (dragStart) {
                        dragEnd = { world: pointFrom(event), screen: event.screenCoords };
                        if (dragStart.world && dragEnd.world) ui.tileSelection.range = {
                            leftTop: { x: Math.min(dragStart.world.x, dragEnd.world.x), y: Math.min(dragStart.world.y, dragEnd.world.y) },
                            rightBottom: { x: Math.max(dragStart.world.x, dragEnd.world.x), y: Math.max(dragStart.world.y, dragEnd.world.y) }
                        };
                    }
                },
                onUp: function (event) {
                    const start = dragStart;
                    clearDrag();
                    if (!start || !start.screen || !event.screenCoords || event.alt) return false;
                    const end = event.screenCoords;
                    if (Math.abs(end.x - start.screen.x) >= 4 || Math.abs(end.y - start.screen.y) >= 4) {
                        chooseRectangle(start.screen, end, event.shift);
                        return true;
                    }
                    const id = unitAtScreen(end, true);
                    if (!id) {
                        const building = buildingAt(event);
                        if (!building) return false;
                        openBuildingInspector(building);
                        return true;
                    }
                    chooseAt(id, event.shift);
                    return true;
                },
                onFinish: clearDrag,
                onRightClick: function (event) {
                    return !event.alt && orderAt(pointFrom(event), event.screenCoords);
                } };
            ui.registerViewportInteraction(marineSelection);
            ui.registerShortcut({ id: "starcoaster.select-mode", text: "Return to unit selection",
                bindings: ["CTRL+SHIFT+U"], callback: function () {
                    if (ui.tool) ui.tool.cancel();
                    clearDrag();
                } });
        }

        if (network.mode !== "server") return;

            context.subscribe("network.join", function () {
                const previousCommander = commanderPlayer;
                electCommander();
                if (missionStatus && previousCommander !== commanderPlayer)
                    context.executeAction(SCENARIO_STATUS_ACTION,
                        Object.assign({}, missionStatus, { commander_player: commanderPlayer }), function () {});
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
            }, function (sender) { worldWaveSender = sender; }, function (status) {
                context.executeAction(WAVE_STATUS_ACTION, status, function (result) {
                    if (result.error) console.log("WORLD_WAVE_STATUS_ERROR " + result.errorMessage);
                });
            }, function (sender) { worldDefenseSender = sender; }, function (status) {
                context.executeAction(DEFENSE_RESULT_ACTION, status, function (result) {
                    if (result.error) console.log("WORLD_DEFENSE_STATUS_ERROR " + result.errorMessage);
                });
            }, function (sender) { worldParkSender = sender; }, function (catalog) {
                context.executeAction(PARK_CATALOG_ACTION, catalog, function (result) {
                    if (result.error) console.log("WORLD_PARK_CATALOG_ERROR " + result.errorMessage);
                });
            }, function (status) {
                context.executeAction(PARK_LOAD_STATUS_ACTION, status, function (result) {
                    if (result.error) console.log("WORLD_PARK_LOAD_STATUS_ERROR " + result.errorMessage);
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
