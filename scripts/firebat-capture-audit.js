/* Test-only graphical audit of the shared Academy and Barracks windows. */
registerPlugin({ name: "Firebat capture audit", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const reported = {};
        let frame = 0, reportedFirebat = false;
        context.subscribe("interval.tick", function () {
            if (++frame % 10 !== 0) return;
            for (const classification of ["starcoaster-construction",
                    "starcoaster-barracks-info", "starcoaster-building-info"]) {
                const window = ui.getWindow(classification);
                if (!window) {
                    delete reported[classification];
                    continue;
                }
                const position = [window.x, window.y, window.width, window.height].join(",");
                if (reported[classification] !== position) {
                    reported[classification] = position;
                    console.log("FIREBAT_CAPTURE_WINDOW type=" + classification
                        + " x=" + window.x + " y=" + window.y
                        + " width=" + window.width + " height=" + window.height);
                }
            }
            if (!reportedFirebat) {
                const snapshot = rtsBridge.getActors();
                const actor = snapshot && snapshot.units.find(function (unit) {
                    return unit.kind === "terran_firebat" && unit.hp > 0;
                });
                if (actor) {
                    reportedFirebat = true;
                    if (ui.mainViewport) {
                        const tile = map.getTile(Math.floor(actor.x / 32), Math.floor(actor.y / 32));
                        let z = 0;
                        for (let index = 0; index < tile.numElements; index++) {
                            const item = tile.getElement(index);
                            if (item.type === "surface")
                                z = item.baseZ === undefined ? item.baseHeight * 8 : item.baseZ;
                        }
                        ui.mainViewport.moveTo({ x: actor.x, y: actor.y, z: z });
                    }
                    console.log("FIREBAT_CAPTURE_ACTOR id=" + actor.id
                        + " x=" + actor.x + " y=" + actor.y + " hp=" + actor.hp);
                }
            }
        });
    }
});
