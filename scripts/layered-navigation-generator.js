/* Test-only layered park. Built from a copied Frontier save under run-data. */
registerPlugin({ name: "Layered Navigation Generator", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "server") return;
        let started = false, saving = false, fixturePending = false, rideId = -1;
        const source = [];
        function fail(message) { console.log("LAYERED_NAV_FAILED " + message); started = true; saving = false; }
        function action(kind, args, next) {
            console.log("LAYERED_NAV_ACTION " + kind + " " + JSON.stringify(args));
            context.executeAction(kind, args, function (result) {
                if (result.error) { fail(kind + " " + JSON.stringify(result)); return; }
                source.push({ action: kind, args: args }); next(result);
            });
        }
        function track(x, y, z, type, next) {
            action("trackplace", { x: x * 32, y: y * 32, z: z, direction: 0,
                ride: rideId, trackType: type, rideType: coaster.rideType[0],
                brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                isFromTrackDesign: false }, next);
        }
        let coaster;
        function build() {
            try {
                coaster = objectManager.getAllObjects("ride").find(function (entry) {
                    return entry.identifier === "rct2.ride.arrt1";
                });
                if (!coaster) {
                    objectManager.load("rct2.ride.arrt1");
                    coaster = objectManager.getAllObjects("ride").find(function (entry) {
                        return entry.identifier === "rct2.ride.arrt1";
                    });
                }
                if (!coaster) throw new Error("corkscrew coaster object unavailable");
                action("ridecreate", { rideType: coaster.rideType[0], rideObject: coaster.index,
                    entranceObject: 0, colour1: 0, colour2: 0, inspectionInterval: 0 }, function (created) {
                    if (!Number.isInteger(created.ride)) { fail("ridecreate did not return an ID"); return; }
                    rideId = created.ride;
                    action("ridesetname", { ride: rideId, name: "Layered Test Coaster" }, function () {
                        track(16, 31, 192, 0, function () { // High straight above Marine start.
                            track(27, 30, 112, 0, function () { // Low rail.
                                track(29, 30, 112, 1, function () { // Ground station.
                                    track(35, 30, 120, 40, function () { // Half-height loop origin.
                                        paths();
                                    });
                                });
                            });
                        });
                    });
                });
            } catch (error) { fail(String(error)); }
        }
        function path(z, next) {
            action("footpathplace", { x: 47 * 32, y: 57 * 32, z: z,
                object: 4, railingsObject: 0, direction: 0,
                slopeType: 0, slopeDirection: 0, constructFlags: 0 }, next);
        }
        function paths() {
            path(112, function () { path(160, function () {
                fixturePending = true;
            }); });
        }
        function addFixture() {
            try {
                // This deliberately low slab is a fixture for clearance testing.
                // Ordinary OpenRCT2 construction may reject overlapping clearance.
                const tile = map.getTile(46, 57);
                tile.insertElement(tile.numElements);
                const element = tile.getElement(tile.numElements - 1);
                element.type = "footpath"; element.baseHeight = 17; element.clearanceHeight = 21;
                element.object = 4; element.slopeDirection = null;
                source.push({ fixture: "low_overhead_path", x: 46, y: 57, base_z: 136 });
                const diagnostics = [];
                [[16,31],[27,30],[29,30],[35,30],[46,57],[47,57]].forEach(function (point) {
                    const item = map.getTile(point[0], point[1]);
                    for (let n = 0; n < item.numElements; n++) {
                        const e = item.getElement(n);
                        diagnostics.push({ x: point[0], y: point[1], type: e.type,
                            base_z: e.baseZ, clearance_z: e.clearanceZ,
                            occupied_quadrants: e.occupiedQuadrants,
                            ghost: e.isGhost, track_type: e.type === "track" ? e.trackType : null,
                            sequence: e.type === "track" ? e.sequence : null,
                            slope: e.type === "surface" ? e.slope : null,
                            slope_direction: e.type === "footpath" ? e.slopeDirection : null });
                    }
                });
                park.name = "Layered Navigation Test";
                console.log("LAYERED_NAV_SOURCE " + JSON.stringify({ ride_id: rideId,
                    actions: source, elements: diagnostics }));
                saving = true;
            } catch (error) { fail(String(error)); }
        }
        context.subscribe("interval.tick", function () {
            if (!started) { started = true; build(); }
            else if (fixturePending) { fixturePending = false; addFixture(); }
            else if (saving) { saving = false; context.saveGame({ filename: "layered-navigation" }); }
        });
    }
});
