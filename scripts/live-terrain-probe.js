// Test-only synchronized land, water, and unsupported slope probe.
registerPlugin({ name: "Live Terrain Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, phase = 0, tiles = [];
        function freeTiles() {
            const result = [];
            for (let y = 29; y <= 36 && result.length < 2; y++)
                for (let x = 27; x <= 37 && result.length < 2; x++) {
                    const tile = map.getTile(x, y);
                    if (tile.numElements !== 1) continue;
                    const surface = tile.getElement(0);
                    if (surface.type === "surface" && surface.baseHeight === 14
                        && !surface.slope && !surface.waterHeight) result.push({ x: x, y: y });
                }
            return result;
        }
        function action(name, tile, args, label) {
            context.executeAction(name, Object.assign({ x: tile.x * 32, y: tile.y * 32 }, args),
                function (result) {
                    console.log("LIVE_TERRAIN_ACTION phase=" + label + " accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) { started = Date.now(); tiles = freeTiles(); }
            if (tiles.length < 2) { console.log("LIVE_TERRAIN_ERROR no_free_tiles"); return; }
            const elapsed = Date.now() - started;
            if (phase === 0 && elapsed > 3000) {
                phase = 1; action("landsetheight", tiles[0], { height: 16, style: 0 }, "raise");
            } else if (phase === 1 && elapsed > 10000) {
                phase = 2; action("landsetheight", tiles[0], { height: 14, style: 0 }, "lower");
            } else if (phase === 2 && elapsed > 17000) {
                phase = 3; action("watersetheight", tiles[1], { height: 16 }, "water_raise");
            } else if (phase === 3 && elapsed > 24000) {
                phase = 4; action("watersetheight", tiles[1], { height: 14 }, "water_lower");
            } else if (phase === 4 && elapsed > 31000) {
                phase = 5; action("landsetheight", tiles[0], { height: 14, style: 16 }, "invalid_slope");
            } else if (phase === 5 && elapsed > 39000) {
                phase = 6; action("landsetheight", tiles[0], { height: 14, style: 0 }, "restore");
            } else if (phase === 6 && elapsed > 53000) {
                phase = 7;
                console.log("LIVE_TERRAIN_COMPLETE actors=" + snapshot.units.map(function (actor) {
                    return actor.id;
                }).sort().join(","));
            }
        });
    }
});
