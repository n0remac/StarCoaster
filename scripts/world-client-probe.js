/* Read-only multiplayer observation for world.v1 integration tests. */
registerPlugin({ name: "StarCoaster World Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var previous = null, ticks = 0;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0) return;
            var ids = map.rides.map(function (ride) { return ride.id; }).sort(function (a, b) { return a - b; });
            var value = JSON.stringify(ids);
            if (value !== previous) {
                console.log("WORLD_CLIENT_RIDES " + value);
                previous = value;
            }
        });
    }
});
