/* Test-only race: place a supported building over a moving native Marine. */
registerPlugin({ name: "Barracks overlap probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const building = typeof STARCOASTER_OVERLAP_BUILDING === "string"
            ? STARCOASTER_OVERLAP_BUILDING : "terran_barracks";
        const label = ({ terran_barracks: "BARRACKS", terran_academy: "ACADEMY",
            terran_supply_depot: "SUPPLY_DEPOT", terran_factory: "FACTORY" })[building];
        const footprint = building === "terran_academy" || building === "terran_supply_depot"
            ? { width: 96, height: 64 } : { width: 128, height: 96 };
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
                    console.log(label + "_OVERLAP_MOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!placed && marine.x >= 3200 && marine.x < 3200 + footprint.width
                && marine.y >= 3328 && marine.y < 3328 + footprint.height) {
                placed = true;
                const object = objectManager.getAllObjects("large_scenery").filter(function (entry) {
                    return entry.identifier === "starcoaster.scenery_large." + building;
                })[0];
                if (!object) { console.log(label + "_OVERLAP_ERROR object_missing"); return; }
                context.executeAction("largesceneryplace", { x: 3200, y: 3328, z: 1216,
                    direction: 0, object: object.index, primaryColour: 0,
                    secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                    console.log(label + "_OVERLAP_BUILD accepted=" + !result.error
                        + " marine_x=" + marine.x + " marine_y=" + marine.y
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!placed && Date.now() - started > 45000) {
                placed = true;
                console.log(label + "_OVERLAP_ERROR marine_did_not_reach_site x="
                    + marine.x + " y=" + marine.y);
            }
        });
    }
});
