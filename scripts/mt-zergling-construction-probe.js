// Test-only ordinary OpenRCT2 wall construction while Mt. Zergling is under attack.
registerPlugin({ name: "Mt. Zergling Construction Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let attempted = false;
        const candidates = [[110, 110], [105, 110], [112, 116], [119, 110], [114, 113], [105, 120]];
        function groundZ(x, y) {
            const tile = map.getTile(x, y);
            for (let i = 0; i < tile.numElements; i++) {
                const element = tile.getElement(i);
                if (element.type === "surface")
                    return element.baseZ === undefined ? element.baseHeight * 8 : element.baseZ;
            }
            return -1;
        }
        function placeAt(index, object) {
            if (index >= candidates.length) {
                console.log("MT_ZERGLING_CONSTRUCTION_FAILED no_valid_tile");
                return;
            }
            const position = candidates[index];
            const args = { x: position[0] * 32, y: position[1] * 32,
                z: groundZ(position[0], position[1]), object: object, edge: 0,
                primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
            context.queryAction("wallplace", args, function (query) {
                if (query.error) {
                    console.log("MT_ZERGLING_CONSTRUCTION_QUERY x=" + position[0]
                        + " y=" + position[1] + " accepted=false reason=" + query.errorMessage);
                    placeAt(index + 1, object);
                    return;
                }
                context.executeAction("wallplace", args, function (result) {
                    console.log("MT_ZERGLING_CONSTRUCTION_BUILD x=" + position[0]
                        + " y=" + position[1] + " accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            });
        }
        context.subscribe("interval.tick", function () {
            if (attempted) return;
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !snapshot.units || !snapshot.units.some(function (actor) {
                return actor.kind === "zerg_zergling" && actor.hp > 0;
            })) return;
            attempted = true;
            const wall = objectManager.getAllObjects("wall").filter(function (entry) {
                return entry.identifier === "rct2.scenery_wall.wbr1";
            })[0];
            if (!wall) {
                console.log("MT_ZERGLING_CONSTRUCTION_FAILED wall_object_missing");
                return;
            }
            console.log("MT_ZERGLING_CONSTRUCTION_ATTEMPT zerglings=" + snapshot.units.filter(function (actor) {
                return actor.kind === "zerg_zergling" && actor.hp > 0;
            }).length);
            placeAt(0, wall.index);
        });
    }
});
