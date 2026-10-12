/* Read-only multiplayer fixture for the 100-unit world snapshot. */
registerPlugin({ name: "World Bridge Unit Count Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, previous = -1;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session || snapshot.units.length === previous) return;
            previous = snapshot.units.length;
            console.log("WORLD_UNIT_COUNT " + previous);
        });
    }
});
