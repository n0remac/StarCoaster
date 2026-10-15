// Test-only native traversal and real construction actions in the layered park.
registerPlugin({ name: "Layered Navigation Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, tick = 0, ordered = false, trackBuilt = false, pathBuilt = false, completed = false;
        let trackAttempted = false, pathAttempted = false, waitingTicks = 0;
        let marineStart = null, zergStart = null;
        function actor(units, id) { return units.find(function (unit) { return unit.id === id; }); }
        function ride() { return map.rides.find(function (item) { return item.name === "Layered Test Coaster"; }); }
        function placeTrack() {
            const item = ride();
            if (!item) { console.log("LAYERED_LIVE_ERROR coaster_missing"); return; }
            context.executeAction("trackplace", { x: 20 * 32, y: 31 * 32, z: 192,
                direction: 0, ride: item.id, trackType: 0, rideType: item.type,
                brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                isFromTrackDesign: false }, function (result) {
                trackBuilt = !result.error;
                console.log("LAYERED_LIVE_TRACK accepted=" + trackBuilt + " ride=" + item.id
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function placePath() {
            context.executeAction("footpathplace", { x: 48 * 32, y: 57 * 32, z: 160,
                object: 4, railingsObject: 0, direction: 0,
                slopeType: 0, slopeDirection: 0, constructFlags: 0 }, function (result) {
                pathBuilt = !result.error;
                console.log("LAYERED_LIVE_PATH accepted=" + pathBuilt
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        context.subscribe("interval.tick", function () {
            if (completed) return;
            const state = rtsBridge.getActors();
            if (!state || !/^[0-9a-f]{32}$/.test(state.session)) {
                if (++waitingTicks % 100 === 0) console.log("LAYERED_LIVE_WAIT session="
                    + (state && state.session) + " units=" + (state && state.units && state.units.length));
                return;
            }
            const marine = actor(state.units, "openbw:1003"), zerg = actor(state.units, "openbw:2000");
            if (!marine || !zerg) {
                if (++waitingTicks % 100 === 0) console.log("LAYERED_LIVE_WAIT actors="
                    + state.units.map(function (unit) { return unit.id; }).join(","));
                return;
            }
            if (!started) {
                started = Date.now(); marineStart = { x: marine.x, y: marine.y };
                zergStart = { x: zerg.x, y: zerg.y };
                console.log("LAYERED_LIVE_START marine=" + marine.x + "," + marine.y
                    + " zerg=" + zerg.x + "," + zerg.y);
            }
            const elapsed = Date.now() - started;
            if (++tick % 8 === 0) console.log("LAYERED_LIVE_POSITION elapsed=" + elapsed
                + " marine=" + marine.x + "," + marine.y + " zerg=" + zerg.x + "," + zerg.y);
            if (!ordered && elapsed > 2000) {
                ordered = true;
                const args = { session: state.session, request: 1,
                    unit_ids: ["openbw:1003"], verb: "move", x: 768, y: 1008 };
                context.queryAction("rtsbridge.marineCommand", args, function (query) {
                    console.log("LAYERED_LIVE_ORDER_QUERY accepted=" + !query.error
                        + " reason=" + (query.errorMessage || "ok"));
                    if (query.error) return;
                    context.executeAction("rtsbridge.marineCommand", args, function (result) {
                        console.log("LAYERED_LIVE_ORDER accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            }
            if (ordered && !trackAttempted && elapsed > 5000) { trackAttempted = true; placeTrack(); }
            if (trackBuilt && !pathAttempted && elapsed > 9000) { pathAttempted = true; placePath(); }
            if (elapsed > 30000) {
                completed = true;
                console.log("LAYERED_LIVE_COMPLETE marine=" + marine.x + "," + marine.y
                    + " zerg=" + zerg.x + "," + zerg.y + " marine_start="
                    + marineStart.x + "," + marineStart.y + " zerg_start="
                    + zergStart.x + "," + zergStart.y + " track=" + trackBuilt + " path=" + pathBuilt);
            }
        });
    }
});
