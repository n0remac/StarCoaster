/* Test-only Marine orders and reinforcement for native multi-wave verification. */
registerPlugin({ name: "Scenario Defense Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client" || !SCENARIO_PROBE_COMMANDER) return;
        var ticks = 0, spawned = false, forwardSpawned = false, reserveSpawned = false, gateSpawned = false;
        var ordered = false, runtimeOrdered = false, held = false;
        var request = 10000;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
            var marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            var zerglings = snapshot.units.filter(function (unit) {
                return unit.kind === "zerg_zergling" && unit.hp > 0;
            });
            if (!spawned && marines.length === 6) {
                spawned = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":scenario:reinforcement", count: 5,
                    x: 720, y: 1040 }, function (result) {
                    console.log("SCENARIO_MANUAL_SPAWN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (spawned && !forwardSpawned && marines.length >= 11) {
                forwardSpawned = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":scenario:forward", count: 5,
                    x: 1056, y: 1536 }, function (result) {
                    console.log("SCENARIO_FORWARD_SPAWN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (forwardSpawned && !reserveSpawned && marines.length >= 15) {
                reserveSpawned = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":scenario:reserve", count: 5,
                    x: 1088, y: 1344 }, function (result) {
                    console.log("SCENARIO_RESERVE_SPAWN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (reserveSpawned && !gateSpawned && marines.length >= 19) {
                gateSpawned = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":scenario:gate", count: 5,
                    x: 1024, y: 1200 }, function (result) {
                    console.log("SCENARIO_GATE_SPAWN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!ordered && marines.length >= 6) {
                ordered = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: marines.map(function (unit) { return unit.id; }),
                    verb: "move", x: 640, y: 560 }, function (result) {
                    console.log("SCENARIO_DEFEND_ORDER accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (marines.length > 6 && !runtimeOrdered) {
                var runtime = marines.filter(function (unit) { return /^openbw:30[0-9][0-9]$/.test(unit.id); });
                if (runtime.length >= 5) {
                    runtimeOrdered = true;
                    context.executeAction("rtsbridge.marineCommand", {
                    session: snapshot.session, request: ++request,
                    unit_ids: runtime.map(function (unit) { return unit.id; }),
                    verb: "move", x: 800, y: 1100 }, function (result) {
                    console.log("SCENARIO_REINFORCEMENT_ORDER accepted=" + !result.error);
                });
                }
            }
            if (!held && marines.length >= 11 && marines.filter(function (unit) {
                return unit.x > 730 && unit.x < 880 && unit.y > 980 && unit.y < 1180;
            }).length >= 5) {
                held = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: marines.filter(function (unit) {
                        return !/^openbw:100[0-5]$/.test(unit.id);
                    }).map(function (unit) { return unit.id; }),
                    verb: "hold" }, function (result) {
                    console.log("SCENARIO_HOLD_ORDER accepted=" + !result.error);
                });
            }
            if (ticks % 200 === 0) console.log("SCENARIO_ROSTER marines=" + marines.length
                + " zerglings=" + zerglings.length);
        });
    }
});
