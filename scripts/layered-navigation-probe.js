// Test-only native traversal and real construction actions in the layered park.
registerPlugin({ name: "Layered Navigation Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, tick = 0, ordered = false, lastOrderAttempt = 0;
        let trackBuilt = false, pathBuilt = false, ghostBuilt = false, completed = false;
        let trackAttempted = false, pathAttempted = false, ghostAttempted = false, heightAttempted = false;
        let heightChanged = false, waitingTicks = 0;
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
        function previewWall() {
            context.executeAction("wallplace", { x: 50 * 32, y: 55 * 32, z: 112,
                object: 9, edge: 1, primaryColour: 0, secondaryColour: 0,
                tertiaryColour: 0, flags: 1 << 6 }, function (result) {
                const tile = map.getTile(50, 55);
                let foundGhost = false;
                for (let i = 0; i < tile.numElements; i++) {
                    const element = tile.getElement(i);
                    if (element.type === "wall" && element.isGhost) foundGhost = true;
                }
                ghostBuilt = !result.error && foundGhost;
                console.log("LAYERED_LIVE_GHOST accepted=" + !result.error
                    + " ghost=" + foundGhost + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function elevateLowTrack() {
            const item = ride();
            if (!item) { console.log("LAYERED_LIVE_ERROR coaster_missing_for_height_change"); return; }
            context.executeAction("trackremove", { x: 27 * 32, y: 30 * 32, z: 112,
                direction: 0, trackType: 0, sequence: 0 }, function (removed) {
                console.log("LAYERED_LIVE_LOW_TRACK_REMOVE accepted=" + !removed.error
                    + " reason=" + (removed.errorMessage || "ok"));
                if (removed.error) return;
                context.executeAction("trackplace", { x: 27 * 32, y: 30 * 32, z: 192,
                    direction: 0, ride: item.id, trackType: 0, rideType: item.type,
                    brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                    isFromTrackDesign: false }, function (placed) {
                    heightChanged = !placed.error;
                    console.log("LAYERED_LIVE_TRACK_HEIGHT accepted=" + heightChanged
                        + " ride=" + item.id + " reason=" + (placed.errorMessage || "ok"));
                });
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
            if (!ordered && elapsed > 2000 && Date.now() - lastOrderAttempt > 3000) {
                lastOrderAttempt = Date.now();
                const args = { session: state.session, request: 1,
                    unit_ids: ["openbw:1003"], verb: "move", x: 768, y: 1008 };
                context.queryAction("rtsbridge.marineCommand", args, function (query) {
                    console.log("LAYERED_LIVE_ORDER_QUERY accepted=" + !query.error
                        + " reason=" + (query.errorMessage || "ok"));
                    if (query.error) return;
                    context.executeAction("rtsbridge.marineCommand", args, function (result) {
                        if (!result.error) ordered = true;
                        console.log("LAYERED_LIVE_ORDER accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            }
            if (ordered && !trackAttempted && elapsed > 5000) { trackAttempted = true; placeTrack(); }
            if (trackBuilt && !ghostAttempted && elapsed > 7000) {
                ghostAttempted = true; previewWall();
            }
            if (trackBuilt && !pathAttempted && elapsed > 9000) { pathAttempted = true; placePath(); }
            if (pathBuilt && !heightAttempted && elapsed > 16000) {
                heightAttempted = true; elevateLowTrack();
            }
            if (elapsed > 30000) {
                completed = true;
                console.log("LAYERED_LIVE_COMPLETE marine=" + marine.x + "," + marine.y
                    + " zerg=" + zerg.x + "," + zerg.y + " marine_start="
                    + marineStart.x + "," + marineStart.y + " zerg_start="
                    + zergStart.x + "," + zergStart.y + " track=" + trackBuilt + " path=" + pathBuilt
                    + " height=" + heightChanged + " ghost=" + ghostBuilt);
            }
        });
    }
});
