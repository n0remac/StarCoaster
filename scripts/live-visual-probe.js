// Test-only nonblocking wall mapping and unchanged native navigation probe.
registerPlugin({ name: "Live Visual Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, phase = 0;
        const x = 640, y = 992;
        function z() {
            const tile = map.getTile(20, 31);
            for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === "surface") return element.baseZ || element.baseHeight * 8;
            }
            return 128;
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            const elapsed = Date.now() - started;
            if (phase === 0 && elapsed > 3000) {
                phase = 1;
                const wall = objectManager.getAllObjects("wall").filter(function (item) {
                    return item.identifier === "rct2.scenery_wall.wbr1";
                })[0];
                if (!wall) { console.log("LIVE_VISUAL_ERROR wall_object_missing"); return; }
                context.executeAction("wallplace", { x: x, y: y, z: z(), object: wall.index,
                    edge: 0, primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 },
                    function (result) {
                        console.log("LIVE_VISUAL_BUILD accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            } else if (phase === 1 && elapsed > 12000) {
                phase = 2;
                context.executeAction("wallremove", { x: x, y: y, z: z(), direction: 0 },
                    function (result) {
                        console.log("LIVE_VISUAL_REMOVE accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            } else if (phase === 2 && elapsed > 23000) {
                phase = 3;
                console.log("LIVE_VISUAL_COMPLETE actors=" + snapshot.units.map(function (actor) {
                    return actor.id;
                }).sort().join(","));
            }
        });
    }
});
