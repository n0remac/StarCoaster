/* Test-only client request through the player-facing train action. */
registerPlugin({ name: "Barracks training probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const building = "openrct2:large_scenery:248:3200:3328:1216:0#1";
        let started = 0, requested = false, duplicateRequested = false, lastAttempt = 0, moved = false;
        const captureUITraining = typeof STARCOASTER_CAPTURE_UI_TRAINING !== "undefined"
            && STARCOASTER_CAPTURE_UI_TRAINING;
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            if (!captureUITraining && !requested && Date.now() - started >= 4000 && Date.now() - lastAttempt >= 2000) {
                lastAttempt = Date.now();
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 101, unit_ids: [], verb: "train", target_entity_id: building },
                function (result) {
                    console.log("BARRACKS_TRAIN_PROBE_ACTION accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (!result.error) requested = true;
                });
            }
            if (!captureUITraining && requested && !duplicateRequested && Date.now() - lastAttempt >= 1000) {
                duplicateRequested = true;
                console.log("BARRACKS_TRAIN_PROBE_DUPLICATE_ATTEMPT");
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 101, unit_ids: [], verb: "train", target_entity_id: building },
                function (duplicate) {
                    console.log("BARRACKS_TRAIN_PROBE_DUPLICATE_RESPONSE rejected=" + !!duplicate.error
                        + " reason=" + (duplicate.errorMessage || "ok"));
                });
            }
            const marine = snapshot.units.filter(function (unit) {
                return /^openbw:3[0-9]+$/.test(unit.id) && unit.kind === "terran_marine";
            })[0];
            if (!marine || moved) return;
            moved = true;
            console.log("BARRACKS_TRAIN_PROBE_MARINE id=" + marine.id
                + " x=" + marine.x + " y=" + marine.y + " hp=" + marine.hp);
            context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                request: 102, unit_ids: [marine.id], verb: "move",
                x: marine.x + 64, y: marine.y + 64 }, function (result) {
                console.log("BARRACKS_TRAIN_PROBE_MOVE accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
