/* One-time, local park generator loaded by scripts/create-render-test-park.py. */
registerPlugin({
    name: "RTS Bridge Render Test Park Generator",
    version: "1.0.0",
    authors: ["StarCoaster"],
    type: "local",
    licence: "MIT",
    targetApiVersion: 124,
    minApiVersion: 124,
    main: function () {
        // The Python generator substitutes this literal in its separate
        // ride-siege process; the original render fixture stays unchanged.
        var fixtureMode = "render";
        var done = false;
        var readyToSave = false;
        context.subscribe("interval.tick", function () {
            if (readyToSave && network.mode === "server") {
                readyToSave = false;
                context.saveGame({ filename: "bridge-ride-siege" });
                return;
            }
            if (done || network.mode !== "server") return;
            done = true;
            function trackTiles(rideId) {
                var cells = [];
                for (var x = 14; x <= 24; x++) for (var y = 11; y <= 22; y++) {
                    var tile = map.getTile(x, y);
                    for (var index = 0; index < tile.numElements; index++) {
                        var element = tile.getElement(index);
                        if (element.type === "track" && element.ride === rideId) {
                            cells.push({ x: x, y: y, z: element.baseHeight * 8,
                                         trackType: element.trackType, sequence: element.sequence });
                        }
                    }
                }
                return cells;
            }
            function intendedRide() {
                return map.rides.filter(function (ride) { return ride.name === "Frontier Carousel"; });
            }
            function add(x, y, type, base, clearance, object) {
                var tile = map.getTile(x, y);
                tile.insertElement(tile.numElements);
                var element = tile.getElement(tile.numElements - 1);
                element.type = type;
                element.baseHeight = base;
                element.clearanceHeight = clearance;
                element.object = object;
                return element;
            }
            if (fixtureMode === "ride-siege-probe") {
                var candidates = intendedRide();
                if (candidates.length !== 1 || candidates[0].object.identifier !== "rct2.ride.mgr1") {
                    console.log("RIDE_SIEGE_PROBE_FAILED identity count=" + candidates.length);
                    return;
                }
                var before = trackTiles(candidates[0].id);
                if (before.length !== 9 || candidates[0].status !== "closed") {
                    console.log("RIDE_SIEGE_PROBE_FAILED footprint=" + before.length + " status=" + candidates[0].status);
                    return;
                }
                context.executeAction("ridedemolish", { ride: candidates[0].id, modifyType: 0 }, function (result) {
                    var after = trackTiles(candidates[0].id);
                    var gone = !map.getRide(candidates[0].id) && after.length === 0;
                    console.log("RIDE_SIEGE_PROBE " + JSON.stringify({ ride: candidates[0].id,
                        error: result.error || 0, errorMessage: result.errorMessage || "",
                        tracks_before: before.length, tracks_after: after.length, removed: gone }));
                });
                return;
            }
            if (fixtureMode === "ride-siege") {
                var matches = objectManager.getAllObjects("ride").filter(function (object) {
                    return object.identifier === "rct2.ride.mgr1";
                });
                if (matches.length !== 1 || !matches[0].rideType.length) {
                    console.log("RIDE_SIEGE_FAILED merry-go-round object unavailable; matches=" + matches.length);
                    return;
                }
                var rideObject = matches[0];
                var rideType = rideObject.rideType[0];
                console.log("RIDE_SIEGE_OBJECT " + JSON.stringify({ identifier: rideObject.identifier,
                    index: rideObject.index, rideTypes: rideObject.rideType, rideType: rideType }));
                // Keep the footprint clear and the approach visible. These
                // decorations are away from the carousel's 3x3 track tiles.
                for (var pathX = 10; pathX <= 16; pathX++) {
                    var path = add(pathX, 17, "footpath", 14, 16, 4);
                    path.surfaceObject = 4;
                    path.railingsObject = 0;
                    path.edges = 5;
                }
                var approachTree = add(15, 12, "small_scenery", 14, 26, 31);
                approachTree.quadrant = 0;
                context.executeAction("ridecreate", { rideType: rideType, rideObject: rideObject.index,
                    entranceObject: 0, colour1: 0, colour2: 0, inspectionInterval: 0 }, function (created) {
                    if (created.error || !Number.isInteger(created.ride)) {
                        console.log("RIDE_SIEGE_FAILED ridecreate " + JSON.stringify(created));
                        return;
                    }
                    var rideId = created.ride;
                    context.executeAction("trackplace", { x: 19 * 32, y: 15 * 32, z: 112,
                        direction: 0, ride: rideId, trackType: 266, rideType: rideType,
                        brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                        isFromTrackDesign: false }, function (placed) {
                        if (placed.error) {
                            console.log("RIDE_SIEGE_FAILED trackplace " + JSON.stringify(placed));
                            return;
                        }
                        context.executeAction("ridesetname", { ride: rideId, name: "Frontier Carousel" }, function (named) {
                            if (named.error) {
                                console.log("RIDE_SIEGE_FAILED ridesetname " + JSON.stringify(named));
                                return;
                            }
                            var ride = map.getRide(rideId);
                            var tracks = trackTiles(rideId);
                            var metadata = { ride: rideId, rideType: ride.type,
                                object: ride.object.identifier, name: ride.name, status: ride.status,
                                tracks: tracks };
                            console.log("RIDE_SIEGE_METADATA " + JSON.stringify(metadata));
                            if (ride.status !== "closed" || tracks.length !== 9) {
                                console.log("RIDE_SIEGE_FAILED unexpected ride state or footprint");
                                return;
                            }
                            // Action callbacks cannot mutate game state; save
                            // on the next normal server tick instead.
                            readyToSave = true;
                        });
                    });
                });
                return;
            }
            // The OpenBW actor traverses y=480, x=320..640 (tiles 10..20,15).
            // Add a visible path, trees on both sides, a fence in front, and
            // a raised section along the last part of the route.
            for (var x = 18; x <= 21; x++) {
                for (var y = 14; y <= 16; y++) {
                    var surface = map.getTile(x, y).getElement(0);
                    surface.baseHeight = 16;
                    surface.clearanceHeight = 16;
                }
            }
            for (var px = 10; px <= 20; px++) {
                var height = px >= 18 ? 16 : 14;
                var path = add(px, 15, "footpath", height, height + 2, 4);
                path.surfaceObject = 4;
                path.railingsObject = 0;
                path.edges = 5;
            }
            var treeNorth = add(13, 14, "small_scenery", 14, 26, 31);
            treeNorth.quadrant = 0;
            var treeSouth = add(14, 16, "small_scenery", 14, 26, 31);
            treeSouth.quadrant = 0;
            var treeEnd = add(19, 16, "small_scenery", 16, 28, 98);
            treeEnd.quadrant = 0;
            for (var wx = 16; wx <= 17; wx++) {
                var wall = add(wx, 16, "wall", 14, 18, 9);
                wall.direction = 0;
            }
            context.saveGame({ filename: "bridge-render-test" });
            console.log("RTS render test park saved");
        });
    }
});
