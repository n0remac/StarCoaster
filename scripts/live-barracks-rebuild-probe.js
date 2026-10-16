/* Test-only demolition and reconstruction after loading a saved Barracks. */
registerPlugin({ name: "Barracks rebuild probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let removedAt = 0, rebuilt = false;
        context.subscribe("interval.tick", function () {
            const actors = rtsBridge.getActors();
            if (!actors.session) return;
            if (!removedAt) {
                removedAt = Date.now();
                context.executeAction("largesceneryremove", { x: 3200, y: 3328,
                    z: 1216, direction: 0, tileIndex: 0 }, function (result) {
                    console.log("BARRACKS_REBUILD_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (rebuilt || Date.now() - removedAt < 8000) return;
            rebuilt = true;
            const object = objectManager.getAllObjects("large_scenery").filter(function (item) {
                return item.identifier === "starcoaster.scenery_large.terran_barracks";
            })[0];
            if (!object) { console.log("BARRACKS_REBUILD_ERROR object_missing"); return; }
            context.executeAction("largesceneryplace", { x: 3200, y: 3328, z: 1216,
                direction: 0, object: object.index, primaryColour: 0,
                secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                console.log("BARRACKS_REBUILD_BUILD accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
