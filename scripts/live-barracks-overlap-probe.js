/* Test-only race: place park scenery while a native Marine stands inside it. */
registerPlugin({ name: "Barracks overlap probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const marineID = "openbw:1003";
        let started = 0, placed = false;
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            const marine = snapshot.units.filter(function (unit) { return unit.id === marineID; })[0];
            if (!marine || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) {
                started = Date.now();
                context.executeAction("rtsbridge.marineCommand", {
                    session: snapshot.session, request: 1, unit_ids: [marineID],
                    verb: "move", x: 3264, y: 3376
                }, function (result) {
                    console.log("BARRACKS_OVERLAP_MOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!placed && marine.x >= 3200 && marine.x < 3328
                && marine.y >= 3328 && marine.y < 3424) {
                placed = true;
                const object = objectManager.getAllObjects("large_scenery").filter(function (entry) {
                    return entry.identifier === "starcoaster.scenery_large.terran_barracks";
                })[0];
                if (!object) { console.log("BARRACKS_OVERLAP_ERROR object_missing"); return; }
                context.executeAction("largesceneryplace", { x: 3200, y: 3328, z: 1216,
                    direction: 0, object: object.index, primaryColour: 0,
                    secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                    console.log("BARRACKS_OVERLAP_BUILD accepted=" + !result.error
                        + " marine_x=" + marine.x + " marine_y=" + marine.y
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!placed && Date.now() - started > 45000) {
                placed = true;
                console.log("BARRACKS_OVERLAP_ERROR marine_did_not_reach_site x="
                    + marine.x + " y=" + marine.y);
            }
        });
    }
});
