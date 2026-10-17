/* Test-only: ordinary park actions and four edge attacks in a native session. */
registerPlugin({ name: "Mt. Zergling Gameplay Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let opened = false, built = false, waveCount = 0, nextWaveAt = 0;
        const confirmedWaves = {};
        const first = {}, moved = {};
        context.subscribe("action.execute", function (event) {
            if (event.action !== "rtsbridge.waveStatus" || !event.args
                || !event.result || event.result.error) return;
            const status = event.args;
            if (status.accepted && status.wave_id) confirmedWaves[status.wave_id] = true;
            console.log("MT_GAMEPLAY_WAVE_STATUS request=" + status.request_id
                + " accepted=" + status.accepted + " wave=" + status.wave_id
                + " reason=" + status.reason);
        });
        function buildRide() {
            const entry = objectManager.getAllObjects("ride").find(function (item) {
                return item.identifier === "rct2.ride.burgb";
            });
            if (!entry) { console.log("MT_GAMEPLAY_RIDE_ERROR object_missing"); return; }
            const rideType = entry.rideType[0];
            context.executeAction("ridecreate", { rideType: rideType, rideObject: entry.index,
                entranceObject: 0, colour1: 0, colour2: 0, inspectionInterval: 0 }, function (created) {
                console.log("MT_GAMEPLAY_RIDECREATE accepted=" + !created.error
                    + " reason=" + (created.errorMessage || "ok"));
                if (created.error) return;
                const tile = map.getTile(105, 104);
                let surface;
                for (let i = 0; i < tile.numElements; i++) {
                    if (tile.getElement(i).type === "surface") surface = tile.getElement(i);
                }
                const args = { x: 105 * 32, y: 104 * 32, z: surface.baseZ,
                    direction: 0, ride: created.ride, trackType: 262, rideType: rideType,
                    brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                    isFromTrackDesign: false };
                context.executeAction("trackplace", args, function (placed) {
                    console.log("MT_GAMEPLAY_TRACKPLACE accepted=" + !placed.error
                        + " reason=" + (placed.errorMessage || "ok"));
                });
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge && rtsBridge.getActors();
            if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
            if (!opened) {
                opened = true;
                context.executeAction("parksetparameter", { parameter: 1, value: 0 }, function (result) {
                    console.log("MT_GAMEPLAY_PARK_OPEN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!built) { built = true; buildRide(); }
            const now = Date.now();
            if (Object.keys(confirmedWaves).length < 6 && waveCount < 24 && now >= nextWaveAt) {
                waveCount++;
                nextWaveAt = now + 6000;
                const request = waveCount;
                context.executeAction("rtsbridge.requestWave", { session: snapshot.session,
                    request: request, request_id: snapshot.session + ":wave:"
                        + network.currentPlayer.id + ":" + request }, function (result) {
                    console.log("MT_GAMEPLAY_WAVE_REQUEST number=" + request
                        + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                });
            }
            snapshot.units.filter(function (unit) { return unit.kind === "zerg_zergling"; })
                .forEach(function (unit) {
                    if (!first[unit.id]) {
                        first[unit.id] = { x: unit.x, y: unit.y };
                        console.log("MT_GAMEPLAY_ZERG_START id=" + unit.id + " x=" + unit.x + " y=" + unit.y);
                    } else if (!moved[unit.id] && Math.abs(unit.x - first[unit.id].x)
                        + Math.abs(unit.y - first[unit.id].y) >= 96) {
                        moved[unit.id] = true;
                        console.log("MT_GAMEPLAY_ZERG_MOVED id=" + unit.id + " x=" + unit.x + " y=" + unit.y);
                    }
                });
        });
    }
});
