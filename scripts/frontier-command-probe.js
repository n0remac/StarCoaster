/* Live client action probe used by capture-live-demo.py. */
registerPlugin({
    name: "Frontier Marine Command Probe",
    version: "1.0.0",
    authors: ["StarCoaster"],
    type: "local",
    licence: "MIT",
    targetApiVersion: 124,
    minApiVersion: 124,
    main: function () {
        var marine = null;
        var start = null;
        var moved = false;
        var ticks = 0;
        var lastRequestTick = -100;
        var requests = 0;
        var attackSent = false;
        context.subscribe("interval.tick", function () {
            if (typeof rtsBridge !== "object" || typeof rtsBridge.getActors !== "function") return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            ++ticks;
            if (!marine || !snapshot.units.some(function (unit) { return unit.id === marine.id; })) {
                var candidates = snapshot.units.filter(function (unit) {
                    return unit.kind === "terran_marine" && unit.hp > 0;
                });
                marine = candidates[1] || candidates[0];
                if (!marine) return;
                start = { x: marine.x, y: marine.y };
            }
            if (!moved) {
                var current = snapshot.units.filter(function (unit) { return unit.id === marine.id; })[0];
                if (current && Math.abs(current.x - start.x) + Math.abs(current.y - start.y) >= 12) {
                    moved = true;
                    console.log("FRONTIER_COMMAND_MOVED id=" + marine.id + " from=" + start.x + "," + start.y
                        + " to=" + current.x + "," + current.y);
                }
            }
            if (!moved && ticks >= 12 && ticks - lastRequestTick >= 15) {
                lastRequestTick = ticks;
                ++requests;
                console.log("FRONTIER_COMMAND_REQUEST id=" + marine.id + " x=790 y=440 attempt=" + requests);
                context.executeAction("rtsbridge.marineCommand", {
                    session: snapshot.session, request: 776 + requests, unit_ids: [marine.id],
                    verb: "move", x: 790, y: 440
                }, function (result) {
                    console.log("FRONTIER_COMMAND_QUERY accepted=" + !result.error
                        + " error=" + (result.errorMessage || "none"));
                });
            }
            if (moved && !attackSent) {
                var enemies = snapshot.units.filter(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                });
                if (enemies.length) {
                    var target = enemies[enemies.length - 1];
                    attackSent = true;
                    console.log("FRONTIER_ATTACK_REQUEST marine=" + marine.id + " target=" + target.id);
                    context.executeAction("rtsbridge.marineCommand", {
                        session: snapshot.session, request: 888, unit_ids: [marine.id],
                        verb: "attack", target_id: target.id
                    }, function (result) {
                        console.log("FRONTIER_ATTACK_QUERY accepted=" + !result.error
                            + " error=" + (result.errorMessage || "none"));
                    });
                }
            }
        });
    }
});
