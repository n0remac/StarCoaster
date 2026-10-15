// Test-only ordinary demolition of a scenario objective.
registerPlugin({ name: "Live Objective Removal Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, removed = false, completed = false;
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            const elapsed = Date.now() - started;
            if (!removed && elapsed > 3000) {
                removed = true;
                context.executeAction("ridedemolish", { ride: 0, modifyType: 0 }, function (result) {
                    console.log("LIVE_OBJECTIVE_MANUAL_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            } else if (removed && !completed && elapsed > 18000) {
                completed = true;
                console.log("LIVE_OBJECTIVE_COMPLETE ride_present=" + !!map.getRide(0)
                    + " actors=" + snapshot.units.map(function (unit) { return unit.id; }).sort().join(","));
            }
        });
    }
});
