/* Passthrough RTS Bridge. Distributed by the OpenRCT2 multiplayer server. */
(function () {
    "use strict";

    const ACTION = "rtsbridge.applySnapshot";
    const PORT = 39999;
    const MAP_ID = "demo-flat";
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
        context.subscribe("network.join", function (event) {
            console.log("RTS Bridge player joined: " + event.player + "; active=" + network.numPlayers);
        });
        context.subscribe("network.leave", function (event) {
            console.log("RTS Bridge player left: " + event.player + "; active=" + network.numPlayers);
        });
        let session = "";
        let lastSeq = 0;
        const retiredSessions = {};
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
            if (!validWire(snapshot)) {
                console.log("RTS Bridge dropped invalid snapshot");
                return;
            }
            if (snapshot.session !== session) {
                if (retiredSessions[snapshot.session]) return;
                if (session) retiredSessions[session] = true;
                session = snapshot.session;
                lastSeq = 0;
                console.log("RTS Bridge session " + session);
            }
            if (snapshot.seq <= lastSeq) return;
            lastSeq = snapshot.seq;

            const units = snapshot.units.map(function (unit) {
                return {
                    id: unit.id,
                    x: Math.round(ORIGIN_X + unit.x * SCALE_X),
                    y: Math.round(ORIGIN_Y + unit.y * SCALE_Y),
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
