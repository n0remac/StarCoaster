/* Local-only camera helper for visual captures. No game state is changed. */
registerPlugin({
    name: "RTS Bridge Demo Camera",
    version: "1.0.0",
    authors: ["Passthrough RTS project"],
    type: "local",
    licence: "MIT",
    targetApiVersion: 124,
    minApiVersion: 124,
    main: function () {
        var demoRotation = 0;
        var cycleRotations = false;
        var siegeCamera = false;
        var ticks = 0;
        var siegeBefore = false;
        var siegeAfter = false;
        function siegeTracks() {
            var count = 0;
            for (var x = 18; x <= 20; ++x) {
                for (var y = 14; y <= 16; ++y) {
                    var tile = map.getTile(x, y);
                    for (var i = 0; i < tile.numElements; ++i) {
                        var element = tile.getElement(i);
                        if (element.type === "track" && element.ride === 100) ++count;
                    }
                }
            }
            return count;
        }
        function treePresent() {
            var tile = map.getTile(15, 12);
            for (var i = 0; i < tile.numElements; ++i) {
                if (tile.getElement(i).type === "small_scenery") return true;
            }
            return false;
        }
        function otherRideIds() {
            return map.rides.filter(function (ride) { return ride.id !== 100; })
                .map(function (ride) { return ride.id; }).sort(function (a, b) { return a - b; });
        }
        function unrelatedScenery() {
            var items = [];
            for (var x = 10; x <= 22; ++x) {
                for (var y = 10; y <= 20; ++y) {
                    if (x >= 18 && x <= 20 && y >= 14 && y <= 16) continue;
                    var tile = map.getTile(x, y);
                    for (var i = 0; i < tile.numElements; ++i) {
                        var element = tile.getElement(i);
                        if (element.type === "small_scenery" || element.type === "wall" || element.type === "footpath")
                            items.push(x + "," + y + ":" + element.type + ":" + element.baseHeight);
                    }
                }
            }
            return items.sort();
        }
        context.subscribe("interval.tick", function () {
            if (network.mode !== "client" || !ui.mainViewport) return;
            ++ticks;
            if (siegeCamera) {
                var ride = map.getRide(100);
                var tracks = siegeTracks();
                if (!siegeBefore && ride && tracks === 9) {
                    siegeBefore = true;
                    console.log("RIDE_SIEGE_CLIENT_BEFORE " + JSON.stringify({ rides: map.rides.length,
                        tracks: tracks, tree: treePresent(), ride: ride.id,
                        otherRideIds: otherRideIds(), scenery: unrelatedScenery() }));
                }
                if (siegeBefore && !siegeAfter && !ride && tracks === 0) {
                    siegeAfter = true;
                    console.log("RIDE_SIEGE_CLIENT_AFTER " + JSON.stringify({ rides: map.rides.length,
                        tracks: tracks, tree: treePresent(), ride: null,
                        otherRideIds: otherRideIds(), scenery: unrelatedScenery() }));
                }
            }
            if (ticks === 40) {
                ui.mainViewport.zoom = -1;
                ui.mainViewport.rotation = demoRotation;
                ui.mainViewport.moveTo(siegeCamera ? { x: 544, y: 488 } : { x: 480, y: 480 });
                console.log("RTS Bridge demo camera centred at world (480,480), rotation=" + demoRotation);
            } else if (cycleRotations && ticks > 40 && (ticks - 40) % 120 === 0) {
                demoRotation = (demoRotation + 1) % 4;
                ui.mainViewport.rotation = demoRotation;
                ui.mainViewport.moveTo({ x: 480, y: 480 });
                console.log("RTS Bridge demo camera rotation=" + demoRotation);
            }
        });
    }
});
