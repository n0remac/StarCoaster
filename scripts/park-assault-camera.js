/* Read-only client camera and independent native ride/track observations. */
registerPlugin({
    name: "Frontier Outpost Camera", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        var closeup = false; // The capture launcher selects the client B view.
        var targets = [
            { id: "carousel-1", name: "Frontier Carousel", x: 640, y: 640, expected: 9 },
            { id: "shop-1", name: "Frontier Burger Bar", x: 1200, y: 640, expected: 1 },
            { id: "ride-2", name: "Frontier Ferris Wheel", x: 1360, y: 1280, expected: 4 }
        ];
        var seenBefore = {}, seenAfter = {}, ticks = 0, focus = -1;
        function tracks(rideId) {
            var count = 0;
            for (var x = 8; x <= 55; x++) for (var y = 8; y <= 55; y++) {
                var tile = map.getTile(x, y);
                for (var i = 0; i < tile.numElements; i++) {
                    var e = tile.getElement(i);
                    if (e.type === "track" && e.ride === rideId) count++;
                }
            }
            return count;
        }
        function scenerySignature() {
            var total = 0, hash = 2166136261;
            for (var x = 8; x <= 55; x++) for (var y = 8; y <= 55; y++) {
                var tile = map.getTile(x, y);
                for (var i = 0; i < tile.numElements; i++) {
                    var e = tile.getElement(i);
                    if (["footpath", "small_scenery", "wall"].indexOf(e.type) === -1) continue;
                    total++;
                    var value = x * 4099 + y * 131 + e.baseHeight * 17
                        + (e.object || 0) * 7 + e.type.length;
                    hash = Math.imul(hash ^ value, 16777619) >>> 0;
                }
            }
            return total + ":" + hash;
        }
        context.subscribe("interval.tick", function () {
            if (network.mode !== "client" || !ui.mainViewport) return;
            ticks++;
            if (ticks === 20) {
                ui.mainViewport.zoom = closeup ? -1 : 2;
                ui.mainViewport.rotation = 0;
                ui.mainViewport.moveTo(closeup ? { x: 640, y: 640 } : { x: 1040, y: 1040 });
                focus = closeup ? 0 : -1;
                console.log("PARK_ASSAULT_CAMERA role=" + (closeup ? "closeup" : "overview"));
            }
            if (ticks % 8 !== 0) return;
            targets.forEach(function (target, index) {
                var rides = map.rides.filter(function (ride) { return ride.name === target.name; });
                if (!seenBefore[target.id] && rides.length === 1) {
                    var ride = rides[0], count = tracks(ride.id);
                    if (count === target.expected) {
                        seenBefore[target.id] = ride.id;
                        console.log("PARK_ASSAULT_CLIENT_BEFORE " + JSON.stringify({ id: target.id,
                            ride_id: ride.id, tracks: count, scenery: scenerySignature(), rides: map.rides.length }));
                    }
                }
                if (seenBefore[target.id] && !seenAfter[target.id]
                    && !map.getRide(seenBefore[target.id]) && tracks(seenBefore[target.id]) === 0) {
                    seenAfter[target.id] = true;
                    console.log("PARK_ASSAULT_CLIENT_AFTER " + JSON.stringify({ id: target.id,
                        ride_id: seenBefore[target.id], tracks: 0,
                        scenery: scenerySignature(), rides: map.rides.length }));
                    if (closeup && focus === index && index + 1 < targets.length) {
                        var next = targets[index + 1];
                        ui.mainViewport.moveTo({ x: next.x, y: next.y });
                        focus = index + 1;
                        console.log("PARK_ASSAULT_CAMERA focus=" + next.id);
                    }
                }
            });
        });
    }
});
