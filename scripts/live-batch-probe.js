// Test-only synchronized multi-action construction batch.
registerPlugin({ name: "Live Batch Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const pathOnly = typeof STARCOASTER_TEST_PATH_ONLY !== "undefined" && STARCOASTER_TEST_PATH_ONLY;
        let started = 0, built = false, completed = 0;
        function chooseTiles() {
            const result = [];
            for (let y = 29; y <= 36 && result.length < 6; y++)
                for (let x = 27; x <= 37 && result.length < 6; x++) {
                    const tile = map.getTile(x, y);
                    if (tile.numElements !== 1) continue;
                    const surface = tile.getElement(0);
                    if (surface.type !== "surface" || surface.baseHeight !== 14
                        || surface.slope || surface.waterHeight) continue;
                    result.push({ x: x, y: y, z: surface.baseZ || 112 });
                }
            return result;
        }
        function build() {
            const tiles = chooseTiles();
            const wall = objectManager.getAllObjects("wall").filter(function (item) {
                return item.identifier === "rct2.scenery_wall.wbr1";
            })[0];
            const scenery = objectManager.getAllObjects("small_scenery")[0];
            if (tiles.length < 6 || !wall || !scenery) {
                console.log("LIVE_BATCH_ERROR construction_inputs_missing"); return;
            }
            const actions = [];
            for (let index = 0; index < 3; index++) {
                const tile = tiles[index];
                actions.push({ kind: "footpathplace", args: { x: tile.x * 32, y: tile.y * 32,
                    z: tile.z, object: 4, railingsObject: 0, direction: 0,
                    slopeType: 0, slopeDirection: 0, constructFlags: 0 } });
            }
            if (!pathOnly) {
                for (let index = 3; index < 5; index++) {
                    const tile = tiles[index];
                    actions.push({ kind: "wallplace", args: { x: tile.x * 32, y: tile.y * 32,
                        z: tile.z, object: wall.index, edge: 0, primaryColour: 0,
                        secondaryColour: 0, tertiaryColour: 0 } });
                }
                const tile = tiles[5];
                actions.push({ kind: "smallsceneryplace", args: { x: tile.x * 32, y: tile.y * 32,
                    z: tile.z, direction: 0, quadrant: 0, object: scenery.index,
                    primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 } });
            }
            actions.forEach(function (action, index) {
                context.executeAction(action.kind, action.args, function (result) {
                    completed++;
                    console.log("LIVE_BATCH_ACTION index=" + index + " kind=" + action.kind
                        + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                });
            });
            console.log("LIVE_BATCH_SUBMITTED count=" + actions.length);
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            if (!built && Date.now() - started > 3000) { built = true; build(); }
            if (built && Date.now() - started > 16000) {
                console.log("LIVE_BATCH_COMPLETE callbacks=" + completed + " actors="
                    + snapshot.units.map(function (actor) { return actor.id; }).sort().join(","));
                started = Number.MAX_SAFE_INTEGER;
            }
        });
    }
});
