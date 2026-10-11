/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const PORT = 39999;
    const SIEGE_ENABLED = false;
    const MAP_ID = SIEGE_ENABLED ? "ride-siege" : "demo-flat";
    const MAX_LINE = 16384;
    const MAX_UNITS = 32;
    const ORIGIN_X = 0;
    const ORIGIN_Y = 0;
    const SCALE_X = 1;
    const SCALE_Y = 1;

    function validAction(args) {
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
                && (unit.motion === "idle" || unit.motion === "walk");
        });
    }

    function validWire(snapshot) {
        if (!snapshot || snapshot.v !== 1 || snapshot.kind !== "units.snapshot"
            || snapshot.map_id !== MAP_ID || !validAction(snapshot)
            || !Number.isSafeInteger(snapshot.bw_tick) || snapshot.bw_tick < 0) {
            return false;
        }
        return snapshot.units.every(function (unit) {
            return unit.kind === "alien_scout" && unit.alive === true;
        });
    }

    function validSiegeWire(snapshot) {
        if (!snapshot || snapshot.v !== 2 || snapshot.kind !== "scenario.snapshot"
            || snapshot.map_id !== "ride-siege" || !validAction(snapshot)
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
        if (typeof rtsBridge !== "object" || rtsBridge.version !== 1 || rtsBridge.assetVersion !== 1
            || typeof rtsBridge.applySnapshot !== "function"
            || typeof rtsBridge.invalidateAnimation !== "function") {
            throw new Error("RTS Bridge needs the matching native OpenRCT2 build and asset pack");
        }

        context.registerAction(ACTION, function (event) {
            if (network.mode === "server" && event.player !== network.currentPlayer.id) {
                return { error: 1, errorMessage: "Only the RTS bridge server may publish snapshots" };
            }
            return validAction(event.args) ? {} : { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
        }, function (event) {
            if (!validAction(event.args)) return { error: 1, errorMessage: "Invalid RTS bridge snapshot" };
            rtsBridge.applySnapshot(event.args);
            return {};
        });

        let animationTicks = 0;
        context.subscribe("interval.tick", function () {
            if (++animationTicks % 4 === 0) rtsBridge.invalidateAnimation();
        });

        if (network.mode !== "server") return;
        const siegeRide = SIEGE_ENABLED ? registeredCarousel() : null;
        if (SIEGE_ENABLED && !siegeRide) {
            console.log("RIDE_SIEGE_ERROR expected closed empty Frontier Carousel fixture is missing or changed");
            return;
        }
        if (SIEGE_ENABLED) console.log("RIDE_SIEGE_READY ride=" + siegeRide.id + " tracks=9 target=carousel-1");
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
        const siege = { rideId: siegeRide ? siegeRide.id : -1, proxyId: "", hp: 200,
            state: "intact", demolitionAttempted: false };
        let socket = null;
        let reconnectTicks = 0;

        function onLine(line) {
            let snapshot;
            try {
                snapshot = JSON.parse(line);
            } catch (error) {
                console.log("RTS Bridge dropped malformed JSON: " + error);
                return;
            }
            if (!(SIEGE_ENABLED ? validSiegeWire(snapshot) : validWire(snapshot))) {
                console.log("RTS Bridge dropped invalid snapshot");
                return;
            }
            if (snapshot.session !== session) {
                if (retiredSessions[snapshot.session]) return;
                if (SIEGE_ENABLED && (siege.demolitionAttempted || siege.state === "destroyed")) {
                    console.log("RIDE_SIEGE_ERROR new session requires a fresh, intact park");
                    return;
                }
                if (session) retiredSessions[session] = true;
                session = snapshot.session;
                lastSeq = 0;
                lastBwTick = -1;
                if (SIEGE_ENABLED) {
                    siege.hp = 200;
                    siege.proxyId = "";
                    siege.state = "intact";
                }
                console.log("RTS Bridge session " + session);
            }
            if (snapshot.seq <= lastSeq || snapshot.bw_tick < lastBwTick) return;
            if (SIEGE_ENABLED) {
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
                    x: Math.round((SIEGE_ENABLED ? -128 : ORIGIN_X) + unit.x * SCALE_X),
                    y: Math.round((SIEGE_ENABLED ? -96 : ORIGIN_Y) + unit.y * SCALE_Y),
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
            });
        }

        connect();
        context.subscribe("interval.tick", function () {
            if (socket === null && ++reconnectTicks >= 40) {
                reconnectTicks = 0;
                connect();
            }
        });
    }

    registerPlugin({
        name: "Passthrough RTS Bridge",
        version: "0.2.0",
        authors: ["Passthrough RTS project"],
        type: "remote",
        licence: "MIT",
        targetApiVersion: 124,
        minApiVersion: 124,
        main: main
    });
}());
