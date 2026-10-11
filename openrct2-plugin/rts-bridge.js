/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const COMMAND_ACTION = "rtsbridge.marineCommand";
    const RESULT_ACTION = "rtsbridge.commandResult";
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

    function validUnits(args, combat) {
        if (!args || typeof args.session !== "string" || !/^[0-9a-f]{32}$/.test(args.session)
            || !Number.isSafeInteger(args.seq) || args.seq < 1 || !Array.isArray(args.units) || args.units.length > MAX_UNITS) {
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
        let commandSocket = null;
        let commandConnected = false;
        let commandSerial = 0;
        const pendingCommands = {};
        context.registerAction(ACTION, function (event) {
            if (network.mode === "server" && event.player !== network.currentPlayer.id) {
                return { error: 1, errorMessage: "Only the RTS bridge server may publish snapshots" };
            }
            return validAction(event.args) ? {} : { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
        }, function (event) {
            if (!validAction(event.args)) return { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
            rtsBridge.applySnapshot(event.args);
            controlSession = event.args.session;
            controlUnits = {};
            event.args.units.forEach(function (unit) { controlUnits[unit.id] = unit; });
            const marine = event.args.units.filter(function (unit) { return unit.kind === "terran_marine"; })[0];
            if (marine) terranOwner = marine.owner;
            return {};
        });

        if (FRONTIER_ENABLED) {
            context.registerAction(COMMAND_ACTION, function (event) {
                const args = event.args;
                if (network.mode === "server" && (!Array.isArray(network.players)
                    || !network.players.some(function (player) { return player.id === event.player; })))
                    return { error: 1, errorMessage: "Player is not connected" };
                if (!args || args.session !== controlSession || !Number.isSafeInteger(args.request)
                    || args.request < 1 || !Array.isArray(args.unit_ids) || args.unit_ids.length < 1
                    || args.unit_ids.length > 4 || !["move", "attack", "hold"].includes(args.verb))
                    return { error: 1, errorMessage: "Invalid Marine command" };
                const unique = {};
                if (!args.unit_ids.every(function (id) {
                    const unit = controlUnits[id];
                    if (!unit || unique[id] || unit.kind !== "terran_marine"
                        || unit.owner !== terranOwner || unit.hp <= 0) return false;
                    unique[id] = true;
                    return true;
                })) return { error: 1, errorMessage: "Marine is unavailable" };
                if (args.verb === "move" && (!Number.isInteger(args.x) || !Number.isInteger(args.y)
                    || args.x < 0 || args.y < 0 || args.x >= 4096 || args.y >= 4096))
                    return { error: 1, errorMessage: "Invalid destination" };
                if (args.verb === "attack") {
                    const target = controlUnits[args.target_id];
                    if (!target || target.kind !== "zerg_zergling" || target.hp <= 0)
                        return { error: 1, errorMessage: "Invalid Zergling target" };
                }
                if (network.mode === "server" && !commandConnected)
                    return { error: 1, errorMessage: "Terran controller disconnected" };
                return {};
            }, function (event) {
                if (network.mode !== "server") return {};
                const args = event.args;
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
                    && /^(ok|invalid_marine|invalid_target|bwapi_rejected)$/.test(args.reason)
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
        context.subscribe("interval.tick", function () {
            if (++animationTicks % 4 === 0) rtsBridge.invalidateAnimation();
        });

        if (FRONTIER_ENABLED && typeof ui !== "undefined") {
            let selected = [];
            let nextRequest = 0;
            let selectingMultiple = false;
            function chooseAt(point, shift) {
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
            function orderAt(point) {
                if (!selected.length || !point) return;
                const hit = rtsBridge.hitTest(point.x, point.y, 22);
                const target = hit && controlUnits[hit];
                const args = { session: controlSession, request: ++nextRequest,
                    unit_ids: selected, verb: target && target.kind === "zerg_zergling" ? "attack" : "move" };
                if (args.verb === "attack") args.target_id = hit;
                else { args.x = point.x + 128; args.y = point.y + 96; }
                context.executeAction(COMMAND_ACTION, args, function (result) {
                    if (result.error) ui.showError("Marine command", result.errorMessage);
                });
            }
            ui.activateTool({ id: "starcoaster.select-marine", cursor: "cross_hair", filter: ["terrain", "footpath"],
                onDown: function (event) { chooseAt(event.mapCoords, event.shift); },
                onRightClick: function (event) { orderAt(event.mapCoords); } });
        }

        if (network.mode !== "server") return;
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
