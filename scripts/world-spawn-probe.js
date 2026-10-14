/* Test-only synchronized action probe. Never bundled with player plugins. */
registerPlugin({ name: "StarCoaster Spawn Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, requested = false, moved = false, attacked = false, lastRoster = "";
        var initialSquadSeen = false, replacementRequested = false, replacementReady = false;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            }).map(function (unit) { return unit.id; }).sort();
            var roster = marines.join(",");
            if (roster !== lastRoster) {
                console.log("WORLD_SPAWN_ROSTER count=" + marines.length + " ids=" + roster);
                lastRoster = roster;
            }
            if (!requested && marines.length === 6) {
                requested = true;
                console.log("WORLD_SPAWN_SUBMIT session=" + snapshot.session);
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":live:marines", count: 5,
                    x: typeof STARCOASTER_TEST_SPAWN_X === "number" ? STARCOASTER_TEST_SPAWN_X : 720,
                    y: typeof STARCOASTER_TEST_SPAWN_Y === "number" ? STARCOASTER_TEST_SPAWN_Y : 1040 },
                    function (result) {
                        console.log("WORLD_SPAWN_REQUEST accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            }
            var runtime = marines.filter(function (id) { return /^openbw:30[0-9][0-9]$/.test(id); });
            if (runtime.length === 5 && runtime.indexOf("openbw:3001") !== -1) initialSquadSeen = true;
            if (typeof STARCOASTER_TEST_RECOVERY !== "undefined" && STARCOASTER_TEST_RECOVERY
                && initialSquadSeen && !replacementRequested && marines.indexOf("openbw:3001") === -1) {
                replacementRequested = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":live:replacement", count: 1, x: 784, y: 1040 },
                    function (result) {
                        console.log("WORLD_SPAWN_REPLACEMENT_REQUEST accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            }
            if (replacementRequested && !replacementReady && runtime.indexOf("openbw:3006") !== -1) {
                replacementReady = true;
                console.log("WORLD_SPAWN_REPLACEMENT ids=" + runtime.join(","));
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 9103, unit_ids: ["openbw:3006"], verb: "move", x: 704, y: 1056 },
                    function (result) {
                        console.log("WORLD_SPAWN_REPLACEMENT_MOVE accepted=" + !result.error);
                    });
            }
            if (runtime.length !== 5) return;
            if (!moved) {
                moved = true;
                console.log("WORLD_SPAWN_SQUAD ids=" + runtime.join(","));
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 9101, unit_ids: runtime, verb: "move", x: 704, y: 1056 },
                    function (result) { console.log("WORLD_SPAWN_MOVE accepted=" + !result.error); });
            } else if (!attacked) {
                var enemy = snapshot.units.filter(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                })[0];
                if (!enemy) return;
                attacked = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 9102, unit_ids: runtime, verb: "attack", target_id: enemy.id },
                    function (result) {
                        console.log("WORLD_SPAWN_ATTACK accepted=" + !result.error);
                        if (typeof STARCOASTER_TEST_RECOVERY !== "undefined" && STARCOASTER_TEST_RECOVERY)
                            context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                                request: 9104, unit_ids: runtime, verb: "stop" },
                                function (stopped) {
                                    console.log("WORLD_SPAWN_STOP accepted=" + !stopped.error);
                                });
                    });
            }
        });
    }
});
