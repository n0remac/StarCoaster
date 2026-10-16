/* Test-only client placement at the verified Mt. Zergling building site. */
registerPlugin({ name: "Barracks build probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let attempted = false;
        context.subscribe("interval.tick", function () {
            if (attempted || !rtsBridge.getActors().session) return;
            const object = objectManager.getAllObjects("large_scenery").filter(function (item) {
                return item.identifier === "starcoaster.scenery_large.terran_barracks";
            })[0];
            if (!object) return;
            attempted = true;
            const args = { x: 3200, y: 3328, z: 1216, direction: 0,
                object: object.index, primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
            context.queryAction("largesceneryplace", args, function (query) {
                if (query.error) { console.log("BARRACKS_BUILD_PROBE_ERROR query=" + query.errorMessage); return; }
                context.executeAction("largesceneryplace", args, function (result) {
                    console.log("BARRACKS_BUILD_PROBE_RESULT accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            });
        });
    }
});
