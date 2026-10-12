/* Local client probe for the generic world.v1 Marine command path. */
registerPlugin({ name: "World Bridge Command Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, request = 0, marineId = "", start = null, moved = false, attacked = false;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge || typeof rtsBridge.getActors !== "function") return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marine = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            })[0];
            if (!marine) return;
            if (!marineId) {
                marineId = marine.id; start = { x: marine.x, y: marine.y };
                console.log("WORLD_COMMAND_MARINE " + JSON.stringify(marine));
            }
            if (marine.id !== marineId) return;
            if (!moved && Math.abs(marine.x - start.x) + Math.abs(marine.y - start.y) >= 24) {
                moved = true;
                console.log("WORLD_COMMAND_MOVED id=" + marine.id + " x=" + marine.x + " y=" + marine.y);
            }
            if (!moved && ticks % 60 === 0) {
                var x = Math.max(0, marine.x - 256), y = Math.max(0, marine.y - 256);
                console.log("WORLD_COMMAND_MOVE_REQUEST id=" + marine.id + " x=" + x + " y=" + y);
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: [marine.id], verb: "move", x: x, y: y },
                    function (result) { console.log("WORLD_COMMAND_MOVE_QUERY accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok")); });
            }
            if (moved && !attacked) {
                var enemy = snapshot.units.filter(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                })[0];
                if (!enemy) return;
                attacked = true;
                console.log("WORLD_COMMAND_ATTACK_REQUEST marine=" + marine.id + " target=" + enemy.id);
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: [marine.id], verb: "attack", target_id: enemy.id },
                    function (result) { console.log("WORLD_COMMAND_ATTACK_QUERY accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok")); });
            }
        });
    }
});
