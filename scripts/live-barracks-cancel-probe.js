/* Test-only cancellation of a native training queue by park demolition. */
registerPlugin({ name: "Barracks cancellation probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const barracks = objectManager.getAllObjects("large_scenery").find(function (item) {
            return item.identifier === "starcoaster.scenery_large.terran_barracks";
        });
        if (!barracks) throw new Error("Barracks scenery object is unavailable");
        const building = "openrct2:large_scenery:" + barracks.index + ":3200:3328:1216:0#1";
        let started = 0, lastAttempt = 0, trainedAt = 0, removed = false;
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            if (!trainedAt && Date.now() - started > 4000 && Date.now() - lastAttempt > 2000) {
                lastAttempt = Date.now();
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 201, unit_ids: [], verb: "train", target_entity_id: building },
                function (result) {
                    if (result.error) return;
                    trainedAt = Date.now();
                    console.log("BARRACKS_CANCEL_TRAIN_ACCEPTED");
                });
            }
            if (trainedAt && !removed && Date.now() - trainedAt > 3500) {
                removed = true;
                context.executeAction("largesceneryremove", { x: 3200, y: 3328,
                    z: 1216, direction: 0, tileIndex: 0 }, function (result) {
                    console.log("BARRACKS_CANCEL_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
        });
    }
});
